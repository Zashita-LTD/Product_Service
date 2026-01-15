"""
Kafka producer for raw products.

Publishes parsed product data to Kafka for processing by Product Service.
"""
import json
from typing import Optional
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from internal.models.product import RawProduct
from pkg.logger.logger import get_logger
from config.settings import Settings


logger = get_logger(__name__)


class KafkaProducer:
    """
    Kafka producer for raw product data.
    
    Publishes digital twins to the raw-products topic.
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize Kafka producer.
        
        Args:
            settings: Application settings.
        """
        self._settings = settings
        self._producer: Optional[AIOKafkaProducer] = None
        self._messages_sent = 0
    
    async def start(self) -> None:
        """Start the Kafka producer."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            client_id=self._settings.kafka_client_id,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            compression_type=self._settings.kafka_compression_type,
            acks="all",
            enable_idempotence=True,
            max_in_flight_requests_per_connection=5,
            request_timeout_ms=30000,
            retry_backoff_ms=100,
        )
        
        await self._producer.start()
        logger.info(
            "Kafka producer started",
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            topic=self._settings.kafka_raw_products_topic,
        )
    
    async def stop(self) -> None:
        """Stop the Kafka producer."""
        if self._producer:
            await self._producer.stop()
            logger.info(
                "Kafka producer stopped",
                total_messages_sent=self._messages_sent,
            )
    
    async def send_product(self, product: RawProduct) -> None:
        """
        Send a raw product to Kafka.
        
        Args:
            product: Raw product data to send.
            
        Raises:
            RuntimeError: If producer is not started.
            KafkaError: If message cannot be sent.
        """
        if not self._producer:
            raise RuntimeError("Producer not started")
        
        try:
            # Use source_url as partition key for consistent partitioning
            key = str(product.source_url)
            value = product.to_kafka_message()
            
            # Send and wait for acknowledgment
            record_metadata = await self._producer.send_and_wait(
                topic=self._settings.kafka_raw_products_topic,
                key=key,
                value=value,
            )
            
            self._messages_sent += 1
            
            logger.info(
                "Product sent to Kafka",
                product_id=str(product.id),
                source_url=str(product.source_url),
                topic=record_metadata.topic,
                partition=record_metadata.partition,
                offset=record_metadata.offset,
                total_sent=self._messages_sent,
            )
            
        except KafkaError as e:
            logger.error(
                "Failed to send product to Kafka",
                product_id=str(product.id),
                source_url=str(product.source_url),
                error=str(e),
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                "Unexpected error sending product to Kafka",
                product_id=str(product.id),
                source_url=str(product.source_url),
                error=str(e),
                exc_info=True,
            )
            raise
    
    async def flush(self) -> None:
        """Flush any pending messages."""
        if self._producer:
            await self._producer.flush()
            logger.debug("Kafka producer flushed")
    
    @property
    def messages_sent(self) -> int:
        """Get total number of messages sent."""
        return self._messages_sent
