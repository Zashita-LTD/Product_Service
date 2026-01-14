"""
FastAPI HTTP Handlers for Product Service API v1.

Implements REST endpoints for product family operations.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from internal.domain.errors import (
    DomainValidationError,
    EnrichmentError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
)
from internal.transport.http.dto import (
    AttributeDTO,
    AvailabilityDTO,
    CategoriesResponse,
    CategoryShort,
    CategoryTreeNode,
    DocumentDTO,
    ImageDTO,
    PaginatedResponse,
    PaginationInfo,
    PriceDTO,
    ProductDetail,
    ProductListItem,
    SearchRequest,
    SourceDTO,
)
from internal.usecase.create_product import (
    CreateProductInput,
    CreateProductUseCase,
)
from internal.usecase.enrich_product import (
    EnrichProductInput,
    EnrichProductUseCase,
)
from internal.usecase.search_products import (
    SearchProductsInput,
    SearchProductsUseCase,
)
from internal.usecase.semantic_search import (
    SemanticSearchInput,
    SemanticSearchUseCase,
)
from pkg.logger.logger import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix="/api/v1", tags=["products"])


# Import existing DTOs from dto module for legacy endpoints
from pydantic import BaseModel, Field


class CreateProductFamilyRequest(BaseModel):
    """Request body for creating a product family."""

    name_technical: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Technical name of the product",
        example="Кирпич М150",
    )
    category_id: int = Field(
        ...,
        gt=0,
        description="Category identifier",
        example=1,
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "name_technical": "Кирпич М150",
                "category_id": 1,
            }
        }


class ProductFamilyResponse(BaseModel):
    """Response body for a product family."""

    uuid: str = Field(..., description="Unique identifier")
    name_technical: str = Field(..., description="Technical name")
    category_id: int = Field(..., description="Category identifier")
    quality_score: Optional[float] = Field(None, description="Quality score (0.00 - 1.00)")
    enrichment_status: str = Field(..., description="Enrichment status")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "uuid": "550e8400-e29b-41d4-a716-446655440000",
                "name_technical": "Кирпич М150",
                "category_id": 1,
                "quality_score": 0.85,
                "enrichment_status": "enriched",
                "created_at": "2024-01-15T10:30:00",
                "updated_at": "2024-01-15T10:35:00",
            }
        }


class EnrichProductResponse(BaseModel):
    """Response body for product enrichment."""

    uuid: str
    quality_score: Optional[float]
    enrichment_status: str
    message: str


class ErrorResponse(BaseModel):
    """Error response body."""

    detail: str
    code: str
    request_id: Optional[str] = None


# Dependency injection container (simplified)
class Dependencies:
    """Container for handler dependencies."""

    create_use_case: Optional[CreateProductUseCase] = None
    enrich_use_case: Optional[EnrichProductUseCase] = None
    search_use_case: Optional[SearchProductsUseCase] = None
    semantic_search_use_case: Optional[SemanticSearchUseCase] = None
    repository = None


_deps = Dependencies()


def get_create_use_case() -> CreateProductUseCase:
    """Get CreateProductUseCase instance."""
    if _deps.create_use_case is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized",
        )
    return _deps.create_use_case


def get_enrich_use_case() -> EnrichProductUseCase:
    """Get EnrichProductUseCase instance."""
    if _deps.enrich_use_case is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized",
        )
    return _deps.enrich_use_case


def get_search_use_case() -> SearchProductsUseCase:
    """Get SearchProductsUseCase instance."""
    if _deps.search_use_case is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized",
        )
    return _deps.search_use_case


def get_semantic_search_use_case() -> SemanticSearchUseCase:
    """Get SemanticSearchUseCase instance."""
    if _deps.semantic_search_use_case is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized",
        )
    return _deps.semantic_search_use_case


def get_repository():
    """Get repository instance."""
    if _deps.repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized",
        )
    return _deps.repository


def set_dependencies(
    create_use_case: CreateProductUseCase,
    enrich_use_case: EnrichProductUseCase,
    search_use_case: Optional[SearchProductsUseCase] = None,
    semantic_search_use_case: Optional[SemanticSearchUseCase] = None,
    repository=None,
) -> None:
    """
    Set handler dependencies.

    Called during application startup.
    """
    _deps.create_use_case = create_use_case
    _deps.enrich_use_case = enrich_use_case
    _deps.search_use_case = search_use_case
    _deps.semantic_search_use_case = semantic_search_use_case
    _deps.repository = repository


# Handlers
@router.post(
    "/products/families",
    response_model=ProductFamilyResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Product family created successfully"},
        400: {"model": ErrorResponse, "description": "Validation error"},
        409: {"model": ErrorResponse, "description": "Product already exists"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
)
async def create_product_family(
    request: CreateProductFamilyRequest,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    use_case: CreateProductUseCase = Depends(get_create_use_case),
) -> ProductFamilyResponse:
    """
    Create a new product family.

    Creates a product family and publishes a creation event via Outbox Pattern.

    Args:
        request: Product family creation request.
        x_request_id: Optional request ID for idempotency.
        use_case: Injected use case.

    Returns:
        Created product family.
    """
    logger.info(
        "Creating product family",
        name_technical=request.name_technical,
        request_id=x_request_id,
    )

    try:
        input_dto = CreateProductInput(
            name_technical=request.name_technical,
            category_id=request.category_id,
            request_id=x_request_id,
        )

        result = await use_case.execute(input_dto)
        product = result.product

        logger.info(
            "Product family created",
            uuid=str(product.uuid),
            request_id=x_request_id,
        )

        return ProductFamilyResponse(
            uuid=str(product.uuid),
            name_technical=product.name_technical,
            category_id=product.category_id,
            quality_score=float(product.quality_score.value) if product.quality_score else None,
            enrichment_status=product.enrichment_status,
            created_at=product.created_at.isoformat(),
            updated_at=product.updated_at.isoformat(),
        )

    except ProductAlreadyExistsError as e:
        logger.warning(
            "Product already exists",
            name_technical=request.name_technical,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=e.message,
        )
    except DomainValidationError as e:
        logger.warning(
            "Validation error",
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


@router.get(
    "/products/families/{product_uuid}",
    response_model=ProductFamilyResponse,
    responses={
        200: {"description": "Product family found"},
        404: {"model": ErrorResponse, "description": "Product not found"},
    },
)
async def get_product_family(
    product_uuid: UUID,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
) -> ProductFamilyResponse:
    """
    Get a product family by UUID.

    Args:
        product_uuid: Product family UUID.
        x_request_id: Optional request ID.

    Returns:
        Product family data.
    """
    logger.info(
        "Getting product family",
        uuid=str(product_uuid),
        request_id=x_request_id,
    )

    if _deps.repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized",
        )

    product = await _deps.repository.get_by_uuid(product_uuid)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product family {product_uuid} not found",
        )

    return ProductFamilyResponse(
        uuid=str(product.uuid),
        name_technical=product.name_technical,
        category_id=product.category_id,
        quality_score=float(product.quality_score.value) if product.quality_score else None,
        enrichment_status=product.enrichment_status,
        created_at=product.created_at.isoformat(),
        updated_at=product.updated_at.isoformat(),
    )


@router.post(
    "/products/families/{product_uuid}/enrich",
    response_model=EnrichProductResponse,
    responses={
        200: {"description": "Product enriched successfully"},
        404: {"model": ErrorResponse, "description": "Product not found"},
        500: {"model": ErrorResponse, "description": "Enrichment failed"},
    },
)
async def enrich_product_family(
    product_uuid: UUID,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    use_case: EnrichProductUseCase = Depends(get_enrich_use_case),
) -> EnrichProductResponse:
    """
    Trigger AI enrichment for a product family.

    Uses Google Vertex AI to calculate quality score and other enrichment data.

    Args:
        product_uuid: Product family UUID.
        x_request_id: Optional request ID.
        use_case: Injected use case.

    Returns:
        Enrichment result.
    """
    logger.info(
        "Enriching product family",
        uuid=str(product_uuid),
        request_id=x_request_id,
    )

    try:
        input_dto = EnrichProductInput(product_uuid=product_uuid)
        result = await use_case.execute(input_dto)

        logger.info(
            "Product family enriched",
            uuid=str(product_uuid),
            quality_score=float(result.quality_score) if result.quality_score else None,
        )

        return EnrichProductResponse(
            uuid=str(product_uuid),
            quality_score=float(result.quality_score) if result.quality_score else None,
            enrichment_status=result.status,
            message="Product enriched successfully",
        )

    except ProductNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product family {product_uuid} not found",
        )
    except EnrichmentError as e:
        logger.error(
            "Enrichment failed",
            uuid=str(product_uuid),
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Enrichment failed: {e.reason}",
        )


@router.get("/products/health")
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns:
        Health status.
    """
    return {"status": "healthy", "service": "product-service"}


@router.get("/products/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.

    Returns:
        Prometheus metrics in text format.
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# Helper functions for DTO conversion
def _build_category_dto(category_id: int) -> CategoryShort:
    """Build category DTO (placeholder for now)."""
    return CategoryShort(
        id=category_id,
        name=f"Category {category_id}",
        path=["Root", f"Category {category_id}"],
    )


def _build_product_list_item(row: dict) -> ProductListItem:
    """Convert database row to ProductListItem DTO."""
    price_dto = None
    # Price will be fetched separately if needed

    return ProductListItem(
        uuid=row["uuid"],
        name_technical=row["name_technical"],
        brand=row.get("brand"),
        sku=row.get("sku"),
        category=_build_category_dto(row["category_id"]),
        price=price_dto,
        image_url=row.get("image_url"),
        source_name=row.get("source_name"),
        enrichment_status=row["enrichment_status"],
        quality_score=float(row["quality_score"]) if row.get("quality_score") else None,
        created_at=row["created_at"],
        similarity=float(row["similarity"]) if row.get("similarity") is not None else None,
    )


# New API Endpoints


@router.get(
    "/products",
    response_model=PaginatedResponse,
    responses={
        200: {"description": "List of products"},
    },
)
async def list_products(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    brand: Optional[str] = Query(None, description="Filter by brand"),
    source_name: Optional[str] = Query(None, description="Filter by source"),
    min_price: Optional[Decimal] = Query(None, description="Minimum price"),
    max_price: Optional[Decimal] = Query(None, description="Maximum price"),
    in_stock: Optional[bool] = Query(None, description="Only in stock"),
    enrichment_status: Optional[str] = Query(None, description="Filter by enrichment status"),
    sort_by: str = Query("created_at", description="Sort by field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    repository=Depends(get_repository),
) -> PaginatedResponse:
    """
    Get list of products with filters and pagination.

    Supports filtering by category, brand, source, price range, stock availability,
    and enrichment status.
    """
    logger.info(
        "Listing products",
        page=page,
        per_page=per_page,
        category_id=category_id,
    )

    offset = (page - 1) * per_page

    products, total = await repository.list_products(
        category_id=category_id,
        brand=brand,
        source_name=source_name,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        enrichment_status=enrichment_status,
        offset=offset,
        limit=per_page,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    product_items = [_build_product_list_item(p) for p in products]

    total_pages = (total + per_page - 1) // per_page

    return PaginatedResponse(
        data=product_items,
        pagination=PaginationInfo(
            page=page,
            per_page=per_page,
            total_items=total,
            total_pages=total_pages,
        ),
    )


@router.get(
    "/products/{uuid}",
    response_model=ProductDetail,
    responses={
        200: {"description": "Product details"},
        404: {"model": ErrorResponse, "description": "Product not found"},
    },
)
async def get_product_details(
    uuid: UUID = Path(..., description="Product UUID"),
    repository=Depends(get_repository),
) -> ProductDetail:
    """
    Get detailed product information including attributes, images, and documents.
    """
    logger.info("Getting product details", uuid=str(uuid))

    result = await repository.get_product_with_details(uuid)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {uuid} not found",
        )

    product = result["product"]

    # Build DTOs
    attributes = [
        AttributeDTO(
            name=attr["name"],
            value=attr["value"],
            unit=attr.get("unit"),
        )
        for attr in result["attributes"]
    ]

    images = [
        ImageDTO(
            url=img["url"],
            alt=img.get("alt_text", ""),
            is_main=img.get("is_main", False),
        )
        for img in result["images"]
    ]

    documents = [
        DocumentDTO(
            type=doc["document_type"],
            title=doc["title"],
            url=doc["url"],
        )
        for doc in result["documents"]
    ]

    price_dto = None
    if result["price"]:
        price_dto = PriceDTO(
            value=Decimal(str(result["price"]["amount"])),
            currency=result["price"].get("currency", "RUB"),
            unit="шт",
        )

    availability = None
    if result["inventory"]:
        availability = AvailabilityDTO(
            in_stock=bool(result["inventory"].get("in_stock", False)),
            quantity=(
                int(result["inventory"]["total_quantity"])
                if result["inventory"].get("total_quantity")
                else None
            ),
            delivery_days=2,  # Placeholder
        )

    return ProductDetail(
        uuid=product["uuid"],
        name_technical=product["name_technical"],
        brand=product.get("brand"),
        manufacturer=product.get("brand"),  # Using brand as manufacturer for now
        sku=product.get("sku"),
        description=product.get("description"),
        category=_build_category_dto(product["category_id"]),
        attributes=attributes,
        price=price_dto,
        availability=availability,
        images=images,
        documents=documents,
        source=SourceDTO(
            name=product.get("source_name"),
            url=product.get("source_url"),
            external_id=product.get("external_id"),
        ),
        enrichment_status=product["enrichment_status"],
        quality_score=float(product["quality_score"]) if product.get("quality_score") else None,
        created_at=product["created_at"],
        updated_at=product["updated_at"],
    )


@router.post(
    "/products/search",
    response_model=PaginatedResponse,
    responses={
        200: {"description": "Search results"},
    },
)
async def search_products(
    request: SearchRequest,
    use_case: SearchProductsUseCase = Depends(get_search_use_case),
) -> PaginatedResponse:
    """
    Full-text search for products.

    Uses PostgreSQL full-text search with Russian language support.
    Supports all the same filters as the list endpoint.
    """
    logger.info(
        "Searching products",
        query=request.query,
        page=request.page,
    )

    input_data = SearchProductsInput(
        query=request.query,
        category_id=request.filters.category_id if request.filters else None,
        brand=request.filters.brand if request.filters else None,
        source_name=request.filters.source_name if request.filters else None,
        min_price=request.filters.min_price if request.filters else None,
        max_price=request.filters.max_price if request.filters else None,
        in_stock=request.filters.in_stock if request.filters else None,
        enrichment_status=request.filters.enrichment_status if request.filters else None,
        page=request.page,
        per_page=request.per_page,
    )

    result = await use_case.execute(input_data)

    product_items = [_build_product_list_item(p) for p in result.products]

    total_pages = (result.total + request.per_page - 1) // request.per_page

    return PaginatedResponse(
        data=product_items,
        pagination=PaginationInfo(
            page=result.page,
            per_page=result.per_page,
            total_items=result.total,
            total_pages=total_pages,
        ),
    )


@router.post(
    "/products/search/semantic",
    response_model=PaginatedResponse,
    responses={
        200: {"description": "Semantic search results"},
    },
)
async def semantic_search_products(
    request: SearchRequest,
    use_case: SemanticSearchUseCase = Depends(get_semantic_search_use_case),
) -> PaginatedResponse:
    """Semantic search endpoint backed by pgvector."""

    logger.info(
        "Semantic search",
        query=request.query,
        page=request.page,
    )

    input_data = SemanticSearchInput(
        query=request.query,
        category_id=request.filters.category_id if request.filters else None,
        brand=request.filters.brand if request.filters else None,
        source_name=request.filters.source_name if request.filters else None,
        min_price=request.filters.min_price if request.filters else None,
        max_price=request.filters.max_price if request.filters else None,
        in_stock=request.filters.in_stock if request.filters else None,
        enrichment_status=request.filters.enrichment_status if request.filters else None,
        page=request.page,
        per_page=request.per_page,
    )

    result = await use_case.execute(input_data)

    product_items = [_build_product_list_item(p) for p in result.products]
    total_pages = (result.total + request.per_page - 1) // request.per_page

    return PaginatedResponse(
        data=product_items,
        pagination=PaginationInfo(
            page=result.page,
            per_page=result.per_page,
            total_items=result.total,
            total_pages=total_pages,
        ),
    )


@router.get(
    "/categories",
    response_model=CategoriesResponse,
    responses={
        200: {"description": "Category tree"},
    },
)
async def get_categories() -> CategoriesResponse:
    """
    Get category tree.

    Returns hierarchical category structure.
    This is a placeholder implementation.
    """
    logger.info("Getting category tree")

    # Placeholder implementation
    # In a real system, this would fetch from a categories table
    categories = [
        CategoryTreeNode(
            id=1,
            name="Стройматериалы",
            slug="stroymaterialy",
            product_count=5234,
            children=[
                CategoryTreeNode(
                    id=10,
                    name="Кирпич",
                    slug="kirpich",
                    product_count=342,
                    children=[],
                )
            ],
        )
    ]

    return CategoriesResponse(data=categories)


@router.get(
    "/categories/{category_id}/products",
    response_model=PaginatedResponse,
    responses={
        200: {"description": "Products in category"},
    },
)
async def get_category_products(
    category_id: int = Path(..., description="Category ID"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    brand: Optional[str] = Query(None, description="Filter by brand"),
    source_name: Optional[str] = Query(None, description="Filter by source"),
    min_price: Optional[Decimal] = Query(None, description="Minimum price"),
    max_price: Optional[Decimal] = Query(None, description="Maximum price"),
    in_stock: Optional[bool] = Query(None, description="Only in stock"),
    enrichment_status: Optional[str] = Query(None, description="Filter by enrichment status"),
    sort_by: str = Query("created_at", description="Sort by field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    repository=Depends(get_repository),
) -> PaginatedResponse:
    """
    Get products in a specific category.

    This is equivalent to GET /products with category_id filter pre-applied.
    """
    logger.info(
        "Getting category products",
        category_id=category_id,
        page=page,
    )

    offset = (page - 1) * per_page

    products, total = await repository.list_products(
        category_id=category_id,
        brand=brand,
        source_name=source_name,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        enrichment_status=enrichment_status,
        offset=offset,
        limit=per_page,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    product_items = [_build_product_list_item(p) for p in products]

    total_pages = (total + per_page - 1) // per_page

    return PaginatedResponse(
        data=product_items,
        pagination=PaginationInfo(
            page=page,
            per_page=per_page,
            total_items=total,
            total_pages=total_pages,
        ),
    )
