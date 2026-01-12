"""
Unit tests for SearchProductsUseCase.
"""
import pytest
from decimal import Decimal
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from internal.usecase.search_products import (
    SearchProductsUseCase,
    SearchProductsInput,
    SearchProductsOutput,
)


class TestSearchProductsUseCase:
    """Tests for SearchProductsUseCase."""
    
    @pytest.mark.asyncio
    async def test_execute_calls_repository_search(self):
        """Test that execute calls repository search method."""
        # Setup
        mock_repository = MagicMock()
        product_uuid = uuid4()
        
        mock_products = [{
            "uuid": product_uuid,
            "name_technical": "Кирпич М150",
            "brand": "ЛСР",
            "sku": "123456",
            "category_id": 10,
            "source_name": "petrovich.ru",
            "enrichment_status": "enriched",
            "quality_score": Decimal("0.85"),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "external_id": "789012",
            "source_url": "https://example.com",
        }]
        
        mock_repository.search = AsyncMock(return_value=(mock_products, 1))
        
        use_case = SearchProductsUseCase(repository=mock_repository)
        
        input_data = SearchProductsInput(
            query="кирпич М150",
            category_id=10,
            page=1,
            per_page=20,
        )
        
        # Execute
        result = await use_case.execute(input_data)
        
        # Assert
        assert isinstance(result, SearchProductsOutput)
        assert len(result.products) == 1
        assert result.total == 1
        assert result.page == 1
        assert result.per_page == 20
        
        # Verify repository was called correctly
        mock_repository.search.assert_called_once()
        call_kwargs = mock_repository.search.call_args.kwargs
        assert call_kwargs["query"] == "кирпич М150"
        assert call_kwargs["category_id"] == 10
        assert call_kwargs["offset"] == 0
        assert call_kwargs["limit"] == 20
    
    @pytest.mark.asyncio
    async def test_execute_with_filters(self):
        """Test execute with various filters applied."""
        mock_repository = MagicMock()
        mock_repository.search = AsyncMock(return_value=([], 0))
        
        use_case = SearchProductsUseCase(repository=mock_repository)
        
        input_data = SearchProductsInput(
            query="кирпич",
            category_id=10,
            brand="ЛСР",
            min_price=Decimal("10.00"),
            max_price=Decimal("50.00"),
            in_stock=True,
            enrichment_status="enriched",
            page=2,
            per_page=10,
        )
        
        result = await use_case.execute(input_data)
        
        # Verify all filters were passed
        call_kwargs = mock_repository.search.call_args.kwargs
        assert call_kwargs["category_id"] == 10
        assert call_kwargs["brand"] == "ЛСР"
        assert call_kwargs["min_price"] == Decimal("10.00")
        assert call_kwargs["max_price"] == Decimal("50.00")
        assert call_kwargs["in_stock"] is True
        assert call_kwargs["enrichment_status"] == "enriched"
        assert call_kwargs["offset"] == 10  # (page 2 - 1) * per_page 10
        assert call_kwargs["limit"] == 10
    
    @pytest.mark.asyncio
    async def test_execute_pagination_offset_calculation(self):
        """Test that pagination offset is calculated correctly."""
        mock_repository = MagicMock()
        mock_repository.search = AsyncMock(return_value=([], 0))
        
        use_case = SearchProductsUseCase(repository=mock_repository)
        
        # Test page 1
        input_data = SearchProductsInput(
            query="test",
            page=1,
            per_page=20,
        )
        await use_case.execute(input_data)
        assert mock_repository.search.call_args.kwargs["offset"] == 0
        
        # Test page 3
        input_data = SearchProductsInput(
            query="test",
            page=3,
            per_page=20,
        )
        await use_case.execute(input_data)
        assert mock_repository.search.call_args.kwargs["offset"] == 40
    
    @pytest.mark.asyncio
    async def test_execute_returns_empty_results(self):
        """Test that execute handles empty search results."""
        mock_repository = MagicMock()
        mock_repository.search = AsyncMock(return_value=([], 0))
        
        use_case = SearchProductsUseCase(repository=mock_repository)
        
        input_data = SearchProductsInput(
            query="nonexistent product",
            page=1,
            per_page=20,
        )
        
        result = await use_case.execute(input_data)
        
        assert len(result.products) == 0
        assert result.total == 0
