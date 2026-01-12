"""
Unit tests for new product API endpoints.
"""
import pytest
from decimal import Decimal
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from internal.transport.http.v1.handlers import (
    router,
    set_dependencies,
    _build_product_list_item,
    _build_category_dto,
)
from internal.usecase.search_products import SearchProductsUseCase
from internal.usecase.create_product import CreateProductUseCase
from internal.usecase.enrich_product import EnrichProductUseCase


class TestProductListEndpoint:
    """Tests for GET /api/v1/products endpoint."""
    
    @pytest.mark.asyncio
    async def test_list_products_returns_paginated_response(self, mock_repository):
        """Test that listing products returns paginated response."""
        # Setup
        product_uuid = uuid4()
        mock_data = [{
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
        
        mock_repository.list_products = AsyncMock(return_value=(mock_data, 1))
        
        # Setup dependencies
        create_use_case = MagicMock(spec=CreateProductUseCase)
        enrich_use_case = MagicMock(spec=EnrichProductUseCase)
        search_use_case = MagicMock(spec=SearchProductsUseCase)
        
        set_dependencies(
            create_use_case=create_use_case,
            enrich_use_case=enrich_use_case,
            search_use_case=search_use_case,
            repository=mock_repository,
        )
        
        # Create test client
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/products")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["name_technical"] == "Кирпич М150"
        assert data["pagination"]["total_items"] == 1
    
    @pytest.mark.asyncio
    async def test_list_products_with_filters(self, mock_repository):
        """Test listing products with filters applied."""
        mock_repository.list_products = AsyncMock(return_value=([], 0))
        
        # Setup dependencies
        create_use_case = MagicMock(spec=CreateProductUseCase)
        enrich_use_case = MagicMock(spec=EnrichProductUseCase)
        search_use_case = MagicMock(spec=SearchProductsUseCase)
        
        set_dependencies(
            create_use_case=create_use_case,
            enrich_use_case=enrich_use_case,
            search_use_case=search_use_case,
            repository=mock_repository,
        )
        
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/products",
                params={
                    "category_id": 10,
                    "brand": "ЛСР",
                    "min_price": "10.00",
                    "max_price": "50.00",
                    "in_stock": True,
                }
            )
        
        assert response.status_code == 200
        # Verify filters were passed to repository
        mock_repository.list_products.assert_called_once()
        call_kwargs = mock_repository.list_products.call_args.kwargs
        assert call_kwargs["category_id"] == 10
        assert call_kwargs["brand"] == "ЛСР"


class TestProductDetailEndpoint:
    """Tests for GET /api/v1/products/{uuid} endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_product_details_returns_full_data(self, mock_repository):
        """Test that product details endpoint returns full product data."""
        product_uuid = uuid4()
        mock_data = {
            "product": {
                "uuid": product_uuid,
                "name_technical": "Кирпич керамический М150",
                "brand": "ЛСР",
                "sku": "123456",
                "description": "Керамический кирпич...",
                "category_id": 10,
                "source_name": "petrovich.ru",
                "source_url": "https://moscow.petrovich.ru/product/...",
                "external_id": "789012",
                "enrichment_status": "enriched",
                "quality_score": Decimal("0.85"),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
            "attributes": [
                {"name": "Марка прочности", "value": "М150", "unit": None},
                {"name": "Вес", "value": "3.5", "unit": "кг"},
            ],
            "images": [
                {
                    "url": "https://example.com/image.jpg",
                    "alt_text": "Кирпич М150",
                    "is_main": True,
                    "sort_order": 0,
                }
            ],
            "documents": [
                {
                    "document_type": "certificate",
                    "title": "Сертификат соответствия",
                    "url": "https://example.com/cert.pdf",
                    "format": "pdf",
                }
            ],
            "price": {
                "amount": Decimal("15.50"),
                "currency": "RUB",
            },
            "inventory": {
                "total_quantity": Decimal("5000"),
                "in_stock": True,
            },
        }
        
        mock_repository.get_product_with_details = AsyncMock(return_value=mock_data)
        
        # Setup dependencies
        create_use_case = MagicMock(spec=CreateProductUseCase)
        enrich_use_case = MagicMock(spec=EnrichProductUseCase)
        search_use_case = MagicMock(spec=SearchProductsUseCase)
        
        set_dependencies(
            create_use_case=create_use_case,
            enrich_use_case=enrich_use_case,
            search_use_case=search_use_case,
            repository=mock_repository,
        )
        
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/products/{product_uuid}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name_technical"] == "Кирпич керамический М150"
        assert data["brand"] == "ЛСР"
        assert len(data["attributes"]) == 2
        assert len(data["images"]) == 1
        assert len(data["documents"]) == 1
        assert data["price"]["value"] == "15.50"
    
    @pytest.mark.asyncio
    async def test_get_product_details_not_found(self, mock_repository):
        """Test that non-existent product returns 404."""
        product_uuid = uuid4()
        mock_repository.get_product_with_details = AsyncMock(return_value=None)
        
        # Setup dependencies
        create_use_case = MagicMock(spec=CreateProductUseCase)
        enrich_use_case = MagicMock(spec=EnrichProductUseCase)
        search_use_case = MagicMock(spec=SearchProductsUseCase)
        
        set_dependencies(
            create_use_case=create_use_case,
            enrich_use_case=enrich_use_case,
            search_use_case=search_use_case,
            repository=mock_repository,
        )
        
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/products/{product_uuid}")
        
        assert response.status_code == 404


class TestSearchEndpoint:
    """Tests for POST /api/v1/products/search endpoint."""
    
    @pytest.mark.asyncio
    async def test_search_products_returns_results(self, mock_search_use_case):
        """Test that search returns matching products."""
        from internal.usecase.search_products import SearchProductsOutput
        
        product_uuid = uuid4()
        mock_products = [{
            "uuid": product_uuid,
            "name_technical": "Кирпич керамический М150",
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
        
        mock_output = SearchProductsOutput(
            products=mock_products,
            total=1,
            page=1,
            per_page=20,
        )
        
        mock_search_use_case.execute = AsyncMock(return_value=mock_output)
        
        # Setup dependencies
        create_use_case = MagicMock(spec=CreateProductUseCase)
        enrich_use_case = MagicMock(spec=EnrichProductUseCase)
        mock_repository = MagicMock()
        
        set_dependencies(
            create_use_case=create_use_case,
            enrich_use_case=enrich_use_case,
            search_use_case=mock_search_use_case,
            repository=mock_repository,
        )
        
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/products/search",
                json={
                    "query": "кирпич керамический М150",
                    "filters": {
                        "category_id": 10,
                        "min_price": "10.00",
                        "max_price": "50.00",
                    },
                    "page": 1,
                    "per_page": 20,
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["name_technical"] == "Кирпич керамический М150"


class TestCategoriesEndpoint:
    """Tests for GET /api/v1/categories endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_categories_returns_tree(self):
        """Test that categories endpoint returns hierarchical structure."""
        # Setup dependencies
        create_use_case = MagicMock(spec=CreateProductUseCase)
        enrich_use_case = MagicMock(spec=EnrichProductUseCase)
        search_use_case = MagicMock(spec=SearchProductsUseCase)
        mock_repository = MagicMock()
        
        set_dependencies(
            create_use_case=create_use_case,
            enrich_use_case=enrich_use_case,
            search_use_case=search_use_case,
            repository=mock_repository,
        )
        
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/categories")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)


class TestCategoryProductsEndpoint:
    """Tests for GET /api/v1/categories/{id}/products endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_category_products(self, mock_repository):
        """Test getting products for a specific category."""
        mock_repository.list_products = AsyncMock(return_value=([], 0))
        
        # Setup dependencies
        create_use_case = MagicMock(spec=CreateProductUseCase)
        enrich_use_case = MagicMock(spec=EnrichProductUseCase)
        search_use_case = MagicMock(spec=SearchProductsUseCase)
        
        set_dependencies(
            create_use_case=create_use_case,
            enrich_use_case=enrich_use_case,
            search_use_case=search_use_case,
            repository=mock_repository,
        )
        
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/categories/10/products")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data
        
        # Verify category_id filter was applied
        mock_repository.list_products.assert_called_once()
        call_kwargs = mock_repository.list_products.call_args.kwargs
        assert call_kwargs["category_id"] == 10


# Fixtures
@pytest.fixture
def mock_repository():
    """Create a mock repository."""
    return MagicMock()


@pytest.fixture
def mock_search_use_case():
    """Create a mock search use case."""
    return MagicMock(spec=SearchProductsUseCase)


class TestHelperFunctions:
    """Tests for helper functions."""
    
    def test_build_category_dto(self):
        """Test building category DTO."""
        category = _build_category_dto(10)
        assert category.id == 10
        assert category.name == "Category 10"
        assert len(category.path) > 0
    
    def test_build_product_list_item(self):
        """Test building product list item DTO."""
        product_uuid = uuid4()
        row = {
            "uuid": product_uuid,
            "name_technical": "Кирпич М150",
            "brand": "ЛСР",
            "sku": "123456",
            "category_id": 10,
            "source_name": "petrovich.ru",
            "enrichment_status": "enriched",
            "quality_score": Decimal("0.85"),
            "created_at": datetime.utcnow(),
        }
        
        item = _build_product_list_item(row)
        assert item.uuid == product_uuid
        assert item.name_technical == "Кирпич М150"
        assert item.brand == "ЛСР"
        assert item.quality_score == 0.85
