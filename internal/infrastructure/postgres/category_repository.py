"""
PostgreSQL Category Repository.

Implements the repository pattern for Category persistence with asyncpg.
"""

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Optional

import asyncpg
from asyncpg import Pool

from internal.domain.category import Category, CategoryMapping


class PostgresCategoryRepository:
    """
    PostgreSQL implementation of the Category Repository.

    Uses asyncpg for async database operations.
    """

    def __init__(self, pool: Pool) -> None:
        """
        Initialize the repository.

        Args:
            pool: asyncpg connection pool.
        """
        self._pool = pool

    async def get_by_id(self, category_id: int) -> Optional[Category]:
        """
        Get a category by ID.

        Args:
            category_id: The ID of the category.

        Returns:
            Category if found, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, parent_id, name, slug, level, path_ids, path_names,
                       product_count, created_at, updated_at
                FROM categories
                WHERE id = $1
                """,
                category_id,
            )

            if not row:
                return None

            return self._row_to_entity(row)

    async def get_by_slug(self, slug: str) -> Optional[Category]:
        """
        Get a category by slug.

        Args:
            slug: The slug of the category.

        Returns:
            Category if found, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, parent_id, name, slug, level, path_ids, path_names,
                       product_count, created_at, updated_at
                FROM categories
                WHERE slug = $1
                """,
                slug,
            )

            if not row:
                return None

            return self._row_to_entity(row)

    async def get_children(self, parent_id: int) -> list[Category]:
        """
        Get child categories of a parent category.

        Args:
            parent_id: The ID of the parent category.

        Returns:
            List of child categories.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, parent_id, name, slug, level, path_ids, path_names,
                       product_count, created_at, updated_at
                FROM categories
                WHERE parent_id = $1
                ORDER BY name
                """,
                parent_id,
            )

            return [self._row_to_entity(row) for row in rows]

    async def get_tree(self) -> list[Category]:
        """
        Get all categories (for building tree).

        Returns:
            List of all categories.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, parent_id, name, slug, level, path_ids, path_names,
                       product_count, created_at, updated_at
                FROM categories
                ORDER BY level, name
                """
            )

            return [self._row_to_entity(row) for row in rows]

    async def create(self, category: Category) -> Category:
        """
        Create a new category.

        Args:
            category: The category to create.

        Returns:
            The created category with assigned ID.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO categories (
                    parent_id, name, slug, level, path_ids, path_names,
                    product_count, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id, parent_id, name, slug, level, path_ids, path_names,
                          product_count, created_at, updated_at
                """,
                category.parent_id,
                category.name,
                category.slug,
                category.level,
                category.path_ids,
                category.path_names,
                category.product_count,
                category.created_at,
                category.updated_at,
            )

            return self._row_to_entity(row)

    async def find_mapping(self, source_name: str, source_path: list[str]) -> Optional[int]:
        """
        Find category ID by source mapping.

        Args:
            source_name: Name of the source (e.g., petrovich.ru).
            source_path: Original breadcrumb path from the source.

        Returns:
            Category ID if mapping found, None otherwise.
        """
        source_path_hash = self._hash_source_path(source_path)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT category_id
                FROM category_mappings
                WHERE source_name = $1 AND source_path_hash = $2
                """,
                source_name,
                source_path_hash,
            )

            return row["category_id"] if row else None

    async def create_mapping(self, mapping: CategoryMapping) -> CategoryMapping:
        """
        Create a new category mapping.

        Args:
            mapping: The category mapping to create.

        Returns:
            The created category mapping with assigned ID.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO category_mappings (
                    source_name, source_path, source_path_hash, category_id,
                    confidence, is_manual, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, source_name, source_path, source_path_hash,
                          category_id, confidence, is_manual, created_at
                """,
                mapping.source_name,
                mapping.source_path,
                mapping.source_path_hash,
                mapping.category_id,
                float(mapping.confidence),
                mapping.is_manual,
                mapping.created_at,
            )

            return self._row_to_mapping(row)

    async def increment_product_count(self, category_id: int) -> None:
        """
        Increment the product count for a category.

        Args:
            category_id: The ID of the category.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE categories
                SET product_count = product_count + 1,
                    updated_at = $2
                WHERE id = $1
                """,
                category_id,
                datetime.utcnow(),
            )

    def _row_to_entity(self, row: asyncpg.Record) -> Category:
        """
        Convert a database row to a Category entity.

        Args:
            row: Database row.

        Returns:
            Category entity.
        """
        return Category(
            id=row["id"],
            parent_id=row["parent_id"],
            name=row["name"],
            slug=row["slug"],
            level=row["level"],
            path_ids=list(row["path_ids"]),
            path_names=list(row["path_names"]),
            product_count=row["product_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_mapping(self, row: asyncpg.Record) -> CategoryMapping:
        """
        Convert a database row to a CategoryMapping entity.

        Args:
            row: Database row.

        Returns:
            CategoryMapping entity.
        """
        return CategoryMapping(
            id=row["id"],
            source_name=row["source_name"],
            source_path=list(row["source_path"]),
            source_path_hash=row["source_path_hash"],
            category_id=row["category_id"],
            confidence=Decimal(str(row["confidence"])),
            is_manual=row["is_manual"],
            created_at=row["created_at"],
        )

    def _hash_source_path(self, source_path: list[str]) -> str:
        """
        Generate SHA256 hash of source path for fast lookup.

        Args:
            source_path: List of category names from source.

        Returns:
            SHA256 hash as hex string.
        """
        path_str = "|".join(source_path)
        return hashlib.sha256(path_str.encode("utf-8")).hexdigest()
