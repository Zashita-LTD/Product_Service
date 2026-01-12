"""
Parser Service Configuration.

Manages settings for all store parsers via environment variables.
"""

import os
from typing import List


class Settings:
    """Parser service settings."""

    # Application settings
    APP_NAME: str = os.getenv("APP_NAME", "parser-service")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Store base URLs
    PETROVICH_BASE_URL: str = os.getenv("PETROVICH_BASE_URL", "https://petrovich.ru")
    LEROYMERLIN_BASE_URL: str = os.getenv("LEROYMERLIN_BASE_URL", "https://leroymerlin.ru")
    SDVOR_BASE_URL: str = os.getenv("SDVOR_BASE_URL", "https://sdvor.com")
    OBI_BASE_URL: str = os.getenv("OBI_BASE_URL", "https://obi.ru")

    # Parser configuration
    ENABLED_PARSERS: str = os.getenv("ENABLED_PARSERS", "petrovich,leroymerlin,sdvor,obi")

    # Scraping settings
    MAX_CONCURRENT_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "5"))
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30000"))  # milliseconds
    HEADLESS_BROWSER: bool = os.getenv("HEADLESS_BROWSER", "true").lower() == "true"

    # Kafka settings for publishing scraped data
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_RAW_PRODUCTS_TOPIC: str = os.getenv("KAFKA_RAW_PRODUCTS_TOPIC", "raw-products")

    # Rate limiting
    REQUESTS_PER_SECOND: int = int(os.getenv("REQUESTS_PER_SECOND", "2"))

    # Retry settings
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY: int = int(os.getenv("RETRY_DELAY", "5"))  # seconds

    @classmethod
    def get_enabled_parsers(cls) -> List[str]:
        """
        Get list of enabled parser names.

        Returns:
            List of parser names to enable.
        """
        return [p.strip() for p in cls.ENABLED_PARSERS.split(",") if p.strip()]

    @classmethod
    def get_base_url(cls, parser_name: str) -> str:
        """
        Get base URL for a specific parser.

        Args:
            parser_name: Name of the parser (e.g., "petrovich", "leroymerlin")

        Returns:
            Base URL for the parser.
        """
        url_map = {
            "petrovich": cls.PETROVICH_BASE_URL,
            "leroymerlin": cls.LEROYMERLIN_BASE_URL,
            "sdvor": cls.SDVOR_BASE_URL,
            "obi": cls.OBI_BASE_URL,
        }
        return url_map.get(parser_name, "")


# Global settings instance
settings = Settings()
