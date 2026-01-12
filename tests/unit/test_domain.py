"""
Unit tests for domain entities.
"""
import pytest
from decimal import Decimal
from uuid import uuid4

from internal.domain.product import ProductFamily, OutboxEvent
from internal.domain.value_objects import Price, QualityScore
from internal.domain.errors import DomainValidationError


class TestProductFamily:
    """Tests for ProductFamily entity."""
    
    def test_create_valid_product(self):
        """Test creating a valid product family."""
        product = ProductFamily(
            name_technical="Кирпич М150",
            category_id=1,
        )
        
        assert product.name_technical == "Кирпич М150"
        assert product.category_id == 1
        assert product.enrichment_status == "pending"
        assert product.uuid is not None
    
    def test_create_product_with_empty_name_raises_error(self):
        """Test that empty name raises validation error."""
        with pytest.raises(DomainValidationError) as exc_info:
            ProductFamily(
                name_technical="",
                category_id=1,
            )
        
        assert "name_technical is required" in str(exc_info.value)
    
    def test_create_product_with_invalid_category_raises_error(self):
        """Test that invalid category raises validation error."""
        with pytest.raises(DomainValidationError) as exc_info:
            ProductFamily(
                name_technical="Test Product",
                category_id=0,
            )
        
        assert "category_id must be positive" in str(exc_info.value)
    
    def test_enrich_product(self):
        """Test enriching a product family."""
        product = ProductFamily(
            name_technical="Test Product",
            category_id=1,
        )
        
        product.enrich(quality_score=Decimal("0.85"))
        
        assert product.enrichment_status == "enriched"
        assert product.quality_score.value == Decimal("0.85")
    
    def test_mark_enrichment_failed(self):
        """Test marking enrichment as failed."""
        product = ProductFamily(
            name_technical="Test Product",
            category_id=1,
        )
        
        product.mark_enrichment_failed()
        
        assert product.enrichment_status == "enrichment_failed"
    
    def test_to_dict(self):
        """Test converting product to dictionary."""
        product = ProductFamily(
            name_technical="Test Product",
            category_id=1,
        )
        
        result = product.to_dict()
        
        assert result["name_technical"] == "Test Product"
        assert result["category_id"] == 1
        assert "uuid" in result
        assert "created_at" in result


class TestPrice:
    """Tests for Price value object."""
    
    def test_create_valid_price(self):
        """Test creating a valid price."""
        price = Price(
            amount=Decimal("1500.00"),
            currency="RUB",
            supplier_id=1,
        )
        
        assert price.amount == Decimal("1500.00")
        assert price.currency == "RUB"
        assert price.supplier_id == 1
    
    def test_create_price_with_negative_amount_raises_error(self):
        """Test that negative amount raises validation error."""
        with pytest.raises(DomainValidationError) as exc_info:
            Price(
                amount=Decimal("-100.00"),
                currency="RUB",
            )
        
        assert "cannot be negative" in str(exc_info.value)
    
    def test_create_price_with_invalid_currency_raises_error(self):
        """Test that invalid currency raises validation error."""
        with pytest.raises(DomainValidationError) as exc_info:
            Price(
                amount=Decimal("100.00"),
                currency="INVALID",
            )
        
        assert "3-letter ISO code" in str(exc_info.value)


class TestQualityScore:
    """Tests for QualityScore value object."""
    
    def test_create_valid_quality_score(self):
        """Test creating a valid quality score."""
        score = QualityScore(value=Decimal("0.85"))
        
        assert score.value == Decimal("0.85")
        assert score.grade == "B"
    
    def test_quality_score_grades(self):
        """Test quality score grading."""
        assert QualityScore(value=Decimal("0.95")).grade == "A"
        assert QualityScore(value=Decimal("0.85")).grade == "B"
        assert QualityScore(value=Decimal("0.75")).grade == "C"
        assert QualityScore(value=Decimal("0.65")).grade == "D"
        assert QualityScore(value=Decimal("0.50")).grade == "F"
    
    def test_create_quality_score_out_of_range_raises_error(self):
        """Test that out of range score raises validation error."""
        with pytest.raises(DomainValidationError):
            QualityScore(value=Decimal("1.50"))
        
        with pytest.raises(DomainValidationError):
            QualityScore(value=Decimal("-0.10"))


class TestOutboxEvent:
    """Tests for OutboxEvent entity."""
    
    def test_create_outbox_event(self):
        """Test creating an outbox event."""
        product_uuid = uuid4()
        
        event = OutboxEvent(
            aggregate_type="product_family",
            aggregate_id=product_uuid,
            event_type="product_family.created",
            payload={"name": "Test"},
        )
        
        assert event.aggregate_type == "product_family"
        assert event.aggregate_id == product_uuid
        assert event.event_type == "product_family.created"
        assert event.processed_at is None
    
    def test_mark_event_processed(self):
        """Test marking an event as processed."""
        event = OutboxEvent(
            aggregate_type="product_family",
            aggregate_id=uuid4(),
            event_type="product_family.created",
            payload={},
        )
        
        event.mark_processed()
        
        assert event.processed_at is not None
