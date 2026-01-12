"""
Pytest configuration and fixtures.
"""
import asyncio
import pytest
from typing import AsyncGenerator


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def product_data():
    """Sample product data for tests."""
    return {
        "name_technical": "Кирпич М150",
        "category_id": 1,
    }


@pytest.fixture
def enriched_product_data():
    """Sample enriched product data for tests."""
    return {
        "name_technical": "Кирпич М150",
        "category_id": 1,
        "quality_score": 0.85,
        "enrichment_status": "enriched",
    }
