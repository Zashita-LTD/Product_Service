"""
Kafka Producer for event publishing.

Publishes domain events to Kafka topics for async processing.
"""
import json
from typing import Optional, Callable, Any
from dataclasses import asdict

from aiokafka import AIOKafkaProducer

from internal.domain.product import OutboxEvent
from pkg.logger.logger import get_logger


logger = get_logger(__name__)


class KafkaProducer:
    """
    Kafka producer for publishing domain events.

    Handles serialization and reliable delivery of events.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        client_id: str = "product-service",
    ) -> None:
        """
        Initialize the Kafka producer.

        Args:
            bootstrap_servers: Comma-separated list of Kafka brokers.
            client_id: Client identifier for the producer.
        """
        self._bootstrap_servers = bootstrap_servers
        self._client_id = client_id
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self) -> None:
        """Start the Kafka producer."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            client_id=self._client_id,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
        )
        await self._producer.start()
        logger.info("Kafka producer started", bootstrap_servers=self._bootstrap_servers)

    async def stop(self) -> None:
        """Stop the Kafka producer."""
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka producer stopped")

    async def publish_event(
        self,
        topic: str,
        event: OutboxEvent,
    ) -> None:
        """
        Publish an outbox event to Kafka.

        Args:
            topic: The Kafka topic to publish to.
            event: The outbox event to publish.
        """
        if not self._producer:
            raise RuntimeError("Producer not started")

        key = f"{event.aggregate_type}:{event.aggregate_id}"
        value = {
            "event_type": event.event_type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id),
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        }

        await self._producer.send_and_wait(
            topic=topic,
            key=key,
            value=value,
        )

        logger.info(
            "Event published to Kafka",
            topic=topic,
            event_type=event.event_type,
            aggregate_id=str(event.aggregate_id),
        )

    async def publish_message(
        self,
        topic: str,
        key: str,
        value: dict,
    ) -> None:
        """
        Publish a generic message to Kafka.

        Args:
            topic: The Kafka topic to publish to.
            key: Message key.
            value: Message value as dictionary.
        """
        if not self._producer:
            raise RuntimeError("Producer not started")

        await self._producer.send_and_wait(
            topic=topic,
            key=key,
            value=value,
        )

        logger.debug("Message published to Kafka", topic=topic, key=key)


class OutboxPublisher:
    """
    Outbox event publisher.

    Polls the outbox table and publishes events to Kafka.
    """

    def __init__(
        self,
        producer: KafkaProducer,
        repository,  # PostgresProductRepository
        topic: str = "product-events",
        batch_size: int = 100,
    ) -> None:
        """
        Initialize the outbox publisher.

        Args:
            producer: Kafka producer instance.
            repository: Product repository for outbox events.
            topic: Kafka topic for product events.
            batch_size: Number of events to process per batch.
        """
        self._producer = producer
        self._repository = repository
        self._topic = topic
        self._batch_size = batch_size

    async def publish_pending_events(self) -> int:
        """
        Publish all pending outbox events.

        Returns:
            Number of events published.
        """
        events = await self._repository.get_unprocessed_outbox_events(
            limit=self._batch_size
        )

        published_count = 0
        for event in events:
            try:
                await self._producer.publish_event(
                    topic=self._topic,
                    event=event,
                )
                await self._repository.mark_event_processed(event.id)
                published_count += 1
            except Exception as e:
                logger.error(
                    "Failed to publish outbox event",
                    event_id=event.id,
                    error=str(e),
                )
                # Continue with other events
                continue

        if published_count > 0:
            logger.info(
                "Published outbox events",
                count=published_count,
                total=len(events),
            )

        return published_count
