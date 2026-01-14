"""Backfill missing semantic embeddings for existing products."""
import asyncio
import os
from typing import Any

from dotenv import load_dotenv

from internal.infrastructure.postgres.repository import (
    PostgresProductRepository,
    create_pool,
)
from internal.infrastructure.ai_provider.vertex_client import VertexAIEmbeddingClient
from pkg.logger.logger import get_logger, setup_logging


load_dotenv()

setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_format=os.getenv("LOG_FORMAT", "json") == "json",
)

logger = get_logger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/product_service",
)
VERTEX_PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
VERTEX_EMBEDDING_MODEL = os.getenv("VERTEX_EMBEDDING_MODEL", "text-embedding-004")
BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "50"))


def _build_embedding_text(product: dict[str, Any]) -> str:
    parts: list[str] = []

    name = product.get("name_technical")
    if name:
        parts.append(name)

    brand = product.get("brand")
    if brand:
        parts.append(f"Бренд: {brand}")

    description = product.get("description")
    if description:
        parts.append(description)

    attributes = product.get("attributes") or []
    for attr in attributes:
        attr_name = attr.get("name")
        attr_value = attr.get("value")
        if not attr_name or not attr_value:
            continue
        unit = attr.get("unit")
        formatted = f"{attr_name}: {attr_value}{(' ' + unit) if unit else ''}"
        parts.append(formatted)

    source_name = product.get("source_name")
    if source_name:
        parts.append(f"Источник: {source_name}")

    return "\n".join(segment.strip() for segment in parts if segment)


async def backfill_embeddings() -> None:
    if not VERTEX_PROJECT_ID:
        raise RuntimeError("VERTEX_PROJECT_ID is required for embedding backfill")

    logger.info(
        "Starting embeddings backfill",
        batch_size=BATCH_SIZE,
        model=VERTEX_EMBEDDING_MODEL,
    )

    pool = await create_pool(DATABASE_URL)
    repository = PostgresProductRepository(pool)
    embedding_client = VertexAIEmbeddingClient(
        project_id=VERTEX_PROJECT_ID,
        location=VERTEX_LOCATION,
        model_id=VERTEX_EMBEDDING_MODEL,
    )
    await embedding_client.initialize()

    processed = 0
    skipped = 0

    try:
        while True:
            batch = await repository.get_products_missing_embeddings(limit=BATCH_SIZE)
            if not batch:
                break

            for product in batch:
                text = _build_embedding_text(product)
                if not text:
                    skipped += 1
                    logger.warning(
                        "Skip embedding generation (empty payload)",
                        uuid=str(product.get("uuid")),
                    )
                    continue

                try:
                    embedding = await embedding_client.generate_embedding(text)
                    await repository.upsert_embedding(
                        product_uuid=product["uuid"],
                        embedding=embedding,
                        model=embedding_client.model_name,
                    )
                    processed += 1
                except Exception as exc:
                    skipped += 1
                    logger.error(
                        "Failed to backfill embedding",
                        uuid=str(product.get("uuid")),
                        error=str(exc),
                    )

            logger.info(
                "Batch finished",
                processed=processed,
                skipped=skipped,
            )

        logger.info(
            "Embeddings backfill completed",
            processed=processed,
            skipped=skipped,
        )
    finally:
        await pool.close()


def main() -> None:
    asyncio.run(backfill_embeddings())


if __name__ == "__main__":
    main()
