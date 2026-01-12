"""
Domain model for Product Family.

This module contains the core domain entities following DDD principles.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from .value_objects import Price, QualityScore
from .errors import DomainValidationError


@dataclass
class ProductFamily:
    """
    ProductFamily is the aggregate root for product-related operations.

    Attributes:
        uuid: Unique identifier for the product family.
        name_technical: Technical name of the product.
        category_id: Category identifier.
        quality_score: Quality score calculated by AI enrichment.
        prices: List of associated prices.
        created_at: Timestamp of creation.
        updated_at: Timestamp of last update.
    """
    uuid: UUID = field(default_factory=uuid4)
    name_technical: str = ""
    category_id: int = 0
    quality_score: Optional[QualityScore] = None
    prices: list[Price] = field(default_factory=list)
    enrichment_status: str = "pending"  # pending, enriched, enrichment_failed
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Validate domain invariants after initialization."""
        self._validate()

    def _validate(self) -> None:
        """
        Validate domain invariants.

        Raises:
            DomainValidationError: If validation fails.
        """
        if not self.name_technical:
            raise DomainValidationError("name_technical is required")
        if len(self.name_technical) > 500:
            raise DomainValidationError("name_technical must be <= 500 characters")
        if self.category_id <= 0:
            raise DomainValidationError("category_id must be positive")

    def enrich(self, quality_score: Decimal, status: str = "enriched") -> None:
        """
        Apply AI enrichment results to the product family.

        Args:
            quality_score: The calculated quality score.
            status: Enrichment status.
        """
        self.quality_score = QualityScore(value=quality_score)
        self.enrichment_status = status
        self.updated_at = datetime.utcnow()

    def mark_enrichment_failed(self) -> None:
        """Mark the enrichment as failed."""
        self.enrichment_status = "enrichment_failed"
        self.updated_at = datetime.utcnow()

    def add_price(self, price: Price) -> None:
        """
        Add a price to the product family.

        Args:
            price: The price to add.
        """
        self.prices.append(price)
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict:
        """
        Convert to dictionary representation.

        Returns:
            Dictionary with all product family data.
        """
        return {
            "uuid": str(self.uuid),
            "name_technical": self.name_technical,
            "category_id": self.category_id,
            "quality_score": float(self.quality_score.value) if self.quality_score else None,
            "enrichment_status": self.enrichment_status,
            "prices": [p.to_dict() for p in self.prices],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class OutboxEvent:
    """
    Outbox event for reliable event publishing.

    Implements the Outbox Pattern for guaranteed event delivery.

    Attributes:
        id: Event identifier.
        aggregate_type: Type of aggregate (e.g., 'product_family').
        aggregate_id: ID of the aggregate.
        event_type: Type of event (e.g., 'created', 'enriched').
        payload: JSON payload of the event.
        created_at: Timestamp of creation.
        processed_at: Timestamp when event was processed.
    """
    id: int = 0
    aggregate_type: str = "product_family"
    aggregate_id: UUID = field(default_factory=uuid4)
    event_type: str = ""
    payload: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None

    def mark_processed(self) -> None:
        """Mark the event as processed."""
        self.processed_at = datetime.utcnow()

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": str(self.aggregate_id),
            "event_type": self.event_type,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }
