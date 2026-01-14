"""
Raw Product Snapshots Repository.

Хранение и работа с сырыми данными от парсеров.
Ни байта информации не теряем!
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

import asyncpg
from asyncpg import Pool

from pkg.logger.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RawProductSnapshot:
    """Сырой снимок товара от парсера."""

    id: UUID = field(default_factory=uuid4)
    source_name: str = ""
    source_url: str = ""
    external_id: Optional[str] = None
    raw_data: dict = field(default_factory=dict)
    content_hash: Optional[str] = None
    extracted_ean: Optional[str] = None
    extracted_sku: Optional[str] = None
    extracted_brand: Optional[str] = None
    processed: bool = False
    processed_at: Optional[datetime] = None
    processing_result: Optional[str] = None
    linked_product_uuid: Optional[UUID] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    parser_version: Optional[str] = None


@dataclass
class ProductSourceLink:
    """Связь товара с источником данных."""

    id: UUID = field(default_factory=uuid4)
    product_uuid: UUID = field(default_factory=uuid4)
    source_name: str = ""
    source_url: str = ""
    external_id: Optional[str] = None
    priority: int = 100
    contributes_name: bool = False
    contributes_description: bool = False
    contributes_images: bool = False
    contributes_price: bool = False
    contributes_attributes: bool = False
    is_active: bool = True
    last_synced_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EnrichmentAuditEntry:
    """Запись аудита обогащения."""

    id: Optional[int] = None
    snapshot_id: Optional[UUID] = None
    product_uuid: Optional[UUID] = None
    action: str = ""
    action_details: Optional[dict] = None
    ai_model: Optional[str] = None
    ai_confidence: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class RawSnapshotRepository:
    """Репозиторий для работы с сырыми снимками товаров."""

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    @staticmethod
    def compute_content_hash(raw_data: dict) -> str:
        """Вычислить SHA256 хэш содержимого для дедупликации."""
        # Сортируем ключи для стабильного хэша
        json_str = json.dumps(raw_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

    @staticmethod
    def extract_ean(raw_data: dict) -> Optional[str]:
        """Извлечь EAN штрих-код из сырых данных."""
        # Ищем в разных местах
        possible_keys = ['ean', 'barcode', 'ean13', 'ean_code', 'gtin']
        
        # Прямой поиск
        for key in possible_keys:
            if key in raw_data and raw_data[key]:
                return str(raw_data[key]).strip()
        
        # Поиск в атрибутах
        attributes = raw_data.get('attributes', [])
        for attr in attributes:
            if isinstance(attr, dict):
                name = attr.get('name', '').lower()
                if any(k in name for k in ['штрих', 'ean', 'barcode', 'gtin']):
                    value = attr.get('value', '')
                    if value:
                        # Валидация EAN-13 или EAN-8
                        cleaned = re.sub(r'\D', '', str(value))
                        if len(cleaned) in [8, 13]:
                            return cleaned
        
        # Поиск в schema.org данных
        schema_data = raw_data.get('schema_org_data', {})
        if schema_data:
            for key in ['gtin13', 'gtin', 'ean', 'productID']:
                if key in schema_data:
                    cleaned = re.sub(r'\D', '', str(schema_data[key]))
                    if len(cleaned) in [8, 13]:
                        return cleaned
        
        return None

    @staticmethod
    def extract_sku(raw_data: dict) -> Optional[str]:
        """Извлечь артикул производителя из сырых данных."""
        possible_keys = ['sku', 'mpn', 'article', 'vendor_code', 'артикул']
        
        for key in possible_keys:
            if key in raw_data and raw_data[key]:
                return str(raw_data[key]).strip()[:50]
        
        # Поиск в атрибутах
        attributes = raw_data.get('attributes', [])
        for attr in attributes:
            if isinstance(attr, dict):
                name = attr.get('name', '').lower()
                if any(k in name for k in ['артикул', 'sku', 'код товара', 'vendor code']):
                    value = attr.get('value', '')
                    if value:
                        return str(value).strip()[:50]
        
        # Поиск в schema.org
        schema_data = raw_data.get('schema_org_data', {})
        if schema_data:
            for key in ['sku', 'mpn', 'productID']:
                if key in schema_data and schema_data[key]:
                    return str(schema_data[key]).strip()[:50]
        
        return None

    @staticmethod
    def extract_brand(raw_data: dict) -> Optional[str]:
        """Извлечь бренд из сырых данных."""
        # Прямой поиск
        if raw_data.get('brand'):
            return str(raw_data['brand']).strip()[:100]
        
        # Поиск в schema.org
        schema_data = raw_data.get('schema_org_data', {})
        if schema_data:
            brand = schema_data.get('brand')
            if isinstance(brand, dict):
                brand = brand.get('name')
            if brand:
                return str(brand).strip()[:100]
        
        # Поиск в атрибутах
        attributes = raw_data.get('attributes', [])
        for attr in attributes:
            if isinstance(attr, dict):
                name = attr.get('name', '').lower()
                if any(k in name for k in ['бренд', 'brand', 'производитель', 'manufacturer']):
                    value = attr.get('value', '')
                    if value:
                        return str(value).strip()[:100]
        
        return None

    @staticmethod
    def extract_source_name(url: str) -> str:
        """Извлечь имя источника из URL."""
        url_lower = url.lower()
        
        source_patterns = {
            'petrovich': ['petrovich.ru', 'petrovich.'],
            'leroy': ['leroymerlin.ru', 'leroy'],
            'vseinstrumenti': ['vseinstrumenti.ru', 'vseinstrumenty'],
            'obi': ['obi.ru'],
            'castorama': ['castorama.ru'],
            'maxidom': ['maxidom.ru'],
            'stroylandiya': ['stroylandiya.ru'],
            'technonikol': ['technonikol.ru'],
            'knauf': ['knauf.ru'],
        }
        
        for source, patterns in source_patterns.items():
            if any(p in url_lower for p in patterns):
                return source
        
        # Попытка извлечь домен
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.replace('www.', '').split('.')[0]
        return domain[:50] if domain else 'unknown'

    async def save_snapshot(self, raw_data: dict, source_url: str) -> RawProductSnapshot:
        """
        Сохранить сырой снимок товара.
        
        Returns:
            RawProductSnapshot с заполненными извлечёнными данными.
        """
        snapshot = RawProductSnapshot(
            id=uuid4(),
            source_name=self.extract_source_name(source_url),
            source_url=source_url,
            external_id=raw_data.get('id') or raw_data.get('external_id'),
            raw_data=raw_data,
            content_hash=self.compute_content_hash(raw_data),
            extracted_ean=self.extract_ean(raw_data),
            extracted_sku=self.extract_sku(raw_data),
            extracted_brand=self.extract_brand(raw_data),
            parser_version=raw_data.get('parser_version'),
        )
        
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO raw_product_snapshots (
                    id, source_name, source_url, external_id, raw_data,
                    content_hash, extracted_ean, extracted_sku, extracted_brand,
                    processed, parser_version, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                snapshot.id,
                snapshot.source_name,
                snapshot.source_url,
                snapshot.external_id,
                json.dumps(snapshot.raw_data),
                snapshot.content_hash,
                snapshot.extracted_ean,
                snapshot.extracted_sku,
                snapshot.extracted_brand,
                False,
                snapshot.parser_version,
                snapshot.created_at,
            )
        
        logger.info(
            "Raw snapshot saved",
            snapshot_id=str(snapshot.id),
            source=snapshot.source_name,
            ean=snapshot.extracted_ean,
            brand=snapshot.extracted_brand,
        )
        
        return snapshot

    async def find_by_content_hash(self, content_hash: str) -> Optional[RawProductSnapshot]:
        """Найти снимок по хэшу содержимого (полный дубль)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM raw_product_snapshots WHERE content_hash = $1 LIMIT 1",
                content_hash,
            )
            return self._row_to_snapshot(row) if row else None

    async def find_by_source_url(self, source_url: str) -> Optional[RawProductSnapshot]:
        """Найти последний снимок по URL источника."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM raw_product_snapshots 
                WHERE source_url = $1 
                ORDER BY created_at DESC 
                LIMIT 1
                """,
                source_url,
            )
            return self._row_to_snapshot(row) if row else None

    async def find_by_ean(self, ean: str) -> List[RawProductSnapshot]:
        """Найти снимки по EAN штрих-коду."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (source_name) * 
                FROM raw_product_snapshots 
                WHERE extracted_ean = $1 
                ORDER BY source_name, created_at DESC
                """,
                ean,
            )
            return [self._row_to_snapshot(row) for row in rows]

    async def find_by_sku_and_brand(self, sku: str, brand: str) -> List[RawProductSnapshot]:
        """Найти снимки по артикулу и бренду."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (source_name) * 
                FROM raw_product_snapshots 
                WHERE extracted_sku = $1 AND LOWER(extracted_brand) = LOWER($2)
                ORDER BY source_name, created_at DESC
                """,
                sku,
                brand,
            )
            return [self._row_to_snapshot(row) for row in rows]

    async def mark_processed(
        self,
        snapshot_id: UUID,
        result: str,
        linked_product_uuid: Optional[UUID] = None,
    ) -> None:
        """Отметить снимок как обработанный."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE raw_product_snapshots 
                SET processed = TRUE, 
                    processed_at = NOW(),
                    processing_result = $2,
                    linked_product_uuid = $3
                WHERE id = $1
                """,
                snapshot_id,
                result,
                linked_product_uuid,
            )

    async def get_unprocessed(self, limit: int = 100) -> List[RawProductSnapshot]:
        """Получить необработанные снимки для пайплайна."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM raw_product_snapshots 
                WHERE processed = FALSE 
                ORDER BY created_at ASC 
                LIMIT $1
                FOR UPDATE SKIP LOCKED
                """,
                limit,
            )
            return [self._row_to_snapshot(row) for row in rows]

    def _row_to_snapshot(self, row: asyncpg.Record) -> RawProductSnapshot:
        """Преобразовать строку БД в объект."""
        raw_data = row['raw_data']
        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)
        
        return RawProductSnapshot(
            id=row['id'],
            source_name=row['source_name'],
            source_url=row['source_url'],
            external_id=row['external_id'],
            raw_data=raw_data,
            content_hash=row['content_hash'],
            extracted_ean=row['extracted_ean'],
            extracted_sku=row['extracted_sku'],
            extracted_brand=row['extracted_brand'],
            processed=row['processed'],
            processed_at=row['processed_at'],
            processing_result=row['processing_result'],
            linked_product_uuid=row['linked_product_uuid'],
            created_at=row['created_at'],
            parser_version=row['parser_version'],
        )


class ProductSourceLinkRepository:
    """Репозиторий для связей товара с источниками."""

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def create_link(self, link: ProductSourceLink) -> ProductSourceLink:
        """Создать связь товара с источником."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO product_source_links (
                    id, product_uuid, source_name, source_url, external_id,
                    priority, contributes_name, contributes_description,
                    contributes_images, contributes_price, contributes_attributes,
                    is_active, last_synced_at, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (product_uuid, source_name, source_url) 
                DO UPDATE SET 
                    last_synced_at = NOW(),
                    updated_at = NOW()
                """,
                link.id,
                link.product_uuid,
                link.source_name,
                link.source_url,
                link.external_id,
                link.priority,
                link.contributes_name,
                link.contributes_description,
                link.contributes_images,
                link.contributes_price,
                link.contributes_attributes,
                link.is_active,
                link.last_synced_at,
                link.created_at,
                link.updated_at,
            )
        return link

    async def get_links_for_product(self, product_uuid: UUID) -> List[ProductSourceLink]:
        """Получить все источники для товара."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM product_source_links 
                WHERE product_uuid = $1 AND is_active = TRUE
                ORDER BY priority ASC
                """,
                product_uuid,
            )
            return [self._row_to_link(row) for row in rows]

    async def find_product_by_source(
        self,
        source_name: str,
        source_url: str,
    ) -> Optional[UUID]:
        """Найти UUID товара по источнику."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT product_uuid FROM product_source_links 
                WHERE source_name = $1 AND source_url = $2 AND is_active = TRUE
                LIMIT 1
                """,
                source_name,
                source_url,
            )
            return row['product_uuid'] if row else None

    def _row_to_link(self, row: asyncpg.Record) -> ProductSourceLink:
        return ProductSourceLink(
            id=row['id'],
            product_uuid=row['product_uuid'],
            source_name=row['source_name'],
            source_url=row['source_url'],
            external_id=row['external_id'],
            priority=row['priority'],
            contributes_name=row['contributes_name'],
            contributes_description=row['contributes_description'],
            contributes_images=row['contributes_images'],
            contributes_price=row['contributes_price'],
            contributes_attributes=row['contributes_attributes'],
            is_active=row['is_active'],
            last_synced_at=row['last_synced_at'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )


class EnrichmentAuditRepository:
    """Репозиторий для аудита обогащения."""

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def log_action(
        self,
        action: str,
        snapshot_id: Optional[UUID] = None,
        product_uuid: Optional[UUID] = None,
        action_details: Optional[dict] = None,
        ai_model: Optional[str] = None,
        ai_confidence: Optional[float] = None,
    ) -> int:
        """Записать действие в аудит."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO enrichment_audit_log (
                    snapshot_id, product_uuid, action, action_details, 
                    ai_model, ai_confidence
                ) VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                snapshot_id,
                product_uuid,
                action,
                json.dumps(action_details) if action_details else None,
                ai_model,
                ai_confidence,
            )
            
            logger.debug(
                "Audit logged",
                action=action,
                product_uuid=str(product_uuid) if product_uuid else None,
            )
            
            return row['id']

    async def get_product_history(
        self,
        product_uuid: UUID,
        limit: int = 50,
    ) -> List[EnrichmentAuditEntry]:
        """Получить историю обогащения товара."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM enrichment_audit_log 
                WHERE product_uuid = $1 
                ORDER BY created_at DESC 
                LIMIT $2
                """,
                product_uuid,
                limit,
            )
            return [self._row_to_entry(row) for row in rows]

    def _row_to_entry(self, row: asyncpg.Record) -> EnrichmentAuditEntry:
        action_details = row['action_details']
        if isinstance(action_details, str):
            action_details = json.loads(action_details)
        
        return EnrichmentAuditEntry(
            id=row['id'],
            snapshot_id=row['snapshot_id'],
            product_uuid=row['product_uuid'],
            action=row['action'],
            action_details=action_details,
            ai_model=row['ai_model'],
            ai_confidence=float(row['ai_confidence']) if row['ai_confidence'] else None,
            created_at=row['created_at'],
        )
