"""
Unit tests for raw product consumer.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from internal.infrastructure.kafka.raw_product_consumer import (
    RawProductImportHandler,
    RawProductConsumer,
)


class TestRawProductImportHandler:
    """Tests for RawProductImportHandler."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock repository."""
        from internal.domain.product import ProductFamily

        repo = MagicMock()
        repo.find_by_source_url = AsyncMock(return_value=None)

        # Mock create_with_outbox to return a product
        async def mock_create(product, event, **kwargs):
            return product

        repo.create_with_outbox = AsyncMock(side_effect=mock_create)
        return repo

    @pytest.fixture
    def handler(self, mock_repository):
        """Create a handler instance with mock repository."""
        return RawProductImportHandler(repository=mock_repository)

    @pytest.fixture
    def valid_raw_product(self):
        """Sample valid raw product data."""
        return {
            "source_url": "https://example.com/product/123",
            "source_name": "Example Store",
            "name_original": "Test Product Name",
            "brand": "Test Brand",
            "sku": "SKU-123",
            "category_path": ["Category 1", "Category 2"],
            "attributes": [
                {"name": "Color", "value": "Red", "unit": None},
                {"name": "Weight", "value": "5", "unit": "kg"},
            ],
            "documents": [
                {
                    "document_type": "certificate",
                    "title": "Test Certificate",
                    "url": "https://example.com/cert.pdf",
                    "format": "pdf",
                }
            ],
            "images": [
                {
                    "url": "https://example.com/image.jpg",
                    "alt_text": "Product image",
                    "is_main": True,
                    "sort_order": 0,
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_handle_valid_product_imports_successfully(
        self, handler, mock_repository, valid_raw_product
    ):
        """Test that a valid product is imported successfully."""
        result = await handler.handle(valid_raw_product)

        assert result == "imported"
        mock_repository.find_by_source_url.assert_called_once_with(
            "https://example.com/product/123"
        )

    @pytest.mark.asyncio
    async def test_handle_missing_source_url_returns_error(self, handler):
        """Test that missing source_url returns error."""
        raw_product = {"name_original": "Test Product"}

        result = await handler.handle(raw_product)

        assert result == "error"

    @pytest.mark.asyncio
    async def test_handle_missing_name_returns_error(self, handler):
        """Test that missing name_original returns error."""
        raw_product = {"source_url": "https://example.com/product/123"}

        result = await handler.handle(raw_product)

        assert result == "error"

    @pytest.mark.asyncio
    async def test_handle_duplicate_product_returns_duplicate(
        self, handler, mock_repository, valid_raw_product
    ):
        """Test that duplicate product is detected."""
        # Mock repository to return an existing product
        from internal.domain.product import ProductFamily

        existing_product = ProductFamily(
            uuid=uuid4(),
            name_technical="Existing Product",
            category_id=1,
        )
        mock_repository.find_by_source_url.return_value = existing_product

        result = await handler.handle(valid_raw_product)

        assert result == "duplicate"
        mock_repository.create_with_outbox.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_repository_error_returns_error(
        self, handler, mock_repository, valid_raw_product
    ):
        """Test that repository errors are handled."""
        mock_repository.create_with_outbox.side_effect = Exception("Database error")

        result = await handler.handle(valid_raw_product)

        assert result == "error"


class TestRawProductConsumer:
    """Tests for RawProductConsumer."""

    @pytest.fixture
    def consumer(self):
        """Create a consumer instance."""
        return RawProductConsumer(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            topic="raw-products",
        )

    def test_consumer_initialization(self, consumer):
        """Test consumer is initialized correctly."""
        assert consumer._bootstrap_servers == "localhost:9092"
        assert consumer._group_id == "test-group"
        assert consumer._topic == "raw-products"
        assert consumer._stats["imported"] == 0
        assert consumer._stats["duplicates"] == 0
        assert consumer._stats["errors"] == 0
        assert consumer._stats["skipped"] == 0
        assert consumer._max_retries == 3

    def test_set_handler(self, consumer):
        """Test setting handler."""
        handler = MagicMock()
        consumer.set_handler(handler)

        assert consumer._handler == handler
