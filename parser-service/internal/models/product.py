"""
Pydantic models for raw product data.

These models represent the data extracted from external sources
before processing by the Product Service.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from enum import Enum

from pydantic import BaseModel, HttpUrl, Field, field_validator


class ProductAttributeType(str, Enum):
    """Product attribute types."""
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    LIST = "list"
    UNIT = "unit"  # Value with unit (e.g., "5 kg")


class ProductAttribute(BaseModel):
    """Product attribute/characteristic."""
    name: str
    value: str
    type: ProductAttributeType = ProductAttributeType.TEXT
    unit: Optional[str] = None


class ProductPrice(BaseModel):
    """Product pricing information."""
    current: float
    currency: str = "RUB"
    original: Optional[float] = None  # Before discount
    discount_percent: Optional[float] = None


class AvailabilityStatus(str, Enum):
    """Product availability status."""
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PRE_ORDER = "pre_order"
    DISCONTINUED = "discontinued"
    UNKNOWN = "unknown"


class ProductAvailability(BaseModel):
    """Product availability information."""
    status: AvailabilityStatus
    quantity: Optional[int] = None
    store_id: Optional[str] = None
    store_name: Optional[str] = None


class ProductImage(BaseModel):
    """Product image."""
    url: HttpUrl
    alt: Optional[str] = None
    position: int = 0  # Order in gallery


class DocumentType(str, Enum):
    """Document types."""
    MANUAL = "manual"
    CERTIFICATE = "certificate"
    DATASHEET = "datasheet"
    WARRANTY = "warranty"
    OTHER = "other"


class ProductDocument(BaseModel):
    """Product document (PDF, etc.)."""
    url: HttpUrl
    title: Optional[str] = None
    type: DocumentType = DocumentType.OTHER
    file_format: Optional[str] = None  # pdf, doc, etc.


class RawProduct(BaseModel):
    """
    Raw product data extracted from external source.
    
    This is the digital twin representation sent to Kafka.
    """
    # Identification
    id: UUID = Field(default_factory=uuid4)
    source_url: HttpUrl
    source_name: str
    external_id: Optional[str] = None
    sku: Optional[str] = None
    
    # Core info
    name_original: str
    name_technical: Optional[str] = None
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    
    # Classification
    category_path: List[str] = Field(default_factory=list)
    category_id: Optional[str] = None
    
    # Description
    description_short: Optional[str] = None
    description_full: Optional[str] = None
    
    # Attributes (KEY for AI)
    attributes: List[ProductAttribute] = Field(default_factory=list)
    
    # Pricing
    price: Optional[ProductPrice] = None
    
    # Availability
    availability: Optional[ProductAvailability] = None
    
    # Media
    images: List[ProductImage] = Field(default_factory=list)
    
    # Documents (CRITICAL for AI agents)
    documents: List[ProductDocument] = Field(default_factory=list)
    
    # Schema.org data (raw JSON-LD)
    schema_org_data: Optional[Dict[str, Any]] = None
    
    # Metadata
    parsed_at: datetime = Field(default_factory=datetime.utcnow)
    parser_version: str = "1.0.0"
    
    class Config:
        """Pydantic config."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }
    
    def to_kafka_message(self) -> dict:
        """
        Convert to Kafka message format.
        
        Returns:
            Dictionary suitable for Kafka publishing.
        """
        return self.model_dump(mode='json')
