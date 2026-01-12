"""
Base Parser Abstract Class.

Defines the interface that all store parsers must implement.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, AsyncGenerator
from playwright.async_api import Page

from parser_service.internal.models.product import RawProduct


class BaseParser(ABC):
    """
    Abstract base class for store parsers.

    Each parser implementation must provide:
    - Store name identifier
    - Category URL extraction
    - Product URL extraction with pagination
    - Product page parsing
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Get the parser name/identifier.

        Returns:
            Parser name (e.g., "leroymerlin.ru", "sdvor.com")
        """
        pass

    @abstractmethod
    async def get_category_urls(self, page: Page) -> List[str]:
        """
        Extract category URLs from the store's catalog.

        Args:
            page: Playwright Page instance for the catalog page.

        Returns:
            List of category URLs to scrape.
        """
        pass

    @abstractmethod
    async def get_product_urls(self, page: Page, category_url: str) -> AsyncGenerator[str, None]:
        """
        Extract product URLs from a category page with pagination support.

        This method should handle pagination automatically and yield
        product URLs as they are discovered.

        Args:
            page: Playwright Page instance.
            category_url: The category page URL to scrape.

        Yields:
            Product URLs from the category.
        """
        pass

    @abstractmethod
    async def parse_product(self, page: Page, url: str) -> Optional[RawProduct]:
        """
        Parse a product page and extract structured data.

        Implementation strategy should be:
        1. Try JSON-LD (Schema.org) extraction
        2. Try __NEXT_DATA__ extraction (for Next.js sites)
        3. Fallback to HTML parsing

        Args:
            page: Playwright Page instance.
            url: The product page URL to parse.

        Returns:
            RawProduct instance or None if parsing failed.
        """
        pass

    async def extract_json_ld(self, page: Page) -> Optional[dict]:
        """
        Extract JSON-LD (Schema.org) structured data from page.

        Args:
            page: Playwright Page instance.

        Returns:
            Parsed JSON-LD data or None if not found.
        """
        try:
            script = await page.query_selector('script[type="application/ld+json"]')
            if script:
                content = await script.inner_text()
                import json

                return json.loads(content)
        except Exception as e:
            # Log error but don't fail - this is a fallback method
            print(f"JSON-LD extraction failed: {e}")
        return None

    async def extract_next_data(self, page: Page) -> Optional[dict]:
        """
        Extract __NEXT_DATA__ from Next.js sites.

        Args:
            page: Playwright Page instance.

        Returns:
            Parsed __NEXT_DATA__ or None if not found.
        """
        try:
            script = await page.query_selector("script#__NEXT_DATA__")
            if script:
                content = await script.inner_text()
                import json

                return json.loads(content)
        except Exception as e:
            print(f"__NEXT_DATA__ extraction failed: {e}")
        return None
