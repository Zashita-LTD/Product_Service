"""
Browser instance management with Playwright.

Handles headless browser operations, proxy rotation, and anti-detection.
"""
import random
from typing import Optional, List, Set
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from pkg.logger.logger import get_logger
from config.settings import Settings


logger = get_logger(__name__)


class ProxyPool:
    """
    Proxy pool with rotation and health tracking.
    """
    
    def __init__(self, proxies: List[str]):
        """
        Initialize proxy pool.
        
        Args:
            proxies: List of proxy URLs (format: http://user:pass@host:port).
        """
        self._all_proxies = proxies.copy()
        self._good_proxies = proxies.copy()
        self._bad_proxies: Set[str] = set()
        logger.info(f"Proxy pool initialized with {len(self._all_proxies)} proxies")
    
    def get_random_proxy(self) -> Optional[str]:
        """
        Get a random good proxy.
        
        Returns:
            Proxy URL or None if no good proxies available.
        """
        if not self._good_proxies:
            # Reset pool if all proxies are bad
            logger.warning("All proxies marked as bad, resetting pool")
            self._good_proxies = self._all_proxies.copy()
            self._bad_proxies.clear()
        
        if self._good_proxies:
            proxy = random.choice(self._good_proxies)
            logger.debug(f"Selected proxy: {self._mask_proxy(proxy)}")
            return proxy
        
        return None
    
    def mark_bad(self, proxy: str) -> None:
        """
        Mark a proxy as bad.
        
        Args:
            proxy: Proxy URL to mark as bad.
        """
        if proxy in self._good_proxies:
            self._good_proxies.remove(proxy)
            self._bad_proxies.add(proxy)
            logger.warning(
                f"Proxy marked as bad: {self._mask_proxy(proxy)}. "
                f"Good proxies left: {len(self._good_proxies)}"
            )
    
    @staticmethod
    def _mask_proxy(proxy: str) -> str:
        """Mask proxy credentials for logging."""
        if "@" in proxy:
            parts = proxy.split("@")
            if len(parts) == 2:
                return f"***@{parts[1]}"
        return proxy
    
    @property
    def has_proxies(self) -> bool:
        """Check if pool has any proxies."""
        return len(self._all_proxies) > 0


class BrowserInstance:
    """
    Playwright browser instance manager.
    
    Manages browser lifecycle, proxy rotation, and anti-detection.
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize browser instance.
        
        Args:
            settings: Application settings.
        """
        self._settings = settings
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._current_proxy: Optional[str] = None
        
        # Initialize proxy pool
        proxies = settings.get_proxies()
        self._proxy_pool = ProxyPool(proxies) if proxies else None
        
        logger.info(
            f"Browser instance initialized (headless={settings.headless}, "
            f"proxies={'enabled' if self._proxy_pool else 'disabled'})"
        )
    
    async def start(self) -> None:
        """Start Playwright and browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._settings.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ]
        )
        logger.info("Browser started")
        
        # Create initial context
        await self._create_context()
    
    async def stop(self) -> None:
        """Stop browser and Playwright."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser stopped")
    
    async def _create_context(self) -> None:
        """Create a new browser context with random UA and proxy."""
        if self._context:
            await self._context.close()
        
        # Select random user agent
        user_agent = random.choice(self._settings.user_agents)
        
        # Get proxy if available
        proxy = None
        if self._proxy_pool and self._proxy_pool.has_proxies:
            proxy_url = self._proxy_pool.get_random_proxy()
            if proxy_url:
                self._current_proxy = proxy_url
                # Parse proxy URL
                # Format: http://user:pass@host:port or http://host:port
                if "@" in proxy_url:
                    protocol_auth, server = proxy_url.split("@", 1)
                    protocol, auth = protocol_auth.split("://", 1)
                    username, password = auth.split(":", 1) if ":" in auth else (auth, "")
                    proxy = {
                        "server": f"{protocol}://{server}",
                        "username": username,
                        "password": password,
                    }
                else:
                    proxy = {"server": proxy_url}
        
        # Create context with stealth
        context_options = {
            "user_agent": user_agent,
            "viewport": {"width": 1920, "height": 1080},
            "locale": "ru-RU",
            "timezone_id": "Europe/Moscow",
        }
        
        if proxy:
            context_options["proxy"] = proxy
        
        self._context = await self._browser.new_context(**context_options)
        
        # Add stealth scripts
        await self._context.add_init_script("""
            // Overwrite the navigator.webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Overwrite the navigator.plugins property
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Overwrite the navigator.languages property
            Object.defineProperty(navigator, 'languages', {
                get: () => ['ru-RU', 'ru', 'en-US', 'en']
            });
        """)
        
        logger.info(
            f"Browser context created (proxy={'enabled' if proxy else 'disabled'}, "
            f"ua={user_agent[:50]}...)"
        )
    
    async def new_page(self) -> Page:
        """
        Create a new page in the current context.
        
        Returns:
            New page instance.
        """
        if not self._context:
            raise RuntimeError("Browser context not initialized")
        
        page = await self._context.new_page()
        return page
    
    async def handle_error(self, error: Exception) -> None:
        """
        Handle browser error and potentially rotate proxy.
        
        Args:
            error: Exception that occurred.
        """
        error_str = str(error).lower()
        
        # Check if error is proxy-related
        should_rotate = any(
            keyword in error_str
            for keyword in ["timeout", "403", "429", "proxy", "connection"]
        )
        
        if should_rotate and self._proxy_pool and self._current_proxy:
            logger.warning(f"Error detected, marking proxy as bad: {error}")
            self._proxy_pool.mark_bad(self._current_proxy)
            
            # Recreate context with new proxy
            await self._create_context()
        else:
            logger.error(f"Browser error: {error}")
    
    async def rotate_context(self) -> None:
        """Manually rotate browser context (new UA and proxy)."""
        logger.info("Rotating browser context")
        await self._create_context()
