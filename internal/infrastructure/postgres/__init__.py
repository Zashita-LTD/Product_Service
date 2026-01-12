"""
PostgreSQL infrastructure package.
"""
from .repository import PostgresProductRepository, create_pool

__all__ = ["PostgresProductRepository", "create_pool"]
