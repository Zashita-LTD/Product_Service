"""Semantic search use case powered by pgvector."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Protocol

from internal.infrastructure.postgres.repository import PostgresProductRepository
from internal.usecase.search_products import SearchProductsOutput
from pkg.logger.logger import get_logger

logger = get_logger(__name__)


class EmbeddingClient(Protocol):
    """Protocol describing embedding provider capabilities."""

    @property
    def model_name(self) -> str:  # pragma: no cover - structural typing helper
        ...

    async def generate_embedding(self, text: str) -> list[float]:
        ...


@dataclass
class SemanticSearchInput:
    """Input DTO for semantic search."""

    query: str
    category_id: Optional[int] = None
    brand: Optional[str] = None
    source_name: Optional[str] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    in_stock: Optional[bool] = None
    enrichment_status: Optional[str] = None
    page: int = 1
    per_page: int = 20


class SemanticSearchUseCase:
    """Execute semantic search with graceful degradation."""

    def __init__(
        self,
        repository: PostgresProductRepository,
        embedding_client: Optional[EmbeddingClient] = None,
    ) -> None:
        self._repository = repository
        self._embedding_client = embedding_client

    async def execute(self, input_data: SemanticSearchInput) -> SearchProductsOutput:
        """Perform vector search or fallback to lexical search."""

        offset = (input_data.page - 1) * input_data.per_page

        if not self._embedding_client:
            logger.warning("Semantic search fallback: embedding client missing")
            return await self._fallback(input_data, offset)

        try:
            embedding = await self._embedding_client.generate_embedding(input_data.query)
        except Exception as exc:
            logger.error("Semantic search fallback: embedding failed", error=str(exc))
            return await self._fallback(input_data, offset)

        products, total = await self._repository.semantic_search(
            embedding=embedding,
            category_id=input_data.category_id,
            brand=input_data.brand,
            source_name=input_data.source_name,
            min_price=input_data.min_price,
            max_price=input_data.max_price,
            in_stock=input_data.in_stock,
            enrichment_status=input_data.enrichment_status,
            offset=offset,
            limit=input_data.per_page,
        )

        logger.info(
            "Semantic search executed",
            query=input_data.query,
            model=self._embedding_client.model_name,
            total=total,
        )

        return SearchProductsOutput(
            products=products,
            total=total,
            page=input_data.page,
            per_page=input_data.per_page,
        )

    async def _fallback(
        self,
        input_data: SemanticSearchInput,
        offset: int,
    ) -> SearchProductsOutput:
        """Reuse lexical search when semantic search unavailable."""

        products, total = await self._repository.search(
            query=input_data.query,
            category_id=input_data.category_id,
            brand=input_data.brand,
            source_name=input_data.source_name,
            min_price=input_data.min_price,
            max_price=input_data.max_price,
            in_stock=input_data.in_stock,
            enrichment_status=input_data.enrichment_status,
            offset=offset,
            limit=input_data.per_page,
        )

        return SearchProductsOutput(
            products=products,
            total=total,
            page=input_data.page,
            per_page=input_data.per_page,
        )
