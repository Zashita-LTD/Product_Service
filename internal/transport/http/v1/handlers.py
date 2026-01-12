"""
FastAPI HTTP Handlers for Product Service API v1.

Implements REST endpoints for product family operations.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Header, status
from pydantic import BaseModel, Field

from internal.usecase.create_product import (
    CreateProductUseCase,
    CreateProductInput,
)
from internal.usecase.enrich_product import (
    EnrichProductUseCase,
    EnrichProductInput,
)
from internal.domain.errors import (
    ProductNotFoundError,
    ProductAlreadyExistsError,
    EnrichmentError,
    DomainValidationError,
)
from pkg.logger.logger import get_logger


logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/products", tags=["products"])


# Request/Response DTOs
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


def set_dependencies(
    create_use_case: CreateProductUseCase,
    enrich_use_case: EnrichProductUseCase,
    repository=None,
) -> None:
    """
    Set handler dependencies.
    
    Called during application startup.
    """
    _deps.create_use_case = create_use_case
    _deps.enrich_use_case = enrich_use_case
    _deps.repository = repository


# Handlers
@router.post(
    "/families",
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
    "/families/{product_uuid}",
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
    "/families/{product_uuid}/enrich",
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


@router.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint.
    
    Returns:
        Health status.
    """
    return {"status": "healthy", "service": "product-service"}
