"""
Enrich Product Use Case.

Handles AI enrichment of product families using Google Vertex AI.
"""
from decimal import Decimal
from typing import Optional, Protocol
from uuid import UUID

from internal.domain.product import ProductFamily
from internal.domain.errors import ProductNotFoundError, EnrichmentError


class ProductRepository(Protocol):
    """Protocol for product repository operations."""
    
    async def get_by_uuid(self, uuid: UUID) -> Optional[ProductFamily]:
        """Get product by UUID."""
        ...
    
    async def update(self, product: ProductFamily) -> ProductFamily:
        """Update product."""
        ...


class AIProvider(Protocol):
    """Protocol for AI provider operations."""
    
    async def calculate_quality_score(
        self,
        name_technical: str,
        category_id: int,
    ) -> Decimal:
        """Calculate quality score using AI."""
        ...


class CacheService(Protocol):
    """Protocol for cache operations."""
    
    async def invalidate(self, key: str) -> None:
        """Invalidate cache key."""
        ...
    
    async def set(self, key: str, value: dict, ttl: int) -> None:
        """Set cache value."""
        ...


class EnrichProductInput:
    """Input DTO for enriching a product."""
    
    def __init__(self, product_uuid: UUID) -> None:
        """
        Initialize enrich product input.
        
        Args:
            product_uuid: UUID of the product to enrich.
        """
        self.product_uuid = product_uuid


class EnrichProductOutput:
    """Output DTO for enriched product."""
    
    def __init__(
        self,
        product: ProductFamily,
        quality_score: Optional[Decimal] = None,
        status: str = "enriched",
    ) -> None:
        """
        Initialize enrich product output.
        
        Args:
            product: The enriched product family.
            quality_score: The calculated quality score.
            status: Enrichment status.
        """
        self.product = product
        self.quality_score = quality_score
        self.status = status
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            **self.product.to_dict(),
            "enrichment_result": {
                "quality_score": float(self.quality_score) if self.quality_score else None,
                "status": self.status,
            },
        }


class EnrichProductUseCase:
    """
    Use case for enriching a product family with AI.
    
    Uses Google Vertex AI to calculate quality scores and other
    enrichment data. Implements graceful degradation with Circuit Breaker.
    """
    
    def __init__(
        self,
        repository: ProductRepository,
        ai_provider: AIProvider,
        cache: Optional[CacheService] = None,
    ) -> None:
        """
        Initialize the use case.
        
        Args:
            repository: Product repository for persistence.
            ai_provider: AI provider for enrichment.
            cache: Optional cache service for caching results.
        """
        self._repository = repository
        self._ai_provider = ai_provider
        self._cache = cache
    
    async def execute(self, input_dto: EnrichProductInput) -> EnrichProductOutput:
        """
        Execute the enrich product use case.
        
        This method:
        1. Retrieves the product
        2. Calls AI provider to calculate quality score
        3. Updates the product with enrichment data
        4. Updates cache with new data
        
        Args:
            input_dto: Input data for enriching the product.
            
        Returns:
            EnrichProductOutput with the enriched product.
            
        Raises:
            ProductNotFoundError: If product doesn't exist.
            EnrichmentError: If AI enrichment fails.
        """
        # Retrieve the product
        product = await self._repository.get_by_uuid(input_dto.product_uuid)
        if not product:
            raise ProductNotFoundError(str(input_dto.product_uuid))
        
        try:
            # Calculate quality score using AI
            quality_score = await self._ai_provider.calculate_quality_score(
                name_technical=product.name_technical,
                category_id=product.category_id,
            )
            
            # Update product with enrichment data
            product.enrich(quality_score=quality_score, status="enriched")
            
            # Persist changes
            updated_product = await self._repository.update(product)
            
            # Update cache with enriched data
            if self._cache:
                cache_key = f"product:fam:{product.uuid}:full"
                await self._cache.set(cache_key, updated_product.to_dict(), ttl=600)
            
            return EnrichProductOutput(
                product=updated_product,
                quality_score=quality_score,
                status="enriched",
            )
            
        except Exception as e:
            # Mark enrichment as failed
            product.mark_enrichment_failed()
            await self._repository.update(product)
            
            # Re-raise as domain error
            raise EnrichmentError(
                product_id=str(input_dto.product_uuid),
                reason=str(e),
            )
