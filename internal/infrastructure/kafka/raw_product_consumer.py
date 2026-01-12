"""
Kafka Consumer for raw products from Parser Service.

Reads messages from the 'raw-products' topic and imports them into the database.
"""

import json
from typing import Any, Optional
from uuid import uuid4

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from internal.domain.product import OutboxEvent, ProductFamily
from internal.infrastructure.postgres.repository import PostgresProductRepository
from pkg.logger.logger import get_logger

logger = get_logger(__name__)


class RawProductConsumer:
    """
    Kafka consumer for the raw-products topic from Parser Service.

    Handles deserialization and reliable processing of raw product data.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topic: str = "raw-products",
    ) -> None:
        """
        Initialize the raw products consumer.

        Args:
            bootstrap_servers: Comma-separated list of Kafka brokers.
            group_id: Consumer group identifier.
            topic: Topic to consume from (default: 'raw-products').
        """
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._topic = topic
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._handler: Optional["RawProductImportHandler"] = None
        self._running = False
        self._max_retries = 3  # Maximum retries before committing failed message
        self._retry_counts: dict[str, int] = {}  # Track retries per message key

        # Statistics
        self._stats = {
            "imported": 0,
            "duplicates": 0,
            "errors": 0,
            "skipped": 0,  # Messages skipped after max retries
            "total_processed": 0,
        }

    def set_handler(self, handler: "RawProductImportHandler") -> None:
        """
        Set the import handler.

        Args:
            handler: RawProductImportHandler instance.
        """
        self._handler = handler

    async def start(self) -> None:
        """Start the Kafka consumer."""
        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            client_id="product-service-raw-consumer",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        await self._consumer.start()
        self._running = True
        logger.info(
            "Raw products consumer started",
            topic=self._topic,
            group_id=self._group_id,
        )

    async def stop(self) -> None:
        """Stop the Kafka consumer."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            logger.info("Raw products consumer stopped", stats=self._stats)

    async def consume(self) -> None:
        """
        Start consuming messages.

        This is a blocking method that runs until stop() is called.
        """
        if not self._consumer:
            raise RuntimeError("Consumer not started")

        if not self._handler:
            raise RuntimeError("Handler not set")

        try:
            async for msg in self._consumer:
                if not self._running:
                    break

                # Create unique key for retry tracking
                msg_key = f"{msg.topic}:{msg.partition}:{msg.offset}"

                try:
                    result = await self._process_message(msg)

                    # Update statistics
                    self._stats["total_processed"] += 1
                    if result == "imported":
                        self._stats["imported"] += 1
                    elif result == "duplicate":
                        self._stats["duplicates"] += 1
                    elif result == "error":
                        self._stats["errors"] += 1

                    # Log progress every 100 products
                    if self._stats["total_processed"] % 100 == 0:
                        logger.info("Import progress", **self._stats)

                    # Clear retry count on success
                    self._retry_counts.pop(msg_key, None)
                    await self._consumer.commit()
                except Exception as e:
                    # Track retries for this message
                    self._retry_counts[msg_key] = self._retry_counts.get(msg_key, 0) + 1
                    retry_count = self._retry_counts[msg_key]

                    logger.error(
                        "Error processing message",
                        topic=msg.topic,
                        partition=msg.partition,
                        offset=msg.offset,
                        retry=retry_count,
                        max_retries=self._max_retries,
                        error=str(e),
                    )

                    if retry_count >= self._max_retries:
                        # Skip message after max retries to avoid infinite loop
                        logger.warning(
                            "Max retries reached, skipping message",
                            topic=msg.topic,
                            partition=msg.partition,
                            offset=msg.offset,
                            source_url=msg.value.get("source_url") if isinstance(msg.value, dict) else None,
                        )
                        self._stats["skipped"] += 1
                        self._stats["total_processed"] += 1
                        self._retry_counts.pop(msg_key, None)
                        await self._consumer.commit()
                    else:
                        self._stats["errors"] += 1
                        self._stats["total_processed"] += 1
                        # Don't commit - message will be reprocessed on next poll
        except KafkaError as e:
            logger.error("Kafka consumer error", error=str(e))
            raise

    async def _process_message(self, msg: Any) -> str:
        """
        Process a single Kafka message.

        Args:
            msg: Kafka message to process.

        Returns:
            "imported", "duplicate", or "error"
        """
        value = msg.value

        logger.debug(
            "Received raw product",
            topic=msg.topic,
            partition=msg.partition,
            offset=msg.offset,
            source_url=value.get("source_url"),
        )

        return await self._handler.handle(value)


class RawProductImportHandler:
    """
    Handler for importing raw products into the database.

    Handles deduplication, category resolution, and product creation.
    """

    def __init__(
        self,
        repository: PostgresProductRepository,
        default_category_id: int = 1,
    ) -> None:
        """
        Initialize the handler.

        Args:
            repository: PostgresProductRepository instance.
            default_category_id: Default category ID for uncategorized products.
        """
        self._repository = repository
        self._default_category_id = default_category_id

    async def handle(self, raw_product: dict) -> str:
        """
        Handle a raw product import.

        Args:
            raw_product: Raw product data from parser.

        Returns:
            "imported" - product created
            "duplicate" - already exists
            "error" - import failed
        """
        source_url = raw_product.get("source_url")

        # 1. Validate required fields
        if not source_url:
            logger.warning("Missing source_url, skipping", raw_product=raw_product)
            return "error"

        name_original = raw_product.get("name_original")
        if not name_original:
            logger.warning("Missing name_original, skipping", source_url=source_url)
            return "error"

        # 2. Check for duplicate by source_url
        try:
            existing = await self._repository.find_by_source_url(source_url)
            if existing:
                logger.debug("Duplicate product found", source_url=source_url, uuid=existing.uuid)
                return "duplicate"
        except Exception as e:
            logger.error("Error checking duplicate", source_url=source_url, error=str(e))
            return "error"

        # 3. Resolve category from breadcrumbs
        category_id = await self._resolve_category(raw_product.get("category_path", []))

        # 4. Create product with all related data
        try:
            product = await self._create_product(
                name_technical=name_original,
                category_id=category_id,
                source_url=source_url,
                source_name=raw_product.get("source_name"),
                brand=raw_product.get("brand"),
                sku=raw_product.get("sku"),
                external_id=raw_product.get("external_id"),
                description=raw_product.get("description"),
                attributes=raw_product.get("attributes", []),
                documents=raw_product.get("documents", []),
                images=raw_product.get("images", []),
                schema_org_data=raw_product.get("schema_org_data"),
            )

            logger.info(
                "Product imported successfully",
                product_uuid=product.uuid,
                product_name=product.name_technical,
                source_url=source_url,
            )

            return "imported"
        except Exception as e:
            logger.error(
                "Failed to create product",
                source_url=source_url,
                error=str(e),
            )
            return "error"

    async def _resolve_category(self, category_path: list[str]) -> int:
        """
        Resolve category ID from category breadcrumbs.

        For now, returns a default category ID.
        In production, this should map category paths to actual category IDs.

        Args:
            category_path: List of category names (breadcrumbs).

        Returns:
            Category ID.
        """
        # TODO: Implement actual category mapping
        # For now, return the configured default category ID
        if category_path:
            logger.debug("Category path", path=category_path)

        # Return configured default category for uncategorized products
        return self._default_category_id

    async def _create_product(
        self,
        name_technical: str,
        category_id: int,
        source_url: str,
        source_name: Optional[str] = None,
        brand: Optional[str] = None,
        sku: Optional[str] = None,
        external_id: Optional[str] = None,
        description: Optional[str] = None,
        attributes: Optional[list[dict]] = None,
        documents: Optional[list[dict]] = None,
        images: Optional[list[dict]] = None,
        schema_org_data: Optional[dict] = None,
    ) -> ProductFamily:
        """
        Create a product with all related data.

        Args:
            name_technical: Technical name of the product.
            category_id: Category identifier.
            source_url: Original URL from parser.
            source_name: Name of the source.
            brand: Brand/manufacturer name.
            sku: Stock Keeping Unit.
            external_id: External ID from source.
            description: Product description.
            attributes: List of attributes.
            documents: List of documents.
            images: List of images.
            schema_org_data: Schema.org structured data.

        Returns:
            Created ProductFamily.
        """
        # Create product entity
        product = ProductFamily(
            uuid=uuid4(),
            name_technical=name_technical,
            category_id=category_id,
            enrichment_status="pending",
        )

        # Create outbox event for AI enrichment
        event = OutboxEvent(
            aggregate_type="product_family",
            aggregate_id=product.uuid,
            event_type="product_family.created",
            payload={
                "uuid": str(product.uuid),
                "name_technical": product.name_technical,
                "category_id": product.category_id,
                "source": "parser",
            },
        )

        # Create product with all related data in a single transaction
        await self._repository.create_with_outbox(
            product=product,
            event=event,
            source_url=source_url,
            source_name=source_name,
            external_id=external_id,
            sku=sku,
            brand=brand,
            description=description,
            schema_org_data=schema_org_data,
            attributes=attributes,
            documents=documents,
            images=images,
        )

        return product
