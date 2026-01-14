"""
Data Transfer Objects for Product Service API.

Contains Pydantic models for request/response validation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# Category DTOs
class CategoryShort(BaseModel):
    """Short category information for product list."""

    id: int = Field(..., description="Category ID")
    name: str = Field(..., description="Category name")
    path: List[str] = Field(default_factory=list, description="Category path (breadcrumb)")

    class Config:
        json_schema_extra = {
            "example": {"id": 10, "name": "Кирпич", "path": ["Стройматериалы", "Кирпич"]}
        }


class CategoryTreeNode(BaseModel):
    """Category tree node with children."""

    id: int = Field(..., description="Category ID")
    name: str = Field(..., description="Category name")
    slug: str = Field(..., description="URL slug")
    product_count: int = Field(0, description="Number of products in category")
    children: List["CategoryTreeNode"] = Field(default_factory=list, description="Child categories")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "Стройматериалы",
                "slug": "stroymaterialy",
                "product_count": 5234,
                "children": [],
            }
        }


class CategoriesResponse(BaseModel):
    """Response with category tree."""

    data: List[CategoryTreeNode] = Field(..., description="Category tree")


# Price DTOs
class PriceDTO(BaseModel):
    """Price information."""

    value: Decimal = Field(..., description="Price value")
    currency: str = Field("RUB", description="Currency code")
    unit: str = Field("шт", description="Unit of measurement")
    old_value: Optional[Decimal] = Field(None, description="Old price (for discounts)")

    class Config:
        json_schema_extra = {
            "example": {"value": "15.50", "currency": "RUB", "unit": "шт", "old_value": "18.00"}
        }


# Attribute DTOs
class AttributeDTO(BaseModel):
    """Product attribute (key-value pair)."""

    name: str = Field(..., description="Attribute name")
    value: str = Field(..., description="Attribute value")
    unit: Optional[str] = Field(None, description="Unit of measurement")

    class Config:
        json_schema_extra = {"example": {"name": "Марка прочности", "value": "М150", "unit": None}}


# Availability DTOs
class AvailabilityDTO(BaseModel):
    """Product availability information."""

    in_stock: bool = Field(False, description="Is product in stock")
    quantity: Optional[int] = Field(None, description="Available quantity")
    delivery_days: Optional[int] = Field(None, description="Delivery time in days")

    class Config:
        json_schema_extra = {"example": {"in_stock": True, "quantity": 5000, "delivery_days": 2}}


# Image DTOs
class ImageDTO(BaseModel):
    """Product image."""

    url: str = Field(..., description="Image URL")
    alt: str = Field("", description="Alternative text")
    is_main: bool = Field(False, description="Is main image")

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com/image.jpg",
                "alt": "Кирпич М150",
                "is_main": True,
            }
        }


# Document DTOs
class DocumentDTO(BaseModel):
    """Product document (certificate, manual, etc.)."""

    type: str = Field(..., description="Document type")
    title: str = Field(..., description="Document title")
    url: str = Field(..., description="Document URL")

    class Config:
        json_schema_extra = {
            "example": {
                "type": "certificate",
                "title": "Сертификат соответствия",
                "url": "https://example.com/cert.pdf",
            }
        }


# Source DTOs
class SourceDTO(BaseModel):
    """Product source information."""

    name: Optional[str] = Field(None, description="Source name (e.g., petrovich.ru)")
    url: Optional[str] = Field(None, description="Source URL")
    external_id: Optional[str] = Field(None, description="External ID in source system")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "petrovich.ru",
                "url": "https://moscow.petrovich.ru/product/...",
                "external_id": "789012",
            }
        }


# Product DTOs
class ProductListItem(BaseModel):
    """Product item in list view."""

    uuid: UUID = Field(..., description="Product UUID")
    name_technical: str = Field(..., description="Technical name")
    brand: Optional[str] = Field(None, description="Brand name")
    sku: Optional[str] = Field(None, description="SKU")
    category: CategoryShort = Field(..., description="Category information")
    price: Optional[PriceDTO] = Field(None, description="Price information")
    source_name: Optional[str] = Field(None, description="Source name")
    enrichment_status: str = Field(..., description="Enrichment status")
    quality_score: Optional[float] = Field(None, description="Quality score (0.00 - 1.00)")
    created_at: datetime = Field(..., description="Creation timestamp")
    similarity: Optional[float] = Field(
        None,
        description="Semantic similarity score (0.00 - 1.00)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "uuid": "550e8400-e29b-41d4-a716-446655440000",
                "name_technical": "Кирпич керамический М150",
                "brand": "ЛСР",
                "sku": "123456",
                "category": {"id": 10, "name": "Кирпич", "path": ["Стройматериалы", "Кирпич"]},
                "price": {"value": "15.50", "currency": "RUB", "unit": "шт"},
                "source_name": "petrovich.ru",
                "enrichment_status": "enriched",
                "quality_score": 0.85,
                "created_at": "2024-01-15T10:30:00Z",
                "similarity": 0.94,
            }
        }


class ProductDetail(BaseModel):
    """Detailed product information."""

    uuid: UUID = Field(..., description="Product UUID")
    name_technical: str = Field(..., description="Technical name")
    brand: Optional[str] = Field(None, description="Brand name")
    manufacturer: Optional[str] = Field(None, description="Manufacturer name")
    sku: Optional[str] = Field(None, description="SKU")
    description: Optional[str] = Field(None, description="Product description")
    category: CategoryShort = Field(..., description="Category information")
    attributes: List[AttributeDTO] = Field(default_factory=list, description="Product attributes")
    price: Optional[PriceDTO] = Field(None, description="Price information")
    availability: Optional[AvailabilityDTO] = Field(None, description="Availability information")
    images: List[ImageDTO] = Field(default_factory=list, description="Product images")
    documents: List[DocumentDTO] = Field(default_factory=list, description="Product documents")
    source: SourceDTO = Field(..., description="Source information")
    enrichment_status: str = Field(..., description="Enrichment status")
    quality_score: Optional[float] = Field(None, description="Quality score (0.00 - 1.00)")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "uuid": "550e8400-e29b-41d4-a716-446655440000",
                "name_technical": "Кирпич керамический М150",
                "brand": "ЛСР",
                "manufacturer": "Группа ЛСР",
                "sku": "123456",
                "description": "Керамический кирпич...",
                "category": {"id": 10, "name": "Кирпич", "path": ["Стройматериалы", "Кирпич"]},
                "attributes": [
                    {"name": "Марка прочности", "value": "М150", "unit": None},
                    {"name": "Вес", "value": "3.5", "unit": "кг"},
                ],
                "price": {"value": "15.50", "currency": "RUB", "unit": "шт"},
                "availability": {"in_stock": True, "quantity": 5000, "delivery_days": 2},
                "images": [],
                "documents": [],
                "source": {
                    "name": "petrovich.ru",
                    "url": "https://moscow.petrovich.ru/product/...",
                    "external_id": "789012",
                },
                "enrichment_status": "enriched",
                "quality_score": 0.85,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T12:00:00Z",
            }
        }


# Pagination DTOs
class PaginationInfo(BaseModel):
    """Pagination metadata."""

    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    total_items: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")

    class Config:
        json_schema_extra = {
            "example": {"page": 1, "per_page": 20, "total_items": 1543, "total_pages": 78}
        }


class PaginatedResponse(BaseModel):
    """Paginated list of products."""

    data: List[ProductListItem] = Field(..., description="List of products")
    pagination: PaginationInfo = Field(..., description="Pagination information")


# Search DTOs
class SearchFilters(BaseModel):
    """Search filters."""

    category_id: Optional[int] = Field(None, description="Filter by category")
    min_price: Optional[Decimal] = Field(None, description="Minimum price")
    max_price: Optional[Decimal] = Field(None, description="Maximum price")
    in_stock: Optional[bool] = Field(None, description="Only in stock")
    brand: Optional[str] = Field(None, description="Filter by brand")
    source_name: Optional[str] = Field(None, description="Filter by source")
    enrichment_status: Optional[str] = Field(None, description="Filter by enrichment status")

    class Config:
        json_schema_extra = {
            "example": {
                "category_id": 10,
                "min_price": "10.00",
                "max_price": "50.00",
                "in_stock": True,
            }
        }


class SearchRequest(BaseModel):
    """Full-text search request."""

    query: str = Field(..., min_length=1, description="Search query")
    filters: Optional[SearchFilters] = Field(None, description="Optional filters")
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(20, ge=1, le=100, description="Items per page")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "кирпич керамический М150",
                "filters": {
                    "category_id": 10,
                    "min_price": "10.00",
                    "max_price": "50.00",
                    "in_stock": True,
                },
                "page": 1,
                "per_page": 20,
            }
        }
