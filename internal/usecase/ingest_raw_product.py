"""
Ingest Raw Product Use Case.

Handles ingestion of raw product data from parser-service (scraper).
Implements deduplication by source_url and creates product families.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Protocol
from uuid import UUID

from internal.domain.product import ProductFamily
from internal.domain.errors import ProductAlreadyExistsError
from internal.usecase.create_product import CreateProductUseCase, CreateProductInput
from pkg.logger.logger import get_logger


logger = get_logger(__name__)


# Default category for scraped products (can be refined by AI later)
DEFAULT_CATEGORY_ID = 1


@dataclass
class RawProductData:
    """
    Raw product data from parser-service.

    Maps to the RawProduct model from parser-service/internal/models/product.py
    """
    id: str
    source_url: str
    name_original: str
    brand: Optional[str] = None
    category_breadcrumbs: Optional[list[str]] = None
    attributes: Optional[list[dict]] = None
    documents: Optional[list[dict]] = None
    images: Optional[list[str]] = None
    price_amount: Optional[float] = None
    price_currency: Optional[str] = None
    availability: Optional[str] = None
    schema_org_data: Optional[dict] = None
    next_data: Optional[dict] = None
    scraped_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "RawProductData":
        """Create RawProductData from dictionary."""
        return cls(
            id=data.get("id", ""),
            source_url=data.get("source_url", ""),
            name_original=data.get("name_original", ""),
            brand=data.get("brand"),
            category_breadcrumbs=data.get("category_breadcrumbs"),
            attributes=data.get("attributes"),
            documents=data.get("documents"),
            images=data.get("images"),
            price_amount=data.get("price_amount"),
            price_currency=data.get("price_currency"),
            availability=data.get("availability"),
            schema_org_data=data.get("schema_org_data"),
            next_data=data.get("next_data"),
            scraped_at=data.get("scraped_at"),
        )


@dataclass
class IngestResult:
    """Result of raw product ingestion."""
    product_uuid: Optional[UUID] = None
    source_url: str = ""
    status: str = "unknown"  # created, duplicate, error
    message: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "product_uuid": str(self.product_uuid) if self.product_uuid else None,
            "source_url": self.source_url,
            "status": self.status,
            "message": self.message,
        }


class CacheProtocol(Protocol):
    """Protocol for cache operations."""

    async def get(self, key: str) -> Optional[dict]:
        """Get value from cache."""
        ...

    async def set(self, key: str, value: dict, ttl: Optional[int] = None) -> bool:
        """Set value in cache."""
        ...


class ProductRepositoryProtocol(Protocol):
    """Protocol for product repository."""

    async def get_by_name(self, name_technical: str) -> Optional[ProductFamily]:
        """Get product by technical name."""
        ...

    async def get_by_source_url(self, source_url: str) -> Optional[ProductFamily]:
        """Get product by source URL."""
        ...


class IngestRawProductUseCase:
    """
    Use case for ingesting raw product data from scraper.

    This use case:
    1. Receives raw product data from parser-service
    2. Checks if product with same source_url already exists (deduplication)
    3. Creates new product family if not duplicate
    4. The created product will be automatically enriched via Outbox Pattern
    """

    # Cache key prefix for tracking processed URLs
    URL_CACHE_PREFIX = "scraped:url:"
    URL_CACHE_TTL = 86400 * 7  # 7 days

    def __init__(
        self,
        repository: ProductRepositoryProtocol,
        create_use_case: CreateProductUseCase,
        cache: Optional[CacheProtocol] = None,
    ) -> None:
        """
        Initialize the use case.

        Args:
            repository: Product repository for checking duplicates.
            create_use_case: Use case for creating products.
            cache: Optional cache for URL deduplication.
        """
        self._repository = repository
        self._create_use_case = create_use_case
        self._cache = cache

    async def execute(self, raw_data: RawProductData) -> IngestResult:
        """
        Execute the ingest raw product use case.

        Args:
            raw_data: Raw product data from scraper.

        Returns:
            IngestResult with status of the operation.
        """
        source_url = raw_data.source_url

        if not source_url:
            logger.warning("Raw product missing source_url", raw_id=raw_data.id)
            return IngestResult(
                source_url="",
                status="error",
                message="Missing source_url",
            )

        if not raw_data.name_original:
            logger.warning(
                "Raw product missing name",
                source_url=source_url,
            )
            return IngestResult(
                source_url=source_url,
                status="error",
                message="Missing product name",
            )

        # Check URL cache for quick deduplication
        if self._cache:
            cache_key = f"{self.URL_CACHE_PREFIX}{source_url}"
            cached = await self._cache.get(cache_key)
            if cached:
                logger.debug(
                    "Product URL already processed (cache hit)",
                    source_url=source_url,
                )
                return IngestResult(
                    product_uuid=UUID(cached["uuid"]) if cached.get("uuid") else None,
                    source_url=source_url,
                    status="duplicate",
                    message="Product already exists (cached)",
                )

        # Check database for existing product by source_url
        existing_by_url = await self._repository.get_by_source_url(source_url)
        if existing_by_url:
            logger.info(
                "Product already exists by source_url",
                source_url=source_url,
                existing_uuid=str(existing_by_url.uuid),
            )
            # Cache the URL mapping
            if self._cache:
                await self._cache.set(
                    f"{self.URL_CACHE_PREFIX}{source_url}",
                    {"uuid": str(existing_by_url.uuid), "name": existing_by_url.name_technical},
                    ttl=self.URL_CACHE_TTL,
                )
            return IngestResult(
                product_uuid=existing_by_url.uuid,
                source_url=source_url,
                status="duplicate",
                message="Product already exists (by URL)",
            )

        # Build technical name from raw data
        name_technical = self._build_technical_name(raw_data)

        # Check for existing product by name
        existing = await self._repository.get_by_name(name_technical)
        if existing:
            logger.info(
                "Product already exists by name",
                source_url=source_url,
                name_technical=name_technical,
                existing_uuid=str(existing.uuid),
            )
            # Cache the URL mapping
            if self._cache:
                await self._cache.set(
                    f"{self.URL_CACHE_PREFIX}{source_url}",
                    {"uuid": str(existing.uuid), "name": name_technical},
                    ttl=self.URL_CACHE_TTL,
                )
            return IngestResult(
                product_uuid=existing.uuid,
                source_url=source_url,
                status="duplicate",
                message="Product already exists",
            )

        # Extract category ID from breadcrumbs or use default
        category_id = self._extract_category_id(raw_data)

        # Create new product
        try:
            create_input = CreateProductInput(
                name_technical=name_technical,
                category_id=category_id,
                request_id=raw_data.id,
            )
            result = await self._create_use_case.execute(create_input)
            product = result.product

            logger.info(
                "Product created from raw data",
                source_url=source_url,
                product_uuid=str(product.uuid),
                name_technical=name_technical,
            )

            # Cache the URL mapping for future deduplication
            if self._cache:
                await self._cache.set(
                    f"{self.URL_CACHE_PREFIX}{source_url}",
                    {"uuid": str(product.uuid), "name": name_technical},
                    ttl=self.URL_CACHE_TTL,
                )

            return IngestResult(
                product_uuid=product.uuid,
                source_url=source_url,
                status="created",
                message="Product created successfully",
            )

        except ProductAlreadyExistsError:
            logger.info(
                "Product already exists (race condition)",
                source_url=source_url,
                name_technical=name_technical,
            )
            return IngestResult(
                source_url=source_url,
                status="duplicate",
                message="Product already exists",
            )
        except Exception as e:
            logger.error(
                "Failed to create product from raw data",
                source_url=source_url,
                error=str(e),
            )
            return IngestResult(
                source_url=source_url,
                status="error",
                message=str(e),
            )

    def _build_technical_name(self, raw_data: RawProductData) -> str:
        """
        Build technical name from raw product data.

        Combines name, brand, and key attributes for uniqueness.

        Args:
            raw_data: Raw product data.

        Returns:
            Technical name string.
        """
        parts = []

        # Add brand if available
        if raw_data.brand:
            parts.append(raw_data.brand)

        # Add original name
        parts.append(raw_data.name_original)

        # Add key attributes for uniqueness (e.g., size, weight)
        if raw_data.attributes:
            key_attrs = []
            for attr in raw_data.attributes[:3]:  # Limit to first 3 attributes
                if isinstance(attr, dict):
                    name = attr.get("name", "")
                    value = attr.get("value", "")
                    unit = attr.get("unit", "")
                    if name and value:
                        key_attrs.append(f"{value}{unit}".strip())
            if key_attrs:
                parts.append(" ".join(key_attrs))

        # Join and normalize
        name = " ".join(filter(None, parts))

        # Truncate to max length
        if len(name) > 500:
            name = name[:497] + "..."

        return name

    def _extract_category_id(self, raw_data: RawProductData) -> int:
        """
        Extract category ID from raw data.

        Uses breadcrumbs or schema.org data to determine category.
        Falls back to default category if not determinable.

        Args:
            raw_data: Raw product data.

        Returns:
            Category ID.
        """
        # TODO: Implement category mapping from breadcrumbs
        # For now, use default category
        # In future: parse breadcrumbs and map to internal category IDs

        if raw_data.category_breadcrumbs:
            # Log breadcrumbs for future category mapping implementation
            logger.debug(
                "Category breadcrumbs",
                breadcrumbs=raw_data.category_breadcrumbs,
                source_url=raw_data.source_url,
            )

        return DEFAULT_CATEGORY_ID


class RawProductEventHandler:
    """
    Handler for raw product events from Kafka.

    Processes messages from raw-products topic.
    """

    def __init__(self, ingest_use_case: IngestRawProductUseCase) -> None:
        """
        Initialize the handler.

        Args:
            ingest_use_case: IngestRawProductUseCase instance.
        """
        self._ingest_use_case = ingest_use_case

    async def handle(self, event: dict) -> None:
        """
        Handle a raw product event.

        Args:
            event: The event data from Kafka.
        """
        # Extract payload - support both flat and nested formats
        payload = event.get("payload", event)

        # Parse raw product data
        try:
            raw_data = RawProductData.from_dict(payload)
        except Exception as e:
            logger.error(
                "Failed to parse raw product data",
                error=str(e),
                event_keys=list(event.keys()),
            )
            return

        source_url = raw_data.source_url
        logger.info(
            "Processing raw product",
            source_url=source_url,
            name=raw_data.name_original[:50] if raw_data.name_original else "N/A",
        )

        try:
            result = await self._ingest_use_case.execute(raw_data)

            logger.info(
                "Raw product processed",
                source_url=source_url,
                status=result.status,
                product_uuid=str(result.product_uuid) if result.product_uuid else None,
            )

        except Exception as e:
            logger.error(
                "Failed to process raw product",
                source_url=source_url,
                error=str(e),
            )
