"""
Parser service settings.

Configuration loaded from environment variables.
"""
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Parser service configuration."""
    
    # Kafka settings
    kafka_bootstrap_servers: str = "kafka:29092"
    kafka_raw_products_topic: str = "raw-products"
    kafka_client_id: str = "parser-service"
    kafka_compression_type: str = "gzip"
    
    # Petrovich settings
    petrovich_base_url: str = "https://moscow.petrovich.ru"
    
    # Parsing settings
    parsing_interval_seconds: int = 21600  # 6 hours
    headless: bool = True
    max_concurrent_pages: int = 3
    min_delay_seconds: float = 1.5
    max_delay_seconds: float = 4.0
    max_retries: int = 3
    max_products_per_run: int = 10000
    
    # Proxy settings
    proxy_list: Optional[str] = None  # Comma-separated list
    proxy_file: str = "proxies.txt"
    
    # Browser settings
    user_agents: List[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    def get_proxies(self) -> List[str]:
        """
        Get list of proxies from environment or file.
        
        Returns:
            List of proxy URLs.
        """
        proxies = []
        
        # First try from environment variable
        if self.proxy_list:
            proxies = [p.strip() for p in self.proxy_list.split(",") if p.strip()]
        
        # Then try from file
        if not proxies:
            try:
                with open(self.proxy_file, "r") as f:
                    proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            except FileNotFoundError:
                pass
        
        return proxies


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Returns:
        Settings instance.
    """
    return Settings()
