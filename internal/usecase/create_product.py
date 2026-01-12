"""
Create Product Use Case.

Implements the Outbox Pattern for reliable event publishing.
"""
from typing import Optional, Protocol
from uuid import UUID

from internal.domain.product import ProductFamily, OutboxEvent
from internal.domain.errors import ProductAlreadyExistsError


class ProductRepository(Protocol):
    """Protocol for product repository operations."""

    async def get_by_uuid(self, uuid: UUID) -> Optional[ProductFamily]:
        """Get product by UUID."""
        ...

    async def get_by_name(self, name_technical: str) -> Optional[ProductFamily]:
        """Get product by technical name."""
        ...

    async def create_with_outbox(
        self,
        product: ProductFamily,
        event: OutboxEvent,
    ) -> ProductFamily:
        """Create product with outbox event atomically."""
        ...


class CacheService(Protocol):
    """Protocol for cache operations."""

    async def invalidate_product(self, uuid: str) -> bool:
        """Invalidate cache for a product."""
        ...

    async def invalidate_category(self, category_id: int) -> int:
        """Invalidate all cached products in a category."""
        ...


class CreateProductInput:
    """Input DTO for creating a product."""

    def __init__(
        self,
        name_technical: str,
        category_id: int,
        request_id: Optional[str] = None,
    ) -> None:
        """
        Initialize create product input.

        Args:
            name_technical: Technical name of the product.
            category_id: Category identifier.
            request_id: Optional request ID for idempotency.
        """
        self.name_technical = name_technical
        self.category_id = category_id
        self.request_id = request_id


class CreateProductOutput:
    """Output DTO for created product."""

    def __init__(self, product: ProductFamily) -> None:
        """
        Initialize create product output.

        Args:
            product: The created product family.
        """
        self.product = product

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return self.product.to_dict()


class CreateProductUseCase:
    """
    Use case for creating a new product family.

    Implements the Outbox Pattern to ensure reliable event publishing.
    The product and outbox event are created in a single database transaction.
    """

    def __init__(
        self,
        repository: ProductRepository,
        cache: Optional[CacheService] = None,
    ) -> None:
        """
        Initialize the use case.

        Args:
            repository: Product repository for persistence.
            cache: Optional cache service for invalidation.
        """
        self._repository = repository
        self._cache = cache

    async def execute(self, input_dto: CreateProductInput) -> CreateProductOutput:
        """
        Execute the create product use case.

        This method:
        1. Validates the input
        2. Checks for duplicate products
        3. Creates the product and outbox event atomically
        4. Invalidates relevant cache entries

        Args:
            input_dto: Input data for creating the product.

        Returns:
            CreateProductOutput with the created product.

        Raises:
            ProductAlreadyExistsError: If product with same name exists.
            DomainValidationError: If input validation fails.
        """
        # Check for existing product with same name
        existing = await self._repository.get_by_name(input_dto.name_technical)
        if existing:
            raise ProductAlreadyExistsError(input_dto.name_technical)

        # Create domain entity
        product = ProductFamily(
            name_technical=input_dto.name_technical,
            category_id=input_dto.category_id,
            enrichment_status="pending",
        )

        # Create outbox event for reliable publishing
        outbox_event = OutboxEvent(
            aggregate_type="product_family",
            aggregate_id=product.uuid,
            event_type="product_family.created",
            payload={
                "uuid": str(product.uuid),
                "name_technical": product.name_technical,
                "category_id": product.category_id,
                "created_at": product.created_at.isoformat(),
            },
        )

        # Persist atomically using Outbox Pattern
        created_product = await self._repository.create_with_outbox(
            product=product,
            event=outbox_event,
        )

        # Invalidate cache if service is available
        if self._cache:
            await self._cache.invalidate_product(str(product.uuid))
            await self._cache.invalidate_category(product.category_id)

        return CreateProductOutput(product=created_product)
