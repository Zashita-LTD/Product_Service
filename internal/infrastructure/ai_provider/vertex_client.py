"""
Google Vertex AI Client.

Implements AI enrichment with Circuit Breaker pattern for resilience.
"""
import asyncio
from decimal import Decimal
from typing import Optional

from circuitbreaker import circuit, CircuitBreakerError
from google.cloud import aiplatform

from pkg.logger.logger import get_logger


logger = get_logger(__name__)


# Circuit Breaker configuration
FAILURE_THRESHOLD = 5
RECOVERY_TIMEOUT = 60


class VertexAIClient:
    """
    Google Vertex AI client for product enrichment.

    Implements Circuit Breaker pattern to handle AI API failures gracefully.
    """

    def __init__(
        self,
        project_id: str,
        location: str = "us-central1",
        model_id: str = "gemini-2.0-flash-001",
    ) -> None:
        """
        Initialize the Vertex AI client.

        Args:
            project_id: Google Cloud project ID.
            location: Vertex AI location.
            model_id: Model ID to use for predictions.
        """
        self._project_id = project_id
        self._location = location
        self._model_id = model_id
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the Vertex AI client."""
        aiplatform.init(
            project=self._project_id,
            location=self._location,
        )
        self._initialized = True
        logger.info(
            "Vertex AI client initialized",
            project=self._project_id,
            location=self._location,
        )

    @circuit(
        failure_threshold=FAILURE_THRESHOLD,
        recovery_timeout=RECOVERY_TIMEOUT,
    )
    async def calculate_quality_score(
        self,
        name_technical: str,
        category_id: int,
    ) -> Decimal:
        """
        Calculate quality score for a product using AI.

        Uses Google Gemini to analyze product information and calculate
        a quality score based on various factors.

        This method is protected by a Circuit Breaker:
        - Opens after 5 consecutive failures
        - Recovers after 60 seconds

        Args:
            name_technical: Technical name of the product.
            category_id: Category identifier.

        Returns:
            Quality score as Decimal (0.00 - 1.00).

        Raises:
            CircuitBreakerError: If circuit is open due to failures.
        """
        if not self._initialized:
            await self.initialize()

        prompt = self._build_quality_prompt(name_technical, category_id)

        try:
            from vertexai.generative_models import GenerativeModel

            model = GenerativeModel(self._model_id)
            response = await model.generate_content_async(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 100,
                },
            )

            # Parse the response to extract quality score
            score = self._parse_quality_score(response.text)

            logger.info(
                "Quality score calculated",
                name_technical=name_technical,
                score=float(score),
            )

            return score

        except Exception as e:
            logger.error(
                "Failed to calculate quality score",
                name_technical=name_technical,
                error=str(e),
            )
            raise

    def _build_quality_prompt(
        self,
        name_technical: str,
        category_id: int,
    ) -> str:
        """
        Build the prompt for quality score calculation.

        Args:
            name_technical: Technical name of the product.
            category_id: Category identifier.

        Returns:
            Formatted prompt string.
        """
        return f"""
        Analyze the following product and provide a quality score from 0.00 to 1.00.

        Product Name: {name_technical}
        Category ID: {category_id}

        Consider the following factors:
        1. Completeness of the product name
        2. Technical specifications present in the name
        3. Brand recognition (if detectable)
        4. Clarity and specificity

        Respond with ONLY a decimal number between 0.00 and 1.00.
        Example response: 0.85
        """

    def _parse_quality_score(self, response_text: str) -> Decimal:
        """
        Parse quality score from AI response.

        Args:
            response_text: Raw response from AI.

        Returns:
            Parsed quality score as Decimal.
        """
        try:
            # Extract number from response
            text = response_text.strip()
            # Handle common formats: "0.85", "85%", "Quality: 0.85"
            import re
            match = re.search(r"(\d+\.?\d*)", text)
            if match:
                value = float(match.group(1))
                # Handle percentage format
                if value > 1:
                    value = value / 100
                # Clamp to valid range
                value = max(0.0, min(1.0, value))
                return Decimal(str(round(value, 2)))
        except (ValueError, AttributeError):
            pass

        # Default score on parse failure
        logger.warning(
            "Could not parse quality score, using default",
            response=response_text,
        )
        return Decimal("0.50")


class VertexAIClientWithFallback(VertexAIClient):
    """
    Vertex AI client with fallback behavior.

    Returns a default score when Circuit Breaker is open.
    """

    async def calculate_quality_score(
        self,
        name_technical: str,
        category_id: int,
    ) -> Decimal:
        """
        Calculate quality score with fallback.

        Args:
            name_technical: Technical name of the product.
            category_id: Category identifier.

        Returns:
            Quality score, or fallback score if AI is unavailable.
        """
        try:
            return await super().calculate_quality_score(
                name_technical=name_technical,
                category_id=category_id,
            )
        except CircuitBreakerError:
            logger.warning(
                "Circuit breaker open, returning fallback score",
                name_technical=name_technical,
            )
            # Return a neutral fallback score
            return Decimal("0.50")
        except Exception as e:
            logger.error(
                "AI enrichment failed, returning fallback score",
                name_technical=name_technical,
                error=str(e),
            )
            return Decimal("0.50")


class VertexAIEmbeddingClient:
    """Client for generating semantic embeddings via Vertex AI."""

    def __init__(
        self,
        project_id: str,
        location: str = "us-central1",
        model_id: str = "text-embedding-004",
    ) -> None:
        self._project_id = project_id
        self._location = location
        self._model_id = model_id
        self._initialized = False
        self._model: Optional["TextEmbeddingModel"] = None

    async def initialize(self) -> None:
        """Initialize Vertex AI client and preload embedding model."""
        if self._initialized:
            return

        aiplatform.init(
            project=self._project_id,
            location=self._location,
        )

        from vertexai.language_models import TextEmbeddingModel

        self._model = TextEmbeddingModel.from_pretrained(self._model_id)
        self._initialized = True
        logger.info(
            "Vertex AI embedding client initialized",
            project=self._project_id,
            location=self._location,
            model=self._model_id,
        )

    @property
    def model_name(self) -> str:
        """Return the identifier of the embedding model."""
        return self._model_id

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for provided text."""
        if not text or not text.strip():
            raise ValueError("Text is required to build embedding")

        if not self._initialized:
            await self.initialize()

        try:
            return await asyncio.to_thread(self._embed_sync, text)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to generate embedding", error=str(exc))
            raise

    def _embed_sync(self, text: str) -> list[float]:
        """Blocking embedding generation executed in a thread."""
        if self._model is None:
            raise RuntimeError("Embedding model not initialized")

        embeddings = self._model.get_embeddings([text])
        if not embeddings:
            raise RuntimeError("Vertex AI returned empty embedding response")

        values = embeddings[0].values
        return list(values)
