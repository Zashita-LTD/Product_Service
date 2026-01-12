"""
AI Enrichment Worker Entry Point.

Consumes product creation events and triggers AI enrichment.
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
from internal.infrastructure.kafka.consumer import KafkaConsumer, EnrichmentEventHandler
from internal.infrastructure.ai_provider.vertex_client import VertexAIClientWithFallback
from internal.usecase.enrich_product import EnrichProductUseCase
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
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "product-enrichment-worker")
KAFKA_TOPICS = os.getenv("KAFKA_TOPICS", "product-events").split(",")
VERTEX_PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")


class EnrichmentWorker:
    """
    Worker for processing product enrichment events.
    
    Consumes events from Kafka and triggers AI enrichment.
    """
    
    def __init__(self) -> None:
        """Initialize the worker."""
        self._running = False
        self._db_pool = None
        self._redis_cache: Optional[RedisCache] = None
        self._consumer: Optional[KafkaConsumer] = None
        self._ai_client: Optional[VertexAIClientWithFallback] = None
    
    async def start(self) -> None:
        """Start the worker."""
        logger.info("Starting Enrichment Worker...")
        
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
        
        # Initialize AI client
        if VERTEX_PROJECT_ID:
            try:
                self._ai_client = VertexAIClientWithFallback(
                    project_id=VERTEX_PROJECT_ID,
                    location=VERTEX_LOCATION,
                )
                await self._ai_client.initialize()
                logger.info("Vertex AI client initialized")
            except Exception as e:
                logger.error("Failed to initialize Vertex AI", error=str(e))
                raise
        else:
            logger.error("VERTEX_PROJECT_ID not set")
            raise ValueError("VERTEX_PROJECT_ID is required for enrichment worker")
        
        # Create repository and services
        repository = PostgresProductRepository(self._db_pool)
        cache_service = ProductCacheService(self._redis_cache) if self._redis_cache else None
        
        # Create use case
        enrich_use_case = EnrichProductUseCase(
            repository=repository,
            ai_provider=self._ai_client,
            cache=cache_service,
        )
        
        # Create event handler
        handler = EnrichmentEventHandler(enrich_use_case)
        
        # Initialize Kafka consumer
        self._consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=KAFKA_GROUP_ID,
            topics=KAFKA_TOPICS,
            client_id="product-enrichment-worker",
        )
        
        # Register handlers
        self._consumer.register_handler(
            "product_family.created",
            handler.handle,
        )
        
        # Start consumer
        await self._consumer.start()
        
        logger.info("Enrichment Worker started successfully")
        
        # Start consuming
        try:
            await self._consumer.consume()
        except asyncio.CancelledError:
            logger.info("Worker consumption cancelled")
    
    async def stop(self) -> None:
        """Stop the worker."""
        logger.info("Stopping Enrichment Worker...")
        
        self._running = False
        
        if self._consumer:
            await self._consumer.stop()
        
        if self._redis_cache:
            await self._redis_cache.disconnect()
        
        if self._db_pool:
            await self._db_pool.close()
        
        logger.info("Enrichment Worker stopped")


async def main() -> None:
    """Main entry point."""
    worker = EnrichmentWorker()
    
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
