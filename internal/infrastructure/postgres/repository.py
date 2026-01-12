"""
PostgreSQL Product Repository.

Implements the repository pattern for Product Family persistence with asyncpg.
Includes Outbox Pattern support for reliable event publishing.
"""
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

import asyncpg
from asyncpg import Pool, Connection

from internal.domain.product import ProductFamily, OutboxEvent
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
                    json.dumps(schema_org_data) if schema_org_data else None,
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
