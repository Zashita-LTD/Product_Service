"""
Raw Products Import Worker Entry Point.

Consumes raw products from Parser Service and imports them into the database.
Now with MDM (Master Data Management) pipeline:
- Deduplication by EAN, SKU+Brand, Vector Search
- Data enrichment from multiple sources
- Manufacturer linking
"""

import asyncio
import os
import signal
from typing import Optional

from dotenv import load_dotenv

from internal.infrastructure.kafka.raw_product_consumer import (
    RawProductConsumer,
    RawProductImportHandler,
    MDMImportHandler,
)
from internal.infrastructure.postgres.repository import (
    PostgresProductRepository,
    create_pool,
)
from internal.infrastructure.postgres.raw_repository import (
    RawSnapshotRepository,
    ProductSourceLinkRepository,
    EnrichmentAuditRepository,
)
from internal.infrastructure.ai_provider.vertex_client import VertexAIEmbeddingClient
from internal.usecase.product_refinery import ProductRefinery
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
DEFAULT_CATEGORY_ID = int(os.getenv("DEFAULT_CATEGORY_ID", "1"))
VERTEX_PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
VERTEX_EMBEDDING_MODEL = os.getenv("VERTEX_EMBEDDING_MODEL", "text-embedding-004")

# MDM Feature Flag - включаем новую логику
USE_MDM_PIPELINE = os.getenv("USE_MDM_PIPELINE", "true").lower() == "true"


class RawProductsWorker:
    """
    Worker for processing raw product imports from Parser Service.

    Consumes events from Kafka and imports products into the database.
    Supports two modes:
    - Legacy: Direct import (RawProductImportHandler)
    - MDM: Deduplication & Enrichment pipeline (MDMImportHandler)
    """

    def __init__(self) -> None:
        """Initialize the worker."""
        self._running = False
        self._db_pool = None
        self._consumer: Optional[RawProductConsumer] = None

    async def start(self) -> None:
        """Start the worker."""
        logger.info(
            "Starting Raw Products Import Worker...",
            mdm_enabled=USE_MDM_PIPELINE,
        )

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

        # Initialize embedding client
        embedding_client = None
        if VERTEX_PROJECT_ID:
            try:
                embedding_client = VertexAIEmbeddingClient(
                    project_id=VERTEX_PROJECT_ID,
                    location=VERTEX_LOCATION,
                    model_id=VERTEX_EMBEDDING_MODEL,
                )
                await embedding_client.initialize()
                logger.info("Vertex AI embedding client ready")
            except Exception as exc:
                logger.warning("Failed to initialize Vertex embeddings", error=str(exc))

        # Create handler based on mode
        if USE_MDM_PIPELINE:
            # NEW: MDM Pipeline with deduplication & enrichment
            raw_repo = RawSnapshotRepository(self._db_pool)
            source_link_repo = ProductSourceLinkRepository(self._db_pool)
            audit_repo = EnrichmentAuditRepository(self._db_pool)
            
            refinery = ProductRefinery(
                pool=self._db_pool,
                product_repo=repository,
                raw_repo=raw_repo,
                source_link_repo=source_link_repo,
                audit_repo=audit_repo,
                embedding_client=embedding_client,
                default_category_id=DEFAULT_CATEGORY_ID,
            )
            
            handler = MDMImportHandler(refinery=refinery)
            logger.info("MDM Pipeline handler initialized")
        else:
            # Legacy: Direct import
            handler = RawProductImportHandler(
                repository=repository,
                default_category_id=DEFAULT_CATEGORY_ID,
                embedding_client=embedding_client,
            )
            logger.info("Legacy import handler initialized")

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
    shutdown_event = asyncio.Event()

    # Handle shutdown signals
    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        # Start worker in a task
        worker_task = asyncio.create_task(worker.start())

        # Wait for shutdown signal
        await shutdown_event.wait()

        # Cancel worker task
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

        # Graceful shutdown
        await worker.stop()
    except Exception as e:
        logger.error("Worker failed", error=str(e))
        await worker.stop()
        raise


if __name__ == "__main__":
    asyncio.run(main())
