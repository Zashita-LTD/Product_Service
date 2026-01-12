"""
Raw Products Import Worker Entry Point.

Consumes raw products from Parser Service and imports them into the database.
"""

import asyncio
import os
import signal
from typing import Optional

from dotenv import load_dotenv

from internal.infrastructure.kafka.raw_product_consumer import (
    RawProductConsumer,
    RawProductImportHandler,
)
from internal.infrastructure.postgres.repository import (
    PostgresProductRepository,
    create_pool,
)
from pkg.logger.logger import get_logger, setup_logging

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
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "product-service-raw-consumer")
KAFKA_RAW_PRODUCTS_TOPIC = os.getenv("KAFKA_RAW_PRODUCTS_TOPIC", "raw-products")


class RawProductsWorker:
    """
    Worker for processing raw product imports from Parser Service.

    Consumes events from Kafka and imports products into the database.
    """

    def __init__(self) -> None:
        """Initialize the worker."""
        self._running = False
        self._db_pool = None
        self._consumer: Optional[RawProductConsumer] = None

    async def start(self) -> None:
        """Start the worker."""
        logger.info("Starting Raw Products Import Worker...")

        self._running = True

        # Initialize database pool
        try:
            self._db_pool = await create_pool(DATABASE_URL)
            logger.info("Database pool created")
        except Exception as e:
            logger.error("Failed to create database pool", error=str(e))
            raise

        # Create repository
        repository = PostgresProductRepository(self._db_pool)

        # Create import handler
        handler = RawProductImportHandler(repository=repository)

        # Initialize Kafka consumer
        self._consumer = RawProductConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=KAFKA_GROUP_ID,
            topic=KAFKA_RAW_PRODUCTS_TOPIC,
        )

        # Set handler
        self._consumer.set_handler(handler)

        # Start consumer
        await self._consumer.start()

        logger.info(
            "Raw Products Import Worker started successfully",
            topic=KAFKA_RAW_PRODUCTS_TOPIC,
            group_id=KAFKA_GROUP_ID,
        )

        # Start consuming
        try:
            await self._consumer.consume()
        except asyncio.CancelledError:
            logger.info("Worker consumption cancelled")

    async def stop(self) -> None:
        """Stop the worker."""
        logger.info("Stopping Raw Products Import Worker...")

        self._running = False

        if self._consumer:
            await self._consumer.stop()

        if self._db_pool:
            await self._db_pool.close()

        logger.info("Raw Products Import Worker stopped")


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
