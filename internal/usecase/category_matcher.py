"""
Category Matcher for fuzzy matching and automatic category mapping.

Provides fuzzy matching capabilities to map source categories to unified taxonomy.
"""
import re
from decimal import Decimal
from typing import Optional

from internal.domain.category import Category


class CategoryMatcher:
    """
    Fuzzy matching for automatic category mapping.

    Uses synonym dictionaries and similarity scoring to find best matches.
    """

    # Словарь синонимов для категорий
    SYNONYMS = {
        "кирпич": ["кирпичи", "кирпичный", "brick"],
        "цемент": ["cement", "цементный"],
        "бетон": ["бетонный", "concrete"],
        "блок": ["блоки", "block", "blocks"],
        "инструмент": ["инструменты", "tools", "tool"],
        "электрика": ["электрический", "электро", "electric", "electrical"],
        "сантехника": ["сантехнический", "plumbing"],
        "отделка": ["отделочный", "отделочные", "finishing"],
        "керамический": ["керамика", "ceramic"],
        "силикатный": ["силикат", "silicate"],
        "облицовочный": ["облицовка", "facing"],
    }

    # Минимальный порог уверенности для автоматического маппинга
    MIN_CONFIDENCE_THRESHOLD = Decimal("0.70")

    def __init__(self) -> None:
        """Initialize the category matcher."""
        # Предкомпилированные регулярные выражения для нормализации
        self._whitespace_re = re.compile(r"\s+")
        self._non_alpha_re = re.compile(r"[^а-яёa-z0-9\s]")

    async def find_best_match(
        self,
        source_path: list[str],
        existing_categories: list[Category],
    ) -> Optional[tuple[int, Decimal]]:
        """
        Find best matching category for a source path.

        Args:
            source_path: Source category path (breadcrumb).
            existing_categories: List of existing categories to match against.

        Returns:
            Tuple of (category_id, confidence) if match found, None otherwise.
        """
        if not source_path or not existing_categories:
            return None

        best_match_id: Optional[int] = None
        best_score = Decimal("0.0")

        for category in existing_categories:
            score = self._calculate_similarity(source_path, category.path_names)

            if score > best_score:
                best_score = score
                best_match_id = category.id

        # Возвращаем только если уверенность выше порога
        if best_score >= self.MIN_CONFIDENCE_THRESHOLD and best_match_id:
            return (best_match_id, best_score)

        return None

    def _calculate_similarity(
        self, path1: list[str], path2: list[str]
    ) -> Decimal:
        """
        Calculate similarity score between two category paths.

        Uses:
        - Exact match scoring
        - Synonym matching
        - Partial match scoring
        - Path length penalty

        Args:
            path1: First category path.
            path2: Second category path.

        Returns:
            Similarity score from 0.0 to 1.0.
        """
        if not path1 or not path2:
            return Decimal("0.0")

        # Normalize paths
        norm_path1 = [self._normalize(p) for p in path1]
        norm_path2 = [self._normalize(p) for p in path2]

        # Exact match gives perfect score
        if norm_path1 == norm_path2:
            return Decimal("1.0")

        # Calculate score based on matching levels
        total_score = Decimal("0.0")
        max_len = max(len(norm_path1), len(norm_path2))
        min_len = min(len(norm_path1), len(norm_path2))

        # Compare each level
        for i in range(min_len):
            term1 = norm_path1[i]
            term2 = norm_path2[i]

            # Exact match at this level
            if term1 == term2:
                # Higher weight for matching at deeper levels
                level_weight = Decimal(str(1.0 / (i + 1)))
                total_score += level_weight
            # Synonym match
            elif self._are_synonyms(term1, term2):
                level_weight = Decimal(str(0.8 / (i + 1)))
                total_score += level_weight
            # Partial match (one contains the other)
            elif term1 in term2 or term2 in term1:
                level_weight = Decimal(str(0.5 / (i + 1)))
                total_score += level_weight

        # Normalize score by path length (penalize very different lengths)
        length_penalty = Decimal(str(min_len / max_len))
        final_score = (total_score / Decimal(str(min_len))) * length_penalty

        # Clamp to [0.0, 1.0]
        return min(max(final_score, Decimal("0.0")), Decimal("1.0"))

    def _normalize(self, text: str) -> str:
        """
        Normalize text for comparison.

        - Convert to lowercase
        - Remove non-alphanumeric characters
        - Normalize whitespace

        Args:
            text: Text to normalize.

        Returns:
            Normalized text.
        """
        # Convert to lowercase
        text = text.lower()

        # Remove non-alphanumeric characters (except spaces)
        text = self._non_alpha_re.sub("", text)

        # Normalize whitespace
        text = self._whitespace_re.sub(" ", text)

        return text.strip()

    def _are_synonyms(self, term1: str, term2: str) -> bool:
        """
        Check if two terms are synonyms.

        Args:
            term1: First term.
            term2: Second term.

        Returns:
            True if terms are synonyms, False otherwise.
        """
        # Check if term1 is a key and term2 is in its synonyms
        if term1 in self.SYNONYMS:
            if term2 in self.SYNONYMS[term1] or term2 == term1:
                return True

        # Check if term2 is a key and term1 is in its synonyms
        if term2 in self.SYNONYMS:
            if term1 in self.SYNONYMS[term2] or term1 == term2:
                return True

        # Check if both are in the same synonym group
        for key, synonyms in self.SYNONYMS.items():
            all_terms = [key] + synonyms
            if term1 in all_terms and term2 in all_terms:
                return True

        return False
