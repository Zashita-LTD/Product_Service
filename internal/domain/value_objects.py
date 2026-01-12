"""
Value Objects for the Product domain.

Value objects are immutable and defined by their attributes.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .errors import DomainValidationError


@dataclass(frozen=True)
class Price:
    """
    Price value object representing a product price.

    Attributes:
        amount: The price amount.
        currency: Currency code (ISO 4217).
        supplier_id: ID of the supplier.
        valid_from: Start of price validity.
        valid_to: End of price validity.
    """
    amount: Decimal
    currency: str = "RUB"
    supplier_id: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate price constraints."""
        if self.amount < 0:
            raise DomainValidationError("Price amount cannot be negative")
        if len(self.currency) != 3:
            raise DomainValidationError("Currency must be a 3-letter ISO code")

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "amount": float(self.amount),
            "currency": self.currency,
            "supplier_id": self.supplier_id,
        }


@dataclass(frozen=True)
class QualityScore:
    """
    Quality Score value object calculated by AI enrichment.

    Score ranges from 0.00 to 1.00 representing the quality level.

    Attributes:
        value: The quality score value (0.00 - 1.00).
    """
    value: Decimal

    def __post_init__(self) -> None:
        """Validate quality score constraints."""
        if not (Decimal("0.00") <= self.value <= Decimal("1.00")):
            raise DomainValidationError("Quality score must be between 0.00 and 1.00")

    @property
    def grade(self) -> str:
        """
        Get grade based on score.

        Returns:
            Grade string: 'A', 'B', 'C', 'D', or 'F'.
        """
        if self.value >= Decimal("0.90"):
            return "A"
        elif self.value >= Decimal("0.80"):
            return "B"
        elif self.value >= Decimal("0.70"):
            return "C"
        elif self.value >= Decimal("0.60"):
            return "D"
        return "F"

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "value": float(self.value),
            "grade": self.grade,
        }


@dataclass(frozen=True)
class CategoryId:
    """
    Category ID value object.

    Attributes:
        value: The category identifier.
    """
    value: int

    def __post_init__(self) -> None:
        """Validate category ID constraints."""
        if self.value <= 0:
            raise DomainValidationError("Category ID must be positive")


@dataclass(frozen=True)
class RequestId:
    """
    Request ID value object for idempotency.

    Attributes:
        value: The unique request identifier.
    """
    value: str

    def __post_init__(self) -> None:
        """Validate request ID constraints."""
        if not self.value:
            raise DomainValidationError("Request ID cannot be empty")
        if len(self.value) > 64:
            raise DomainValidationError("Request ID must be <= 64 characters")
