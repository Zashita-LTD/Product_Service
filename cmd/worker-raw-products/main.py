"""
Raw Products Worker Entry Point.

Consumes raw product data from parser-service and creates product families.
Implements the ingestion pipeline for scraped products.
"""
import asyncio
import os
import signal
from typing import Optional

from dotenv import load_dotenv

from internal.infrastructure.postgres.repository import (
    PostgresProductRepository,
    create_pool,
)
from internal.infrastructure.redis.cache import RedisCache, ProductCacheService
from internal.infrastructure.kafka.consumer import KafkaConsumer
from internal.infrastructure.kafka.producer import KafkaProducer
from internal.usecase.create_product import CreateProductUseCase
from internal.usecase.ingest_raw_product import (
    IngestRawProductUseCase,
    RawProductEventHandler,
)
from pkg.logger.logger import setup_logging, get_logger


# Load environment variables
load_dotenv()

# Setup logging
setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_format=os.getenv("LOG_FORMAT", "json") == "json",
)

logger = get_logger(__name__)


# Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/product_service",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_GROUP_ID = os.getenv("KAFKA_RAW_GROUP_ID", "raw-products-worker")
KAFKA_RAW_TOPICS = os.getenv("KAFKA_RAW_TOPICS", "raw-products").split(",")


class RawProductsWorker:
    """
    Worker for processing raw products from parser-service.

    Consumes raw product data from Kafka, deduplicates by source_url,
    creates product families, and triggers enrichment pipeline.
    """

    def __init__(self) -> None:
        """Initialize the worker."""
        self._running = False
        self._db_pool = None
        self._redis_cache: Optional[RedisCache] = None
        self._consumer: Optional[KafkaConsumer] = None
        self._producer: Optional[KafkaProducer] = None

    async def start(self) -> None:
        """Start the worker."""
        logger.info("Starting Raw Products Worker...")

        self._running = True

        # Initialize database pool
        try:
            self._db_pool = await create_pool(DATABASE_URL)
            logger.info("Database pool created")
        except Exception as e:
            logger.error("Failed to create database pool", error=str(e))
            raise

        # Initialize Redis cache
        try:
            self._redis_cache = RedisCache(redis_url=REDIS_URL)
            await self._redis_cache.connect()
            logger.info("Redis cache connected")
        except Exception as e:
            logger.warning("Failed to connect to Redis", error=str(e))
            self._redis_cache = None

        # Initialize Kafka producer for publishing events
        try:
            self._producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                client_id="raw-products-worker-producer",
            )
            await self._producer.start()
            logger.info("Kafka producer started")
        except Exception as e:
            logger.error("Failed to start Kafka producer", error=str(e))
            raise

        # Create repository and services
        repository = PostgresProductRepository(self._db_pool)
        cache_service = ProductCacheService(self._redis_cache) if self._redis_cache else None

        # Create use cases
        create_use_case = CreateProductUseCase(
            repository=repository,
            cache=cache_service,
        )

        ingest_use_case = IngestRawProductUseCase(
            repository=repository,
            create_use_case=create_use_case,
            cache=self._redis_cache,
        )

        # Create event handler
        handler = RawProductEventHandler(ingest_use_case)

        # Initialize Kafka consumer
        self._consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=KAFKA_GROUP_ID,
            topics=KAFKA_RAW_TOPICS,
            client_id="raw-products-worker",
        )

        # Register handlers for raw product events
        self._consumer.register_handler(
            "raw_product",
            handler.handle,
        )
        # Also handle legacy event type if parser sends different format
        self._consumer.register_handler(
            "product.scraped",
            handler.handle,
        )

        # Start consumer
        await self._consumer.start()

        logger.info(
            "Raw Products Worker started successfully",
            topics=KAFKA_RAW_TOPICS,
        )

        # Start consuming
        try:
            await self._consumer.consume()
        except asyncio.CancelledError:
            logger.info("Worker consumption cancelled")

    async def stop(self) -> None:
        """Stop the worker."""
        logger.info("Stopping Raw Products Worker...")

        self._running = False

        if self._consumer:
            await self._consumer.stop()

        if self._producer:
            await self._producer.stop()

        if self._redis_cache:
            await self._redis_cache.disconnect()

        if self._db_pool:
            await self._db_pool.close()

        logger.info("Raw Products Worker stopped")


async def main() -> None:
    """Main entry point."""
    worker = RawProductsWorker()

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        asyncio.create_task(worker.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await worker.start()
    except Exception as e:
        logger.error("Worker failed", error=str(e))
        await worker.stop()
        raise


if __name__ == "__main__":
    asyncio.run(main())
