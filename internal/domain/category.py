"""
Domain model for Category.

This module contains category-related domain entities following DDD principles.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class Category:
    """
    Category entity representing a node in the unified category taxonomy.

    Attributes:
        id: Unique identifier for the category.
        parent_id: ID of the parent category (None for root categories).
        name: Human-readable category name.
        slug: URL-friendly identifier.
        level: Category level in the hierarchy (0=root, 1=L1, 2=L2, 3=L3).
        path_ids: Materialized path as list of category IDs [1, 5, 23].
        path_names: Materialized path as list of category names.
        product_count: Number of products in this category.
        created_at: Timestamp of creation.
        updated_at: Timestamp of last update.
    """

    id: int
    parent_id: Optional[int]
    name: str
    slug: str
    level: int
    path_ids: list[int]
    path_names: list[str]
    product_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """
        Convert to dictionary representation.

        Returns:
            Dictionary with all category data.
        """
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "name": self.name,
            "slug": self.slug,
            "level": self.level,
            "path_ids": self.path_ids,
            "path_names": self.path_names,
            "product_count": self.product_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class CategoryMapping:
    """
    CategoryMapping entity for mapping source categories to unified taxonomy.

    Attributes:
        id: Unique identifier for the mapping.
        source_name: Name of the source (e.g., petrovich.ru, leroymerlin.ru).
        source_path: Original breadcrumb path from the source.
        source_path_hash: SHA256 hash of source_path for fast lookup.
        category_id: ID of the unified category this maps to.
        confidence: Confidence score for AI-based mappings (0.0-1.0).
        is_manual: Whether this is a manual or automatic mapping.
        created_at: Timestamp of creation.
    """

    id: int
    source_name: str
    source_path: list[str]
    source_path_hash: str
    category_id: int
    confidence: Decimal = Decimal("1.0")
    is_manual: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """
        Convert to dictionary representation.

        Returns:
            Dictionary with all mapping data.
        """
        return {
            "id": self.id,
            "source_name": self.source_name,
            "source_path": self.source_path,
            "source_path_hash": self.source_path_hash,
            "category_id": self.category_id,
            "confidence": float(self.confidence),
            "is_manual": self.is_manual,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class CategoryTreeNode:
    """
    CategoryTreeNode for UI representation of category hierarchy.

    Attributes:
        category: The category entity.
        children: List of child category tree nodes.
    """

    category: Category
    children: list["CategoryTreeNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        """
        Convert to dictionary representation.

        Returns:
            Nested dictionary with category and children.
        """
        return {
            **self.category.to_dict(),
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class MappingSuggestion:
    """
    MappingSuggestion for suggesting category mappings.

    Attributes:
        source_name: Name of the source.
        source_path: Original breadcrumb path from the source.
        suggested_category_id: Suggested unified category ID.
        confidence: Confidence score for the suggestion (0.0-1.0).
        reason: Human-readable reason for the suggestion.
    """

    source_name: str
    source_path: list[str]
    suggested_category_id: int
    confidence: Decimal
    reason: str

    def to_dict(self) -> dict:
        """
        Convert to dictionary representation.

        Returns:
            Dictionary with suggestion data.
        """
        return {
            "source_name": self.source_name,
            "source_path": self.source_path,
            "suggested_category_id": self.suggested_category_id,
            "confidence": float(self.confidence),
            "reason": self.reason,
        }
