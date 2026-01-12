"""
Kafka Consumer for processing events.

Consumes events from Kafka topics for async processing.
"""
import asyncio
import json
from typing import Callable, Awaitable, Optional, Any

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from pkg.logger.logger import get_logger


logger = get_logger(__name__)


MessageHandler = Callable[[dict], Awaitable[None]]


class KafkaConsumer:
    """
    Kafka consumer for processing domain events.
    
    Handles deserialization and reliable processing of events.
    """
    
    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
        client_id: str = "product-service-consumer",
    ) -> None:
        """
        Initialize the Kafka consumer.
        
        Args:
            bootstrap_servers: Comma-separated list of Kafka brokers.
            group_id: Consumer group identifier.
            topics: List of topics to subscribe to.
            client_id: Client identifier for the consumer.
        """
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._topics = topics
        self._client_id = client_id
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._handlers: dict[str, MessageHandler] = {}
        self._running = False
    
    def register_handler(
        self,
        event_type: str,
        handler: MessageHandler,
    ) -> None:
        """
        Register a handler for a specific event type.
        
        Args:
            event_type: The event type to handle.
            handler: Async function to handle the event.
        """
        self._handlers[event_type] = handler
        logger.info("Registered handler for event type", event_type=event_type)
    
    async def start(self) -> None:
        """Start the Kafka consumer."""
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            client_id=self._client_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        await self._consumer.start()
        self._running = True
        logger.info(
            "Kafka consumer started",
            topics=self._topics,
            group_id=self._group_id,
        )
    
    async def stop(self) -> None:
        """Stop the Kafka consumer."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            logger.info("Kafka consumer stopped")
    
    async def consume(self) -> None:
        """
        Start consuming messages.
        
        This is a blocking method that runs until stop() is called.
        """
        if not self._consumer:
            raise RuntimeError("Consumer not started")
        
        try:
            async for msg in self._consumer:
                if not self._running:
                    break
                
                try:
                    await self._process_message(msg)
                    await self._consumer.commit()
                except Exception as e:
                    logger.error(
                        "Error processing message",
                        topic=msg.topic,
                        partition=msg.partition,
                        offset=msg.offset,
                        error=str(e),
                    )
                    # Don't commit on error - message will be reprocessed
        except KafkaError as e:
            logger.error("Kafka consumer error", error=str(e))
            raise
    
    async def _process_message(self, msg: Any) -> None:
        """
        Process a single Kafka message.
        
        Args:
            msg: Kafka message to process.
        """
        value = msg.value
        event_type = value.get("event_type", "unknown")
        
        logger.debug(
            "Received message",
            topic=msg.topic,
            partition=msg.partition,
            offset=msg.offset,
            event_type=event_type,
        )
        
        handler = self._handlers.get(event_type)
        if handler:
            await handler(value)
        else:
            logger.warning(
                "No handler registered for event type",
                event_type=event_type,
            )


class EnrichmentEventHandler:
    """
    Handler for product enrichment events.
    
    Processes product.created events and triggers AI enrichment.
    """
    
    def __init__(self, enrich_use_case) -> None:
        """
        Initialize the handler.
        
        Args:
            enrich_use_case: EnrichProductUseCase instance.
        """
        self._enrich_use_case = enrich_use_case
    
    async def handle(self, event: dict) -> None:
        """
        Handle a product.created event.
        
        Args:
            event: The event data.
        """
        from uuid import UUID
        from internal.usecase.enrich_product import EnrichProductInput
        
        payload = event.get("payload", {})
        product_uuid = payload.get("uuid")
        
        if not product_uuid:
            logger.error("Missing product UUID in event", event=event)
            return
        
        logger.info("Processing enrichment for product", product_uuid=product_uuid)
        
        try:
            input_dto = EnrichProductInput(product_uuid=UUID(product_uuid))
            result = await self._enrich_use_case.execute(input_dto)
            logger.info(
                "Product enriched successfully",
                product_uuid=product_uuid,
                quality_score=float(result.quality_score) if result.quality_score else None,
            )
        except Exception as e:
            logger.error(
                "Failed to enrich product",
                product_uuid=product_uuid,
                error=str(e),
            )
            raise
