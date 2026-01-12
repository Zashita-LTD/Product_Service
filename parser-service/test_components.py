#!/usr/bin/env python3
"""
Simple integration test for parser service components.

This script tests that all components can be imported and initialized.
It does NOT run the actual parsing (which requires Kafka and internet access).
"""
import sys
sys.path.insert(0, '/app')

from internal.models.product import (
    RawProduct,
    ProductAttribute,
    ProductAttributeType,
    ProductPrice,
    ProductAvailability,
    AvailabilityStatus,
    ProductImage,
    ProductDocument,
    DocumentType,
)
from config.settings import get_settings
from pkg.logger.logger import setup_logging, get_logger


def test_models():
    """Test Pydantic models."""
    print("Testing models...")
    
    product = RawProduct(
        source_url="https://moscow.petrovich.ru/product/test-123",
        source_name="moscow.petrovich.ru",
        name_original="Тестовый товар",
        sku="TEST-123",
        brand="TestBrand",
        attributes=[
            ProductAttribute(
                name="Вес",
                value="5.5",
                type=ProductAttributeType.UNIT,
                unit="кг"
            ),
        ],
        price=ProductPrice(current=1999.99, currency="RUB"),
        availability=ProductAvailability(status=AvailabilityStatus.IN_STOCK),
    )
    
    message = product.to_kafka_message()
    assert "source_url" in message
    assert message["name_original"] == "Тестовый товар"
    
    print("✓ Models test passed")


def test_config():
    """Test configuration."""
    print("Testing configuration...")
    
    settings = get_settings()
    assert settings.kafka_bootstrap_servers is not None
    assert settings.petrovich_base_url is not None
    assert settings.max_products_per_run > 0
    
    print("✓ Configuration test passed")


def test_logger():
    """Test logger."""
    print("Testing logger...")
    
    setup_logging(level="INFO", json_format=True)
    logger = get_logger("test")
    
    logger.info("Test message", extra={"test_field": "value"})
    
    print("✓ Logger test passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Parser Service Component Tests")
    print("=" * 60)
    
    try:
        test_models()
        test_config()
        test_logger()
        
        print("\n" + "=" * 60)
        print("✓ All component tests passed!")
        print("=" * 60)
        
        print("\nNote: This does not test actual parsing functionality.")
        print("To test full functionality, run the service with:")
        print("  docker-compose up")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
