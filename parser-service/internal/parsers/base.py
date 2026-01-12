"""
Base parser abstract class.

Defines the interface for all parsers.
"""
from abc import ABC, abstractmethod
from typing import List, AsyncIterator

from internal.models.product import RawProduct
from internal.browser.instance import BrowserInstance
from internal.kafka.producer import KafkaProducer


class BaseParser(ABC):
    """
    Abstract base class for website parsers.
    """
    
    def __init__(
        self,
        browser: BrowserInstance,
        kafka_producer: KafkaProducer,
    ):
        """
        Initialize parser.
        
        Args:
            browser: Browser instance for web scraping.
            kafka_producer: Kafka producer for sending products.
        """
        self._browser = browser
        self._kafka = kafka_producer
    
    @abstractmethod
    async def parse_catalog(self) -> AsyncIterator[RawProduct]:
        """
        Parse the entire catalog.
        
        Yields:
            Raw product data.
        """
        pass
    
    @abstractmethod
    async def parse_product(self, url: str) -> RawProduct:
        """
        Parse a single product page.
        
        Args:
            url: Product page URL.
            
        Returns:
            Raw product data.
        """
        pass
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Get the source name identifier."""
        pass
