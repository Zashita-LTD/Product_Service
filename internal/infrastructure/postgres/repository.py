"""
PostgreSQL Product Repository.

Implements the repository pattern for Product Family persistence with asyncpg.
Includes Outbox Pattern support for reliable event publishing.
"""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import asyncpg
from asyncpg import Pool

from internal.domain.product import OutboxEvent, ProductFamily
from internal.domain.value_objects import QualityScore


class PostgresProductRepository:
    """
    PostgreSQL implementation of the Product Repository.

    Uses asyncpg for async database operations and implements
    the Outbox Pattern for reliable event publishing.
    """

    def __init__(self, pool: Pool) -> None:
        """
        Initialize the repository.

        Args:
            pool: asyncpg connection pool.
        """
        self._pool = pool

    async def get_by_uuid(self, uuid: UUID) -> Optional[ProductFamily]:
        """
        Get a product family by UUID.

        Args:
            uuid: The UUID of the product family.

        Returns:
            ProductFamily if found, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT uuid, name_technical, category_id, quality_score,
                       enrichment_status, created_at, updated_at
                FROM product_families
                WHERE uuid = $1
                """,
                uuid,
            )

            if not row:
                return None

            return self._row_to_entity(row)

    async def get_by_name(self, name_technical: str) -> Optional[ProductFamily]:
        """
        Get a product family by technical name.

        Args:
            name_technical: The technical name of the product.

        Returns:
            ProductFamily if found, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT uuid, name_technical, category_id, quality_score,
                       enrichment_status, created_at, updated_at
                FROM product_families
                WHERE name_technical = $1
                """,
                name_technical,
            )

            if not row:
                return None

            return self._row_to_entity(row)

    async def find_by_source_url(self, source_url: str) -> Optional[ProductFamily]:
        """
        Find a product family by source URL (for deduplication).

        Args:
            source_url: The source URL from the parser.

        Returns:
            ProductFamily if found, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT uuid, name_technical, category_id, quality_score,
                       enrichment_status, created_at, updated_at
                FROM product_families
                WHERE source_url = $1
                """,
                source_url,
            )

            if not row:
                return None

            return self._row_to_entity(row)

    async def create_with_outbox(
        self,
        product: ProductFamily,
        event: OutboxEvent,
        source_url: Optional[str] = None,
        source_name: Optional[str] = None,
        external_id: Optional[str] = None,
        sku: Optional[str] = None,
        brand: Optional[str] = None,
        description: Optional[str] = None,
        schema_org_data: Optional[dict] = None,
        attributes: Optional[list[dict]] = None,
        documents: Optional[list[dict]] = None,
        images: Optional[list[dict]] = None,
    ) -> ProductFamily:
        """
        Create a product family with an outbox event atomically.

        Implements the Outbox Pattern for reliable event publishing.
        Both the product and the event are created in a single transaction.
        Optionally creates related attributes, documents, and images.

        Args:
            product: The product family to create.
            event: The outbox event to create.
            source_url: Original URL from parser.
            source_name: Name of the source.
            external_id: External ID from source system.
            sku: Stock Keeping Unit.
            brand: Brand/manufacturer name.
            description: Product description.
            schema_org_data: Schema.org structured data.
            attributes: List of attribute dicts (name, value, unit).
            documents: List of document dicts (document_type, title, url, format).
            images: List of image dicts (url, alt_text, is_main, sort_order).

        Returns:
            The created product family.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Insert product family
                await conn.execute(
                    """
                    INSERT INTO product_families (
                        uuid, name_technical, category_id, quality_score,
                        enrichment_status, created_at, updated_at,
                        source_url, source_name, external_id, sku, brand,
                        description, schema_org_data
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """,
                    product.uuid,
                    product.name_technical,
                    product.category_id,
                    float(product.quality_score.value) if product.quality_score else None,
                    product.enrichment_status,
                    product.created_at,
                    product.updated_at,
                    source_url,
                    source_name,
                    external_id,
                    sku,
                    brand,
                    description,
                    self._serialize_json(schema_org_data) if schema_org_data else None,
                )

                # Insert attributes if provided
                if attributes:
                    for attr in attributes:
                        await conn.execute(
                            """
                            INSERT INTO product_attributes (
                                product_uuid, name, value, unit
                            ) VALUES ($1, $2, $3, $4)
                            """,
                            product.uuid,
                            attr.get("name"),
                            attr.get("value"),
                            attr.get("unit"),
                        )

                # Insert documents if provided
                if documents:
                    for doc in documents:
                        await conn.execute(
                            """
                            INSERT INTO product_documents (
                                product_uuid, document_type, title, url, format
                            ) VALUES ($1, $2, $3, $4, $5)
                            """,
                            product.uuid,
                            doc.get("document_type"),
                            doc.get("title"),
                            doc.get("url"),
                            doc.get("format"),
                        )

                # Insert images if provided
                if images:
                    for img in images:
                        await conn.execute(
                            """
                            INSERT INTO product_images (
                                product_uuid, url, alt_text, is_main, sort_order
                            ) VALUES ($1, $2, $3, $4, $5)
                            """,
                            product.uuid,
                            img.get("url"),
                            img.get("alt_text"),
                            img.get("is_main", False),
                            img.get("sort_order", 0),
                        )

                # Insert outbox event
                await conn.execute(
                    """
                    INSERT INTO outbox_events (
                        aggregate_type, aggregate_id, event_type,
                        payload, created_at
                    ) VALUES ($1, $2, $3, $4, $5)
                    """,
                    event.aggregate_type,
                    event.aggregate_id,
                    event.event_type,
                    json.dumps(event.payload),
                    event.created_at,
                )

        return product

    async def update(self, product: ProductFamily) -> ProductFamily:
        """
        Update a product family.

        Args:
            product: The product family to update.

        Returns:
            The updated product family.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE product_families
                SET name_technical = $2,
                    category_id = $3,
                    quality_score = $4,
                    enrichment_status = $5,
                    updated_at = $6
                WHERE uuid = $1
                """,
                product.uuid,
                product.name_technical,
                product.category_id,
                float(product.quality_score.value) if product.quality_score else None,
                product.enrichment_status,
                product.updated_at,
            )

        return product

    async def list_by_category(
        self,
        category_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProductFamily]:
        """
        List product families by category.

        Args:
            category_id: The category ID to filter by.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of product families.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT uuid, name_technical, category_id, quality_score,
                       enrichment_status, created_at, updated_at
                FROM product_families
                WHERE category_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                category_id,
                limit,
                offset,
            )

            return [self._row_to_entity(row) for row in rows]

    async def get_unprocessed_outbox_events(
        self,
        limit: int = 100,
    ) -> list[OutboxEvent]:
        """
        Get unprocessed outbox events for publishing.

        Args:
            limit: Maximum number of events to retrieve.

        Returns:
            List of unprocessed outbox events.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, aggregate_type, aggregate_id, event_type,
                       payload, created_at, processed_at
                FROM outbox_events
                WHERE processed_at IS NULL
                ORDER BY created_at ASC
                LIMIT $1
                FOR UPDATE SKIP LOCKED
                """,
                limit,
            )

            return [self._row_to_outbox_event(row) for row in rows]

    async def mark_event_processed(self, event_id: int) -> None:
        """
        Mark an outbox event as processed.

        Args:
            event_id: The ID of the event to mark as processed.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE outbox_events
                SET processed_at = $2
                WHERE id = $1
                """,
                event_id,
                datetime.utcnow(),
            )

    def _row_to_entity(self, row: asyncpg.Record) -> ProductFamily:
        """
        Convert a database row to a ProductFamily entity.

        Args:
            row: Database row.

        Returns:
            ProductFamily entity.
        """
        quality_score = None
        if row["quality_score"] is not None:
            quality_score = QualityScore(value=Decimal(str(row["quality_score"])))

        return ProductFamily(
            uuid=row["uuid"],
            name_technical=row["name_technical"],
            category_id=row["category_id"],
            quality_score=quality_score,
            enrichment_status=row["enrichment_status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_outbox_event(self, row: asyncpg.Record) -> OutboxEvent:
        """
        Convert a database row to an OutboxEvent entity.

        Args:
            row: Database row.

        Returns:
            OutboxEvent entity.
        """
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)

        return OutboxEvent(
            id=row["id"],
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            event_type=row["event_type"],
            payload=payload,
            created_at=row["created_at"],
            processed_at=row["processed_at"],
        )

    async def list_products(
        self,
        category_id: Optional[int] = None,
        brand: Optional[str] = None,
        source_name: Optional[str] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        in_stock: Optional[bool] = None,
        enrichment_status: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[dict], int]:
        """
        List products with filters and pagination.

        Args:
            category_id: Filter by category.
            brand: Filter by brand.
            source_name: Filter by source.
            min_price: Minimum price filter.
            max_price: Maximum price filter.
            in_stock: Filter by stock availability.
            enrichment_status: Filter by enrichment status.
            offset: Number of results to skip.
            limit: Maximum number of results.
            sort_by: Field to sort by.
            sort_order: Sort order (asc/desc).

        Returns:
            Tuple of (list of product dicts, total count).
        """
        # Build WHERE clause dynamically
        conditions = []
        params = []
        param_num = 1

        if category_id is not None:
            conditions.append(f"pf.category_id = ${param_num}")
            params.append(category_id)
            param_num += 1

        if brand is not None:
            conditions.append(f"pf.brand = ${param_num}")
            params.append(brand)
            param_num += 1

        if source_name is not None:
            conditions.append(f"pf.source_name = ${param_num}")
            params.append(source_name)
            param_num += 1

        if enrichment_status is not None:
            conditions.append(f"pf.enrichment_status = ${param_num}")
            params.append(enrichment_status)
            param_num += 1

        if min_price is not None or max_price is not None:
            # Join with prices table for price filtering
            price_conditions = []
            if min_price is not None:
                price_conditions.append(f"p.amount >= ${param_num}")
                params.append(min_price)
                param_num += 1
            if max_price is not None:
                price_conditions.append(f"p.amount <= ${param_num}")
                params.append(max_price)
                param_num += 1
            conditions.extend(price_conditions)

        if in_stock is not None and in_stock:
            conditions.append("i.quantity > 0")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Validate sort_by to prevent SQL injection
        valid_sort_fields = ["created_at", "updated_at", "name_technical", "quality_score"]
        if sort_by not in valid_sort_fields:
            sort_by = "created_at"

        sort_order = "DESC" if sort_order.lower() == "desc" else "ASC"

        # Build JOIN clauses
        join_clauses = ""
        if min_price is not None or max_price is not None:
            join_clauses += (
                " LEFT JOIN prices p ON pf.uuid = p.product_family_uuid AND p.is_active = true"
            )
        if in_stock is not None and in_stock:
            join_clauses += " LEFT JOIN inventory i ON pf.uuid = i.product_family_uuid"

        # Query for products
        query = f"""
            SELECT DISTINCT
                pf.uuid, pf.name_technical, pf.brand, pf.sku, pf.category_id,
                pf.source_name, pf.enrichment_status, pf.quality_score,
                pf.created_at, pf.updated_at, pf.external_id, pf.source_url
            FROM product_families pf
            {join_clauses}
            WHERE {where_clause}
            ORDER BY pf.{sort_by} {sort_order}
            LIMIT ${param_num} OFFSET ${param_num + 1}
        """

        # Count query uses same filters but no limit/offset
        count_query = f"""
            SELECT COUNT(DISTINCT pf.uuid)
            FROM product_families pf
            {join_clauses}
            WHERE {where_clause}
        """

        # Parameters for count query (without limit and offset)
        count_params = params.copy()
        # Parameters for data query (with limit and offset)
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            count_row = await conn.fetchval(count_query, *count_params)

            products = []
            for row in rows:
                product_dict = dict(row)
                products.append(product_dict)

            return products, count_row or 0

    async def get_product_with_details(self, uuid: UUID) -> Optional[dict]:
        """
        Get a product with all related data (attributes, images, documents).

        Args:
            uuid: The UUID of the product family.

        Returns:
            Dict with product and all related data, or None if not found.
        """
        async with self._pool.acquire() as conn:
            # Get product family
            product_row = await conn.fetchrow(
                """
                SELECT uuid, name_technical, category_id, quality_score,
                       enrichment_status, created_at, updated_at, brand,
                       sku, description, source_name, source_url, external_id
                FROM product_families
                WHERE uuid = $1
                """,
                uuid,
            )

            if not product_row:
                return None

            # Get attributes
            attributes = await conn.fetch(
                """
                SELECT name, value, unit
                FROM product_attributes
                WHERE product_uuid = $1
                ORDER BY name
                """,
                uuid,
            )

            # Get images
            images = await conn.fetch(
                """
                SELECT url, alt_text, is_main, sort_order
                FROM product_images
                WHERE product_uuid = $1
                ORDER BY sort_order, is_main DESC
                """,
                uuid,
            )

            # Get documents
            documents = await conn.fetch(
                """
                SELECT document_type, title, url, format
                FROM product_documents
                WHERE product_uuid = $1
                ORDER BY document_type
                """,
                uuid,
            )

            # Get active price
            price_row = await conn.fetchrow(
                """
                SELECT amount, currency
                FROM prices
                WHERE product_family_uuid = $1 AND is_active = true
                ORDER BY created_at DESC
                LIMIT 1
                """,
                uuid,
            )

            # Get inventory
            inventory_row = await conn.fetchrow(
                """
                SELECT SUM(quantity) as total_quantity,
                       BOOL_OR(quantity > 0) as in_stock
                FROM inventory
                WHERE product_family_uuid = $1
                """,
                uuid,
            )

            return {
                "product": dict(product_row),
                "attributes": [dict(row) for row in attributes],
                "images": [dict(row) for row in images],
                "documents": [dict(row) for row in documents],
                "price": dict(price_row) if price_row else None,
                "inventory": dict(inventory_row) if inventory_row else None,
            }

    async def search(
        self,
        query: str,
        category_id: Optional[int] = None,
        brand: Optional[str] = None,
        source_name: Optional[str] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        in_stock: Optional[bool] = None,
        enrichment_status: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict], int]:
        """
        Full-text search for products.

        Args:
            query: Search query.
            category_id: Filter by category.
            brand: Filter by brand.
            source_name: Filter by source.
            min_price: Minimum price filter.
            max_price: Maximum price filter.
            in_stock: Filter by stock availability.
            enrichment_status: Filter by enrichment status.
            offset: Number of results to skip.
            limit: Maximum number of results.

        Returns:
            Tuple of (list of product dicts, total count).
        """
        # Build WHERE clause dynamically
        conditions = ["pf.search_vector @@ plainto_tsquery('russian', $1)"]
        params = [query]
        param_num = 2

        if category_id is not None:
            conditions.append(f"pf.category_id = ${param_num}")
            params.append(category_id)
            param_num += 1

        if brand is not None:
            conditions.append(f"pf.brand = ${param_num}")
            params.append(brand)
            param_num += 1

        if source_name is not None:
            conditions.append(f"pf.source_name = ${param_num}")
            params.append(source_name)
            param_num += 1

        if enrichment_status is not None:
            conditions.append(f"pf.enrichment_status = ${param_num}")
            params.append(enrichment_status)
            param_num += 1

        if min_price is not None or max_price is not None:
            price_conditions = []
            if min_price is not None:
                price_conditions.append(f"p.amount >= ${param_num}")
                params.append(min_price)
                param_num += 1
            if max_price is not None:
                price_conditions.append(f"p.amount <= ${param_num}")
                params.append(max_price)
                param_num += 1
            conditions.extend(price_conditions)

        if in_stock is not None and in_stock:
            conditions.append("i.quantity > 0")

        where_clause = " AND ".join(conditions)

        # Build JOIN clauses
        join_clauses = ""
        if min_price is not None or max_price is not None:
            join_clauses += (
                " LEFT JOIN prices p ON pf.uuid = p.product_family_uuid AND p.is_active = true"
            )
        if in_stock is not None and in_stock:
            join_clauses += " LEFT JOIN inventory i ON pf.uuid = i.product_family_uuid"

        # Query for products with relevance ranking
        query_sql = f"""
            SELECT DISTINCT
                pf.uuid, pf.name_technical, pf.brand, pf.sku, pf.category_id,
                pf.source_name, pf.enrichment_status, pf.quality_score,
                pf.created_at, pf.updated_at, pf.external_id, pf.source_url,
                ts_rank(pf.search_vector, plainto_tsquery('russian', $1)) as rank
            FROM product_families pf
            {join_clauses}
            WHERE {where_clause}
            ORDER BY rank DESC, pf.created_at DESC
            LIMIT ${param_num} OFFSET ${param_num + 1}
        """

        # Count query uses same filters but no limit/offset
        count_query = f"""
            SELECT COUNT(DISTINCT pf.uuid)
            FROM product_families pf
            {join_clauses}
            WHERE {where_clause}
        """

        # Parameters for count query (without limit and offset)
        count_params = params.copy()
        # Parameters for data query (with limit and offset)
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query_sql, *params)
            count_row = await conn.fetchval(count_query, *count_params)

            products = []
            for row in rows:
                product_dict = dict(row)
                # Remove rank from result
                product_dict.pop("rank", None)
                products.append(product_dict)

            return products, count_row or 0

    def _serialize_json(self, data: dict) -> str:
        """
        Safely serialize data to JSON.

        Args:
            data: Data to serialize.

        Returns:
            JSON string.

        Raises:
            TypeError: If data contains non-serializable objects.
        """
        try:
            return json.dumps(data)
        except (TypeError, ValueError) as e:
            raise TypeError(f"Failed to serialize data to JSON: {e}") from e


async def create_pool(dsn: str, min_size: int = 10, max_size: int = 50) -> Pool:
    """
    Create an asyncpg connection pool.

    Args:
        dsn: Database connection string.
        min_size: Minimum pool size.
        max_size: Maximum pool size.

    Returns:
        asyncpg connection pool.
    """
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
    )
