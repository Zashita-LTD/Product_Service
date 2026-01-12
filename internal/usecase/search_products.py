"""
Search Products Use Case.

Implements full-text search for products with filtering.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from internal.infrastructure.postgres.repository import PostgresProductRepository
from pkg.logger.logger import get_logger


logger = get_logger(__name__)


@dataclass
class SearchProductsInput:
    """Input for SearchProductsUseCase."""
    
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


@dataclass
class SearchProductsOutput:
    """Output for SearchProductsUseCase."""
    
    products: list[dict]
    total: int
    page: int
    per_page: int


class SearchProductsUseCase:
    """
    Use case for full-text search of products.
    
    Performs PostgreSQL full-text search with filtering and pagination.
    """
    
    def __init__(self, repository: PostgresProductRepository):
        """
        Initialize the use case.
        
        Args:
            repository: Product repository.
        """
        self._repository = repository
    
    async def execute(self, input_data: SearchProductsInput) -> SearchProductsOutput:
        """
        Execute the search use case.
        
        Args:
            input_data: Search input with query and filters.
            
        Returns:
            Search results with pagination.
        """
        logger.info(
            "Searching products",
            query=input_data.query,
            category_id=input_data.category_id,
            page=input_data.page,
        )
        
        offset = (input_data.page - 1) * input_data.per_page
        
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
        
        logger.info(
            "Search completed",
            query=input_data.query,
            total=total,
            returned=len(products),
        )
        
        return SearchProductsOutput(
            products=products,
            total=total,
            page=input_data.page,
            per_page=input_data.per_page,
        )
