"""
Category Service Use Case.

Provides business logic for category management and mapping.
"""

import hashlib
from decimal import Decimal
from typing import Optional

from internal.domain.category import (
    Category,
    CategoryMapping,
    CategoryTreeNode,
    MappingSuggestion,
)
from internal.infrastructure.postgres.category_repository import (
    PostgresCategoryRepository,
)
from internal.usecase.category_matcher import CategoryMatcher
from pkg.logger.logger import get_logger

logger = get_logger(__name__)


class CategoryService:
    """
    Service for category operations and automatic mapping.

    This service:
    1. Resolves source categories to unified taxonomy
    2. Creates automatic mappings using fuzzy matching
    3. Manages category hierarchy
    """

    def __init__(
        self,
        repository: PostgresCategoryRepository,
        matcher: Optional[CategoryMatcher] = None,
    ) -> None:
        """
        Initialize the category service.

        Args:
            repository: Category repository instance.
            matcher: Category matcher for fuzzy matching (optional).
        """
        self._repository = repository
        self._matcher = matcher or CategoryMatcher()

    async def resolve_category(self, source_name: str, source_path: list[str]) -> int:
        """
        Resolve category ID from source path.

        Process:
        1. Check for existing mapping
        2. If not found, try fuzzy matching against existing categories
        3. If no good match, create new category
        4. Save mapping for future use

        Args:
            source_name: Name of the source (e.g., petrovich.ru).
            source_path: Category breadcrumb from source.

        Returns:
            Category ID (existing or newly created).
        """
        if not source_path:
            logger.warning("Empty source_path provided", source_name=source_name)
            return 1  # Default to root category

        # 1. Check for existing mapping
        category_id = await self._repository.find_mapping(source_name, source_path)
        if category_id:
            logger.debug(
                "Found existing category mapping",
                source_name=source_name,
                source_path=source_path,
                category_id=category_id,
            )
            return category_id

        # 2. Try fuzzy matching
        existing_categories = await self._repository.get_tree()
        match_result = await self._matcher.find_best_match(source_path, existing_categories)

        if match_result:
            category_id, confidence = match_result
            logger.info(
                "Found fuzzy match for category",
                source_name=source_name,
                source_path=source_path,
                category_id=category_id,
                confidence=float(confidence),
            )

            # Save mapping for future use
            await self._create_mapping(
                source_name=source_name,
                source_path=source_path,
                category_id=category_id,
                confidence=confidence,
                is_manual=False,
            )

            return category_id

        # 3. No good match found, use default category
        # In production, this could create a new category or queue for manual review
        default_category_id = 1  # Default to root category

        logger.info(
            "No fuzzy match found, using default category",
            source_name=source_name,
            source_path=source_path,
            default_category_id=default_category_id,
        )

        # Save mapping with low confidence
        await self._create_mapping(
            source_name=source_name,
            source_path=source_path,
            category_id=default_category_id,
            confidence=Decimal("0.5"),
            is_manual=False,
        )

        return default_category_id

    async def get_category_tree(self) -> list[CategoryTreeNode]:
        """
        Get category hierarchy as tree structure.

        Returns:
            List of root category tree nodes with nested children.
        """
        all_categories = await self._repository.get_tree()

        # Build lookup map
        category_map: dict[int, CategoryTreeNode] = {}
        for cat in all_categories:
            category_map[cat.id] = CategoryTreeNode(category=cat, children=[])

        # Build tree structure
        roots: list[CategoryTreeNode] = []
        for node in category_map.values():
            if node.category.parent_id is None:
                roots.append(node)
            else:
                parent = category_map.get(node.category.parent_id)
                if parent:
                    parent.children.append(node)

        return roots

    async def merge_categories(self, source_id: int, target_id: int) -> None:
        """
        Merge two categories (manual operation).

        This would typically:
        1. Move all products from source to target
        2. Update all mappings to point to target
        3. Delete or archive source category

        Args:
            source_id: ID of category to merge from.
            target_id: ID of category to merge into.
        """
        # This is a placeholder for future implementation
        logger.warning(
            "Category merge not yet implemented",
            source_id=source_id,
            target_id=target_id,
        )
        raise NotImplementedError("Category merge not yet implemented")

    async def suggest_mappings(self, source_name: str) -> list[MappingSuggestion]:
        """
        Suggest category mappings for unmapped source categories.

        This would typically:
        1. Find all unique source paths without mappings
        2. Run fuzzy matching for each
        3. Return suggestions for manual review

        Args:
            source_name: Name of the source to generate suggestions for.

        Returns:
            List of mapping suggestions.
        """
        # This is a placeholder for future implementation
        logger.warning("Suggest mappings not yet implemented", source_name=source_name)
        return []

    async def get_by_id(self, category_id: int) -> Optional[Category]:
        """
        Get category by ID.

        Args:
            category_id: The ID of the category.

        Returns:
            Category if found, None otherwise.
        """
        return await self._repository.get_by_id(category_id)

    async def increment_product_count(self, category_id: int) -> None:
        """
        Increment product count for a category.

        Args:
            category_id: The ID of the category.
        """
        await self._repository.increment_product_count(category_id)

    async def _create_mapping(
        self,
        source_name: str,
        source_path: list[str],
        category_id: int,
        confidence: Decimal,
        is_manual: bool,
    ) -> CategoryMapping:
        """
        Create a new category mapping.

        Args:
            source_name: Name of the source.
            source_path: Category path from source.
            category_id: Unified category ID.
            confidence: Confidence score.
            is_manual: Whether this is a manual mapping.

        Returns:
            Created category mapping.
        """
        source_path_hash = self._hash_source_path(source_path)

        mapping = CategoryMapping(
            id=0,  # Will be assigned by database
            source_name=source_name,
            source_path=source_path,
            source_path_hash=source_path_hash,
            category_id=category_id,
            confidence=confidence,
            is_manual=is_manual,
        )

        try:
            return await self._repository.create_mapping(mapping)
        except Exception as e:
            # Handle duplicate mapping (concurrent creation)
            logger.warning(
                "Failed to create mapping (may already exist)",
                source_name=source_name,
                source_path=source_path,
                error=str(e),
            )
            # Re-fetch the mapping
            existing_id = await self._repository.find_mapping(source_name, source_path)
            if existing_id:
                mapping.category_id = existing_id
            return mapping

    def _hash_source_path(self, source_path: list[str]) -> str:
        """
        Generate SHA256 hash of source path.

        Args:
            source_path: List of category names from source.

        Returns:
            SHA256 hash as hex string.
        """
        path_str = "|".join(source_path)
        return hashlib.sha256(path_str.encode("utf-8")).hexdigest()
