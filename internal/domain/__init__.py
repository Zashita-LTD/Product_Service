"""
Domain package for Product Service.

Contains domain entities, value objects, and domain errors.
"""
from .product import ProductFamily, OutboxEvent
from .value_objects import Price, QualityScore, CategoryId, RequestId
from .errors import (
    DomainError,
    DomainValidationError,
    ProductNotFoundError,
    ProductAlreadyExistsError,
    EnrichmentError,
    CacheError,
    EventPublishError,
)
from .crm import (
    Manufacturer,
    Supplier,
    Person,
    CareerRecord,
    Interaction,
    PartnerStatus,
    SupplierStatus,
    CompanyType,
    InteractionType,
    InteractionDirection,
    SupplierManufacturer,
)

__all__ = [
    "ProductFamily",
    "OutboxEvent",
    "Price",
    "QualityScore",
    "CategoryId",
    "RequestId",
    "DomainError",
    "DomainValidationError",
    "ProductNotFoundError",
    "ProductAlreadyExistsError",
    "EnrichmentError",
    "CacheError",
    # CRM
    "Manufacturer",
    "Supplier",
    "Person",
    "CareerRecord",
    "Interaction",
    "PartnerStatus",
    "SupplierStatus",
    "CompanyType",
    "InteractionType",
    "InteractionDirection",
    "SupplierManufacturer",
    "EventPublishError",
]
