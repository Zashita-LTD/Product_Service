"""
Domain-specific exceptions.

Custom exceptions for domain validation and business rule violations.
"""


class DomainError(Exception):
    """Base exception for domain errors."""
    
    def __init__(self, message: str) -> None:
        """
        Initialize domain error.
        
        Args:
            message: Error message describing the issue.
        """
        self.message = message
        super().__init__(self.message)


class DomainValidationError(DomainError):
    """Exception raised when domain validation fails."""
    pass


class ProductNotFoundError(DomainError):
    """Exception raised when a product is not found."""
    
    def __init__(self, product_id: str) -> None:
        """
        Initialize product not found error.
        
        Args:
            product_id: The ID of the product that was not found.
        """
        super().__init__(f"Product with ID {product_id} not found")
        self.product_id = product_id


class ProductAlreadyExistsError(DomainError):
    """Exception raised when attempting to create a duplicate product."""
    
    def __init__(self, name_technical: str) -> None:
        """
        Initialize product already exists error.
        
        Args:
            name_technical: The technical name that already exists.
        """
        super().__init__(f"Product with name '{name_technical}' already exists")
        self.name_technical = name_technical


class EnrichmentError(DomainError):
    """Exception raised when AI enrichment fails."""
    
    def __init__(self, product_id: str, reason: str) -> None:
        """
        Initialize enrichment error.
        
        Args:
            product_id: The ID of the product that failed enrichment.
            reason: The reason for the failure.
        """
        super().__init__(f"Enrichment failed for product {product_id}: {reason}")
        self.product_id = product_id
        self.reason = reason


class CacheError(DomainError):
    """Exception raised when cache operations fail."""
    pass


class EventPublishError(DomainError):
    """Exception raised when event publishing fails."""
    
    def __init__(self, event_type: str, reason: str) -> None:
        """
        Initialize event publish error.
        
        Args:
            event_type: Type of event that failed to publish.
            reason: The reason for the failure.
        """
        super().__init__(f"Failed to publish event '{event_type}': {reason}")
        self.event_type = event_type
        self.reason = reason
