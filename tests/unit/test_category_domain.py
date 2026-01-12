"""
Unit tests for category domain entities.
"""
import pytest
from decimal import Decimal

from internal.domain.category import (
    Category,
    CategoryMapping,
    CategoryTreeNode,
    MappingSuggestion,
)


class TestCategory:
    """Tests for Category entity."""

    def test_create_valid_category(self):
        """Test creating a valid category."""
        category = Category(
            id=1,
            parent_id=None,
            name="Стройматериалы",
            slug="stroymaterialy",
            level=1,
            path_ids=[1],
            path_names=["Стройматериалы"],
        )

        assert category.id == 1
        assert category.parent_id is None
        assert category.name == "Стройматериалы"
        assert category.slug == "stroymaterialy"
        assert category.level == 1
        assert category.path_ids == [1]
        assert category.path_names == ["Стройматериалы"]
        assert category.product_count == 0

    def test_create_child_category(self):
        """Test creating a child category."""
        category = Category(
            id=10,
            parent_id=1,
            name="Кирпич",
            slug="kirpich",
            level=2,
            path_ids=[1, 10],
            path_names=["Стройматериалы", "Кирпич"],
        )

        assert category.parent_id == 1
        assert category.level == 2
        assert len(category.path_ids) == 2
        assert len(category.path_names) == 2

    def test_to_dict(self):
        """Test converting category to dictionary."""
        category = Category(
            id=1,
            parent_id=None,
            name="Стройматериалы",
            slug="stroymaterialy",
            level=1,
            path_ids=[1],
            path_names=["Стройматериалы"],
            product_count=42,
        )

        result = category.to_dict()

        assert result["id"] == 1
        assert result["parent_id"] is None
        assert result["name"] == "Стройматериалы"
        assert result["slug"] == "stroymaterialy"
        assert result["product_count"] == 42
        assert "created_at" in result
        assert "updated_at" in result


class TestCategoryMapping:
    """Tests for CategoryMapping entity."""

    def test_create_valid_mapping(self):
        """Test creating a valid category mapping."""
        mapping = CategoryMapping(
            id=1,
            source_name="petrovich.ru",
            source_path=["Стройматериалы", "Кирпич"],
            source_path_hash="abc123",
            category_id=10,
            confidence=Decimal("0.95"),
            is_manual=True,
        )

        assert mapping.id == 1
        assert mapping.source_name == "petrovich.ru"
        assert mapping.source_path == ["Стройматериалы", "Кирпич"]
        assert mapping.category_id == 10
        assert mapping.confidence == Decimal("0.95")
        assert mapping.is_manual is True

    def test_create_automatic_mapping(self):
        """Test creating an automatic mapping with default values."""
        mapping = CategoryMapping(
            id=2,
            source_name="leroymerlin.ru",
            source_path=["Кирпичи"],
            source_path_hash="def456",
            category_id=10,
        )

        assert mapping.confidence == Decimal("1.0")
        assert mapping.is_manual is False

    def test_to_dict(self):
        """Test converting mapping to dictionary."""
        mapping = CategoryMapping(
            id=1,
            source_name="petrovich.ru",
            source_path=["Стройматериалы", "Кирпич"],
            source_path_hash="abc123",
            category_id=10,
            confidence=Decimal("0.95"),
            is_manual=True,
        )

        result = mapping.to_dict()

        assert result["id"] == 1
        assert result["source_name"] == "petrovich.ru"
        assert result["source_path"] == ["Стройматериалы", "Кирпич"]
        assert result["category_id"] == 10
        assert result["confidence"] == 0.95
        assert result["is_manual"] is True
        assert "created_at" in result


class TestCategoryTreeNode:
    """Tests for CategoryTreeNode entity."""

    def test_create_tree_node(self):
        """Test creating a category tree node."""
        category = Category(
            id=1,
            parent_id=None,
            name="Стройматериалы",
            slug="stroymaterialy",
            level=1,
            path_ids=[1],
            path_names=["Стройматериалы"],
        )

        node = CategoryTreeNode(category=category, children=[])

        assert node.category.id == 1
        assert len(node.children) == 0

    def test_tree_with_children(self):
        """Test building a category tree with children."""
        parent_cat = Category(
            id=1,
            parent_id=None,
            name="Стройматериалы",
            slug="stroymaterialy",
            level=1,
            path_ids=[1],
            path_names=["Стройматериалы"],
        )

        child_cat = Category(
            id=10,
            parent_id=1,
            name="Кирпич",
            slug="kirpich",
            level=2,
            path_ids=[1, 10],
            path_names=["Стройматериалы", "Кирпич"],
        )

        child_node = CategoryTreeNode(category=child_cat, children=[])
        parent_node = CategoryTreeNode(category=parent_cat, children=[child_node])

        assert len(parent_node.children) == 1
        assert parent_node.children[0].category.id == 10

    def test_to_dict_with_children(self):
        """Test converting tree to dictionary."""
        parent_cat = Category(
            id=1,
            parent_id=None,
            name="Стройматериалы",
            slug="stroymaterialy",
            level=1,
            path_ids=[1],
            path_names=["Стройматериалы"],
        )

        child_cat = Category(
            id=10,
            parent_id=1,
            name="Кирпич",
            slug="kirpich",
            level=2,
            path_ids=[1, 10],
            path_names=["Стройматериалы", "Кирпич"],
        )

        child_node = CategoryTreeNode(category=child_cat, children=[])
        parent_node = CategoryTreeNode(category=parent_cat, children=[child_node])

        result = parent_node.to_dict()

        assert result["id"] == 1
        assert len(result["children"]) == 1
        assert result["children"][0]["id"] == 10


class TestMappingSuggestion:
    """Tests for MappingSuggestion entity."""

    def test_create_suggestion(self):
        """Test creating a mapping suggestion."""
        suggestion = MappingSuggestion(
            source_name="petrovich.ru",
            source_path=["Стройматериалы", "Кирпичи"],
            suggested_category_id=10,
            confidence=Decimal("0.85"),
            reason="Fuzzy match on 'Кирпич' synonym",
        )

        assert suggestion.source_name == "petrovich.ru"
        assert suggestion.suggested_category_id == 10
        assert suggestion.confidence == Decimal("0.85")
        assert "Fuzzy match" in suggestion.reason

    def test_to_dict(self):
        """Test converting suggestion to dictionary."""
        suggestion = MappingSuggestion(
            source_name="petrovich.ru",
            source_path=["Стройматериалы", "Кирпичи"],
            suggested_category_id=10,
            confidence=Decimal("0.85"),
            reason="Fuzzy match",
        )

        result = suggestion.to_dict()

        assert result["source_name"] == "petrovich.ru"
        assert result["source_path"] == ["Стройматериалы", "Кирпичи"]
        assert result["suggested_category_id"] == 10
        assert result["confidence"] == 0.85
        assert result["reason"] == "Fuzzy match"
