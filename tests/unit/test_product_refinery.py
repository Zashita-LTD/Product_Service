"""
Tests for ProductRefinery MDM Pipeline.

Tests the core MDM logic:
- Raw snapshot saving
- Deduplication strategies (EAN, SKU+Brand, Vector)
- Data merging from multiple sources
- Manufacturer linking
"""
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from internal.infrastructure.postgres.raw_repository import (
    RawProductSnapshot,
    RawSnapshotRepository,
    ProductSourceLinkRepository,
    EnrichmentAuditRepository,
)
from internal.usecase.product_refinery import (
    ProductRefinery,
    DeduplicationStrategy,
    DataMerger,
    ManufacturerLinker,
    RefineryResult,
)
from internal.domain.product import ProductFamily
from internal.domain.value_objects import QualityScore


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_pool():
    """Create mock database pool."""
    pool = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.fixture
def mock_product_repo():
    """Create mock product repository."""
    repo = AsyncMock()
    repo.get_by_uuid = AsyncMock(return_value=None)
    repo.find_by_source_url = AsyncMock(return_value=None)
    repo.get_by_name = AsyncMock(return_value=None)
    repo.create_with_outbox = AsyncMock()
    repo.upsert_embedding = AsyncMock()
    repo.semantic_search = AsyncMock(return_value=([], 0))
    return repo


@pytest.fixture
def mock_raw_repo():
    """Create mock raw snapshot repository."""
    repo = AsyncMock()
    repo.save_snapshot = AsyncMock()
    repo.find_by_content_hash = AsyncMock(return_value=None)
    repo.find_by_ean = AsyncMock(return_value=[])
    repo.find_by_sku_and_brand = AsyncMock(return_value=[])
    repo.mark_processed = AsyncMock()
    return repo


@pytest.fixture
def mock_source_link_repo():
    """Create mock source link repository."""
    repo = AsyncMock()
    repo.find_product_by_source = AsyncMock(return_value=None)
    repo.create_link = AsyncMock()
    return repo


@pytest.fixture
def mock_audit_repo():
    """Create mock audit repository."""
    repo = AsyncMock()
    repo.log_action = AsyncMock(return_value=1)
    return repo


@pytest.fixture
def mock_embedding_client():
    """Create mock embedding client."""
    client = AsyncMock()
    client.model_name = "text-embedding-004"
    client.generate_embedding = AsyncMock(return_value=[0.1] * 768)
    return client


@pytest.fixture
def sample_raw_data():
    """Sample raw product data from parser."""
    return {
        "id": "ext-123",
        "source_url": "https://petrovich.ru/product/123",
        "name_original": "Штукатурка гипсовая Ротбанд 30 кг",
        "brand": "Knauf",
        "category_breadcrumbs": ["Строительные материалы", "Штукатурка"],
        "attributes": [
            {"name": "Вес", "value": "30", "unit": "кг"},
            {"name": "EAN", "value": "4607026710047"},
            {"name": "Артикул", "value": "ROT-30"},
        ],
        "images": [
            "https://cdn.petrovich.ru/img1.jpg",
            "https://cdn.petrovich.ru/img2.jpg",
        ],
        "documents": [
            {"url": "https://cdn.petrovich.ru/doc.pdf", "title": "Инструкция"},
        ],
        "price_amount": 450.0,
        "price_currency": "RUB",
        "description": "Универсальная гипсовая штукатурка для стен и потолков",
    }


@pytest.fixture
def sample_snapshot(sample_raw_data):
    """Sample RawProductSnapshot."""
    return RawProductSnapshot(
        id=uuid4(),
        source_name="petrovich",
        source_url=sample_raw_data["source_url"],
        external_id="ext-123",
        raw_data=sample_raw_data,
        content_hash="abc123",
        extracted_ean="4607026710047",
        extracted_sku="ROT-30",
        extracted_brand="Knauf",
        processed=False,
    )


@pytest.fixture
def existing_product():
    """Existing product in database."""
    return ProductFamily(
        uuid=uuid4(),
        name_technical="Knauf Ротбанд",
        category_id=1,
        quality_score=QualityScore(value=Decimal("0.5")),
        enrichment_status="pending",
    )


# ============================================================================
# RAW SNAPSHOT REPOSITORY TESTS
# ============================================================================

class TestRawSnapshotExtraction:
    """Test data extraction from raw data."""

    def test_extract_ean_from_attributes(self):
        """EAN should be extracted from attributes."""
        raw_data = {
            "attributes": [
                {"name": "Штрих-код", "value": "4607026710047"},
            ]
        }
        ean = RawSnapshotRepository.extract_ean(raw_data)
        assert ean == "4607026710047"

    def test_extract_ean_from_schema_org(self):
        """EAN should be extracted from schema.org data."""
        raw_data = {
            "schema_org_data": {"gtin13": "4607026710047"},
        }
        ean = RawSnapshotRepository.extract_ean(raw_data)
        assert ean == "4607026710047"

    def test_extract_ean_direct(self):
        """EAN should be extracted from direct field."""
        raw_data = {"ean": "4607026710047"}
        ean = RawSnapshotRepository.extract_ean(raw_data)
        assert ean == "4607026710047"

    def test_extract_brand_from_direct(self):
        """Brand should be extracted from direct field."""
        raw_data = {"brand": "Knauf"}
        brand = RawSnapshotRepository.extract_brand(raw_data)
        assert brand == "Knauf"

    def test_extract_brand_from_schema_org(self):
        """Brand should be extracted from schema.org."""
        raw_data = {"schema_org_data": {"brand": {"name": "Bosch"}}}
        brand = RawSnapshotRepository.extract_brand(raw_data)
        assert brand == "Bosch"

    def test_extract_sku_from_attributes(self):
        """SKU should be extracted from attributes."""
        raw_data = {
            "attributes": [
                {"name": "Артикул производителя", "value": "ROT-30"},
            ]
        }
        sku = RawSnapshotRepository.extract_sku(raw_data)
        assert sku == "ROT-30"

    def test_extract_source_name(self):
        """Source name should be extracted from URL."""
        assert RawSnapshotRepository.extract_source_name(
            "https://petrovich.ru/product/123"
        ) == "petrovich"
        assert RawSnapshotRepository.extract_source_name(
            "https://leroymerlin.ru/product/456"
        ) == "leroy"
        assert RawSnapshotRepository.extract_source_name(
            "https://unknown-shop.com/item"
        ) == "unknown-shop"

    def test_compute_content_hash(self):
        """Content hash should be deterministic."""
        raw_data = {"name": "Test", "price": 100}
        hash1 = RawSnapshotRepository.compute_content_hash(raw_data)
        hash2 = RawSnapshotRepository.compute_content_hash(raw_data)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256


# ============================================================================
# DEDUPLICATION STRATEGY TESTS
# ============================================================================

class TestDeduplicationStrategy:
    """Test deduplication strategies."""

    @pytest.mark.asyncio
    async def test_find_duplicate_by_url(
        self,
        mock_product_repo,
        mock_raw_repo,
        mock_source_link_repo,
        existing_product,
        sample_snapshot,
    ):
        """Duplicate should be found by exact URL match."""
        mock_source_link_repo.find_product_by_source.return_value = existing_product.uuid
        mock_product_repo.get_by_uuid.return_value = existing_product

        strategy = DeduplicationStrategy(
            product_repo=mock_product_repo,
            raw_repo=mock_raw_repo,
            source_link_repo=mock_source_link_repo,
        )

        product, confidence, method = await strategy.find_duplicate(sample_snapshot)

        assert product == existing_product
        assert confidence == 1.0
        assert method == "url_match"

    @pytest.mark.asyncio
    async def test_find_duplicate_by_ean(
        self,
        mock_product_repo,
        mock_raw_repo,
        mock_source_link_repo,
        existing_product,
        sample_snapshot,
    ):
        """Duplicate should be found by EAN."""
        mock_source_link_repo.find_product_by_source.return_value = None
        
        # Create snapshot with linked product
        linked_snapshot = RawProductSnapshot(
            id=uuid4(),
            source_name="leroy",
            source_url="https://leroy.ru/product/456",
            raw_data={},
            extracted_ean=sample_snapshot.extracted_ean,
            linked_product_uuid=existing_product.uuid,
        )
        mock_raw_repo.find_by_ean.return_value = [linked_snapshot]
        mock_product_repo.get_by_uuid.return_value = existing_product

        strategy = DeduplicationStrategy(
            product_repo=mock_product_repo,
            raw_repo=mock_raw_repo,
            source_link_repo=mock_source_link_repo,
        )

        product, confidence, method = await strategy.find_duplicate(sample_snapshot)

        assert product == existing_product
        assert confidence == 0.99
        assert method == "ean_match"

    @pytest.mark.asyncio
    async def test_find_duplicate_by_sku_brand(
        self,
        mock_product_repo,
        mock_raw_repo,
        mock_source_link_repo,
        existing_product,
        sample_snapshot,
    ):
        """Duplicate should be found by SKU + Brand."""
        mock_source_link_repo.find_product_by_source.return_value = None
        mock_raw_repo.find_by_ean.return_value = []
        
        linked_snapshot = RawProductSnapshot(
            id=uuid4(),
            source_name="obi",
            source_url="https://obi.ru/product/789",
            raw_data={},
            extracted_sku=sample_snapshot.extracted_sku,
            extracted_brand=sample_snapshot.extracted_brand,
            linked_product_uuid=existing_product.uuid,
        )
        mock_raw_repo.find_by_sku_and_brand.return_value = [linked_snapshot]
        mock_product_repo.get_by_uuid.return_value = existing_product

        strategy = DeduplicationStrategy(
            product_repo=mock_product_repo,
            raw_repo=mock_raw_repo,
            source_link_repo=mock_source_link_repo,
        )

        product, confidence, method = await strategy.find_duplicate(sample_snapshot)

        assert product == existing_product
        assert confidence == 0.95
        assert method == "sku_brand_match"

    @pytest.mark.asyncio
    async def test_no_duplicate_found(
        self,
        mock_product_repo,
        mock_raw_repo,
        mock_source_link_repo,
        sample_snapshot,
    ):
        """Should return None when no duplicate found."""
        mock_source_link_repo.find_product_by_source.return_value = None
        mock_raw_repo.find_by_ean.return_value = []
        mock_raw_repo.find_by_sku_and_brand.return_value = []
        mock_product_repo.get_by_name.return_value = None

        strategy = DeduplicationStrategy(
            product_repo=mock_product_repo,
            raw_repo=mock_raw_repo,
            source_link_repo=mock_source_link_repo,
        )

        product, confidence, method = await strategy.find_duplicate(sample_snapshot)

        assert product is None
        assert confidence == 0.0
        assert method == ""


# ============================================================================
# PRODUCT REFINERY TESTS
# ============================================================================

class TestProductRefinery:
    """Test main ProductRefinery class."""

    @pytest.mark.asyncio
    async def test_process_creates_new_product(
        self,
        mock_pool,
        mock_product_repo,
        mock_raw_repo,
        mock_source_link_repo,
        mock_audit_repo,
        mock_embedding_client,
        sample_raw_data,
    ):
        """Should create new product when no duplicate found."""
        snapshot = RawProductSnapshot(
            id=uuid4(),
            source_name="petrovich",
            source_url=sample_raw_data["source_url"],
            external_id="ext-123",
            raw_data=sample_raw_data,
            content_hash="hash123",
            extracted_ean="4607026710047",
            extracted_sku="ROT-30",
            extracted_brand="Knauf",
        )
        
        mock_raw_repo.save_snapshot.return_value = snapshot
        mock_raw_repo.find_by_content_hash.return_value = None
        mock_source_link_repo.find_product_by_source.return_value = None
        mock_raw_repo.find_by_ean.return_value = []
        mock_raw_repo.find_by_sku_and_brand.return_value = []
        mock_product_repo.get_by_name.return_value = None

        refinery = ProductRefinery(
            pool=mock_pool,
            product_repo=mock_product_repo,
            raw_repo=mock_raw_repo,
            source_link_repo=mock_source_link_repo,
            audit_repo=mock_audit_repo,
            embedding_client=mock_embedding_client,
        )

        result = await refinery.process(sample_raw_data)

        assert result.status == "new_product"
        assert result.product_uuid is not None
        mock_product_repo.create_with_outbox.assert_called_once()
        mock_audit_repo.log_action.assert_called()

    @pytest.mark.asyncio
    async def test_process_enriches_existing_product(
        self,
        mock_pool,
        mock_product_repo,
        mock_raw_repo,
        mock_source_link_repo,
        mock_audit_repo,
        existing_product,
        sample_raw_data,
    ):
        """Should enrich existing product when duplicate found."""
        snapshot = RawProductSnapshot(
            id=uuid4(),
            source_name="leroy",
            source_url="https://leroy.ru/product/456",
            raw_data=sample_raw_data,
            content_hash="hash456",
            extracted_ean="4607026710047",
            extracted_brand="Knauf",
        )
        
        mock_raw_repo.save_snapshot.return_value = snapshot
        mock_raw_repo.find_by_content_hash.return_value = None
        mock_source_link_repo.find_product_by_source.return_value = existing_product.uuid
        mock_product_repo.get_by_uuid.return_value = existing_product

        # Mock connection for merge operations
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []  # No existing images
        mock_conn.fetchval.return_value = 0  # No existing images
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        refinery = ProductRefinery(
            pool=mock_pool,
            product_repo=mock_product_repo,
            raw_repo=mock_raw_repo,
            source_link_repo=mock_source_link_repo,
            audit_repo=mock_audit_repo,
        )

        result = await refinery.process(sample_raw_data)

        # Since URL match, it should be enriched or duplicate
        assert result.status in ["enriched", "duplicate"]
        assert result.product_uuid == existing_product.uuid

    @pytest.mark.asyncio
    async def test_process_skips_content_duplicate(
        self,
        mock_pool,
        mock_product_repo,
        mock_raw_repo,
        mock_source_link_repo,
        mock_audit_repo,
        sample_raw_data,
    ):
        """Should skip if exact content already exists."""
        existing_snapshot = RawProductSnapshot(
            id=uuid4(),
            source_name="petrovich",
            source_url=sample_raw_data["source_url"],
            raw_data=sample_raw_data,
            content_hash="hash123",
            linked_product_uuid=uuid4(),
        )
        
        new_snapshot = RawProductSnapshot(
            id=uuid4(),
            source_name="petrovich",
            source_url=sample_raw_data["source_url"],
            raw_data=sample_raw_data,
            content_hash="hash123",
        )
        
        mock_raw_repo.save_snapshot.return_value = new_snapshot
        mock_raw_repo.find_by_content_hash.return_value = existing_snapshot

        refinery = ProductRefinery(
            pool=mock_pool,
            product_repo=mock_product_repo,
            raw_repo=mock_raw_repo,
            source_link_repo=mock_source_link_repo,
            audit_repo=mock_audit_repo,
        )

        result = await refinery.process(sample_raw_data)

        assert result.status == "duplicate"
        assert result.product_uuid == existing_snapshot.linked_product_uuid

    @pytest.mark.asyncio
    async def test_process_handles_missing_url(
        self,
        mock_pool,
        mock_product_repo,
        mock_raw_repo,
        mock_source_link_repo,
        mock_audit_repo,
    ):
        """Should return error for missing source_url."""
        refinery = ProductRefinery(
            pool=mock_pool,
            product_repo=mock_product_repo,
            raw_repo=mock_raw_repo,
            source_link_repo=mock_source_link_repo,
            audit_repo=mock_audit_repo,
        )

        result = await refinery.process({"name_original": "Test"})

        assert result.status == "error"
        assert "source_url" in result.message.lower()


# ============================================================================
# DATA MERGER TESTS
# ============================================================================

class TestDataMerger:
    """Test data merging logic."""

    def test_source_priority(self, mock_pool):
        """Source priority should be correctly ordered."""
        merger = DataMerger(mock_pool)
        
        # Official sources should have lowest priority (best)
        assert merger.get_source_priority("knauf") < merger.get_source_priority("petrovich")
        assert merger.get_source_priority("petrovich") < merger.get_source_priority("unknown")

    @pytest.mark.asyncio
    async def test_merge_images_adds_new(self, mock_pool):
        """Should add new images without duplicates."""
        product_uuid = uuid4()
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [{"url": "https://existing.jpg"}]
        mock_conn.fetchval.return_value = 1
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        merger = DataMerger(mock_pool)
        
        new_images = [
            {"url": "https://existing.jpg"},  # Should skip
            {"url": "https://new1.jpg"},       # Should add
            {"url": "https://new2.jpg"},       # Should add
        ]

        added = await merger.merge_images(product_uuid, new_images, "petrovich")

        assert len(added) == 2
        assert "https://new1.jpg" in added
        assert "https://new2.jpg" in added

    @pytest.mark.asyncio
    async def test_merge_attributes_no_overwrite(self, mock_pool):
        """Should add new attributes without overwriting existing."""
        product_uuid = uuid4()
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [{"name": "вес"}]  # Existing
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        merger = DataMerger(mock_pool)
        
        new_attrs = [
            {"name": "Вес", "value": "30", "unit": "кг"},    # Should skip (exists)
            {"name": "Цвет", "value": "Белый"},              # Should add
        ]

        added = await merger.merge_attributes(product_uuid, new_attrs, "leroy")

        assert len(added) == 1
        assert "Цвет" in added


# ============================================================================
# MANUFACTURER LINKER TESTS
# ============================================================================

class TestManufacturerLinker:
    """Test manufacturer linking logic."""

    @pytest.mark.asyncio
    async def test_link_existing_manufacturer(self, mock_pool):
        """Should link to existing manufacturer."""
        product_uuid = uuid4()
        manufacturer_id = uuid4()
        
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"id": manufacturer_id}
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        linker = ManufacturerLinker(mock_pool)
        
        result = await linker.link_manufacturer(product_uuid, "Knauf")

        assert result == manufacturer_id

    @pytest.mark.asyncio
    async def test_create_new_manufacturer(self, mock_pool):
        """Should create new manufacturer if not exists."""
        product_uuid = uuid4()
        
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None  # No existing
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        linker = ManufacturerLinker(mock_pool)
        
        result = await linker.link_manufacturer(product_uuid, "NewBrand")

        assert result is not None
        mock_conn.execute.assert_called()  # INSERT was called
