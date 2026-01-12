"""
Unit tests for category service and matcher.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from internal.domain.category import Category
from internal.usecase.category_matcher import CategoryMatcher
from internal.usecase.category_service import CategoryService


class TestCategoryMatcher:
    """Tests for CategoryMatcher fuzzy matching."""

    @pytest.fixture
    def matcher(self):
        """Create category matcher instance."""
        return CategoryMatcher()

    @pytest.fixture
    def sample_categories(self):
        """Sample categories for testing."""
        return [
            Category(
                id=10,
                parent_id=1,
                name="Кирпич",
                slug="kirpich",
                level=2,
                path_ids=[1, 10],
                path_names=["Стройматериалы", "Кирпич"],
            ),
            Category(
                id=100,
                parent_id=10,
                name="Керамический кирпич",
                slug="keramicheskiy-kirpich",
                level=3,
                path_ids=[1, 10, 100],
                path_names=["Стройматериалы", "Кирпич", "Керамический кирпич"],
            ),
        ]

    def test_normalize_text(self, matcher):
        """Test text normalization."""
        assert matcher._normalize("Кирпич М150") == "кирпич м150"
        assert matcher._normalize("  Цемент  ") == "цемент"
        assert matcher._normalize("Блок-2000") == "блок2000"

    def test_are_synonyms(self, matcher):
        """Test synonym detection."""
        assert matcher._are_synonyms("кирпич", "кирпичи")
        assert matcher._are_synonyms("кирпичи", "кирпич")
        assert matcher._are_synonyms("цемент", "cement")
        assert not matcher._are_synonyms("кирпич", "цемент")

    def test_exact_match(self, matcher):
        """Test exact path matching."""
        path1 = ["Стройматериалы", "Кирпич"]
        path2 = ["Стройматериалы", "Кирпич"]

        score = matcher._calculate_similarity(path1, path2)
        assert score == Decimal("1.0")

    def test_synonym_match(self, matcher):
        """Test synonym-based matching."""
        path1 = ["Стройматериалы", "Кирпич"]
        path2 = ["Стройматериалы", "Кирпичи"]

        score = matcher._calculate_similarity(path1, path2)
        assert score >= Decimal("0.7")  # Should have high confidence

    def test_no_match(self, matcher):
        """Test no matching."""
        path1 = ["Стройматериалы", "Кирпич"]
        path2 = ["Электрика", "Провода"]

        score = matcher._calculate_similarity(path1, path2)
        assert score < Decimal("0.5")  # Should have low confidence

    @pytest.mark.asyncio
    async def test_find_best_match_exact(self, matcher, sample_categories):
        """Test finding best match with exact match."""
        source_path = ["Стройматериалы", "Кирпич"]

        result = await matcher.find_best_match(source_path, sample_categories)

        assert result is not None
        category_id, confidence = result
        assert category_id == 10
        assert confidence == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_find_best_match_fuzzy(self, matcher, sample_categories):
        """Test finding best match with fuzzy matching."""
        source_path = ["Стройматериалы", "Кирпичи"]

        result = await matcher.find_best_match(source_path, sample_categories)

        assert result is not None
        category_id, confidence = result
        assert category_id == 10
        assert confidence >= Decimal("0.7")

    @pytest.mark.asyncio
    async def test_find_best_match_no_match(self, matcher, sample_categories):
        """Test when no good match is found."""
        source_path = ["Электрика", "Провода"]

        result = await matcher.find_best_match(source_path, sample_categories)

        assert result is None  # No match above threshold


class TestCategoryService:
    """Tests for CategoryService."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock category repository."""
        repo = AsyncMock()
        return repo

    @pytest.fixture
    def mock_matcher(self):
        """Create mock category matcher."""
        matcher = AsyncMock(spec=CategoryMatcher)
        return matcher

    @pytest.fixture
    def service(self, mock_repository, mock_matcher):
        """Create category service instance."""
        return CategoryService(
            repository=mock_repository,
            matcher=mock_matcher,
        )

    @pytest.mark.asyncio
    async def test_resolve_category_with_existing_mapping(self, service, mock_repository):
        """Test resolving category with existing mapping."""
        # Setup
        mock_repository.find_mapping.return_value = 10

        # Execute
        result = await service.resolve_category(
            source_name="petrovich.ru",
            source_path=["Стройматериалы", "Кирпич"],
        )

        # Assert
        assert result == 10
        mock_repository.find_mapping.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_category_with_fuzzy_match(self, service, mock_repository, mock_matcher):
        """Test resolving category with fuzzy matching."""
        # Setup
        mock_repository.find_mapping.return_value = None
        mock_repository.get_tree.return_value = []
        mock_matcher.find_best_match.return_value = (10, Decimal("0.85"))
        mock_repository.create_mapping.return_value = Mock()

        # Execute
        result = await service.resolve_category(
            source_name="petrovich.ru",
            source_path=["Стройматериалы", "Кирпичи"],
        )

        # Assert
        assert result == 10
        mock_matcher.find_best_match.assert_called_once()
        mock_repository.create_mapping.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_category_with_no_match(self, service, mock_repository, mock_matcher):
        """Test resolving category when no fuzzy match found."""
        # Setup
        mock_repository.find_mapping.return_value = None
        mock_repository.get_tree.return_value = []
        mock_matcher.find_best_match.return_value = None
        mock_repository.create_mapping.return_value = Mock()

        # Execute
        result = await service.resolve_category(
            source_name="petrovich.ru",
            source_path=["Unknown", "Category"],
        )

        # Assert
        assert result == 1  # Default category
        mock_repository.create_mapping.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_category_with_empty_path(self, service):
        """Test resolving category with empty path."""
        result = await service.resolve_category(
            source_name="petrovich.ru",
            source_path=[],
        )

        assert result == 1  # Default category

    @pytest.mark.asyncio
    async def test_get_category_tree(self, service, mock_repository):
        """Test building category tree."""
        # Setup
        categories = [
            Category(
                id=1,
                parent_id=None,
                name="Стройматериалы",
                slug="stroymaterialy",
                level=1,
                path_ids=[1],
                path_names=["Стройматериалы"],
            ),
            Category(
                id=10,
                parent_id=1,
                name="Кирпич",
                slug="kirpich",
                level=2,
                path_ids=[1, 10],
                path_names=["Стройматериалы", "Кирпич"],
            ),
        ]
        mock_repository.get_tree.return_value = categories

        # Execute
        result = await service.get_category_tree()

        # Assert
        assert len(result) == 1  # One root
        assert result[0].category.id == 1
        assert len(result[0].children) == 1
        assert result[0].children[0].category.id == 10

    @pytest.mark.asyncio
    async def test_get_by_id(self, service, mock_repository):
        """Test getting category by ID."""
        # Setup
        category = Category(
            id=10,
            parent_id=1,
            name="Кирпич",
            slug="kirpich",
            level=2,
            path_ids=[1, 10],
            path_names=["Стройматериалы", "Кирпич"],
        )
        mock_repository.get_by_id.return_value = category

        # Execute
        result = await service.get_by_id(10)

        # Assert
        assert result is not None
        assert result.id == 10
        mock_repository.get_by_id.assert_called_once_with(10)

    @pytest.mark.asyncio
    async def test_increment_product_count(self, service, mock_repository):
        """Test incrementing product count."""
        # Execute
        await service.increment_product_count(10)

        # Assert
        mock_repository.increment_product_count.assert_called_once_with(10)
