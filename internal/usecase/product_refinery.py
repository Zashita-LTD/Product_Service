"""
Product Refinery - MDM (Master Data Management) Pipeline.

Умная система обработки сырых данных от парсеров:
1. Дедупликация (по EAN, SKU, Vector Search)
2. Слияние данных из разных источников
3. Обогащение карточки (фото, атрибуты, документы)
4. Привязка к производителю

Чем больше магазинов парсим — тем полнее карточка товара!
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Protocol, List, Tuple
from uuid import UUID, uuid4

from internal.domain.product import ProductFamily, OutboxEvent
from internal.domain.value_objects import QualityScore
from internal.infrastructure.postgres.raw_repository import (
    RawProductSnapshot,
    RawSnapshotRepository,
    ProductSourceLink,
    ProductSourceLinkRepository,
    EnrichmentAuditRepository,
)
from pkg.logger.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# PROTOCOLS
# ============================================================================

class EmbeddingClientProtocol(Protocol):
    """Протокол для генерации эмбеддингов."""

    @property
    def model_name(self) -> str:
        """Model name."""
        ...

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        ...


class ProductRepositoryProtocol(Protocol):
    """Протокол для работы с товарами."""

    async def get_by_uuid(self, uuid: UUID) -> Optional[ProductFamily]:
        """Get product by UUID."""
        ...

    async def find_by_source_url(self, source_url: str) -> Optional[ProductFamily]:
        """Find product by source URL."""
        ...

    async def get_by_name(self, name_technical: str) -> Optional[ProductFamily]:
        """Get product by technical name."""
        ...

    async def create_with_outbox(
        self,
        product: ProductFamily,
        event: OutboxEvent,
        **kwargs,
    ) -> ProductFamily:
        """Create product with outbox event."""
        ...

    async def upsert_embedding(
        self,
        product_uuid: UUID,
        embedding: List[float],
        model: str,
    ) -> None:
        """Upsert product embedding."""
        ...

    async def semantic_search(
        self,
        embedding: List[float],
        **kwargs,
    ) -> Tuple[List[dict], int]:
        """Semantic search by embedding."""
        ...


class ManufacturerServiceProtocol(Protocol):
    """Протокол для работы с производителями."""

    async def get_or_create_by_name(self, name: str) -> Optional[UUID]:
        """Get or create manufacturer by name."""
        ...


# ============================================================================
# RESULT TYPES
# ============================================================================

@dataclass
class RefineryResult:
    """Результат обработки сырых данных."""

    snapshot_id: UUID
    status: str  # 'new_product', 'enriched', 'duplicate', 'error'
    product_uuid: Optional[UUID] = None
    message: str = ""
    enrichments: List[str] = None  # Список добавленных данных

    def __post_init__(self):
        if self.enrichments is None:
            self.enrichments = []


@dataclass
class MergeDecision:
    """Решение о слиянии данных."""

    field: str
    action: str  # 'keep_existing', 'use_new', 'merge'
    reason: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None


# ============================================================================
# DEDUPLICATION STRATEGIES
# ============================================================================

class DeduplicationStrategy:
    """Стратегии поиска дубликатов."""

    # Пороги уверенности
    EAN_CONFIDENCE = 0.99  # EAN — почти 100% точность
    SKU_BRAND_CONFIDENCE = 0.95  # Артикул + Бренд — высокая точность
    VECTOR_THRESHOLD = 0.92  # Семантический поиск — порог схожести
    NAME_THRESHOLD = 0.85  # Поиск по имени — более мягкий порог

    def __init__(
        self,
        product_repo: ProductRepositoryProtocol,
        raw_repo: RawSnapshotRepository,
        source_link_repo: ProductSourceLinkRepository,
        embedding_client: Optional[EmbeddingClientProtocol] = None,
    ):
        self._product_repo = product_repo
        self._raw_repo = raw_repo
        self._source_link_repo = source_link_repo
        self._embedding_client = embedding_client

    async def find_duplicate(
        self,
        snapshot: RawProductSnapshot,
    ) -> Tuple[Optional[ProductFamily], float, str]:
        """
        Найти дубликат товара.
        
        Returns:
            (product, confidence, method) или (None, 0, '')
        """
        # 1. Точное совпадение по URL (обновление существующего товара)
        product_uuid = await self._source_link_repo.find_product_by_source(
            snapshot.source_name,
            snapshot.source_url,
        )
        if product_uuid:
            product = await self._product_repo.get_by_uuid(product_uuid)
            if product:
                logger.info(
                    "Duplicate found by URL",
                    source_url=snapshot.source_url,
                    product_uuid=str(product_uuid),
                )
                return product, 1.0, "url_match"

        # 2. Поиск по EAN штрих-коду (самый надёжный)
        if snapshot.extracted_ean:
            product = await self._find_by_ean(snapshot.extracted_ean)
            if product:
                logger.info(
                    "Duplicate found by EAN",
                    ean=snapshot.extracted_ean,
                    product_uuid=str(product.uuid),
                )
                return product, self.EAN_CONFIDENCE, "ean_match"

        # 3. Поиск по артикулу + бренду
        if snapshot.extracted_sku and snapshot.extracted_brand:
            product = await self._find_by_sku_brand(
                snapshot.extracted_sku,
                snapshot.extracted_brand,
            )
            if product:
                logger.info(
                    "Duplicate found by SKU+Brand",
                    sku=snapshot.extracted_sku,
                    brand=snapshot.extracted_brand,
                    product_uuid=str(product.uuid),
                )
                return product, self.SKU_BRAND_CONFIDENCE, "sku_brand_match"

        # 4. Семантический поиск (Vector Search)
        if self._embedding_client:
            product, score = await self._find_by_vector(snapshot)
            if product and score >= self.VECTOR_THRESHOLD:
                logger.info(
                    "Duplicate found by vector search",
                    similarity=score,
                    product_uuid=str(product.uuid),
                )
                return product, score, "vector_match"

        # 5. Поиск по нормализованному имени (fallback)
        raw_name = snapshot.raw_data.get('name_original', '')
        if raw_name:
            product = await self._find_by_name(raw_name, snapshot.extracted_brand)
            if product:
                logger.info(
                    "Duplicate found by name",
                    name=raw_name[:50],
                    product_uuid=str(product.uuid),
                )
                return product, self.NAME_THRESHOLD, "name_match"

        return None, 0.0, ""

    async def _find_by_ean(self, ean: str) -> Optional[ProductFamily]:
        """Найти товар по EAN через source_links или raw_snapshots."""
        # Ищем в обработанных снимках с таким же EAN
        snapshots = await self._raw_repo.find_by_ean(ean)
        for snap in snapshots:
            if snap.linked_product_uuid:
                return await self._product_repo.get_by_uuid(snap.linked_product_uuid)
        return None

    async def _find_by_sku_brand(self, sku: str, brand: str) -> Optional[ProductFamily]:
        """Найти товар по артикулу и бренду."""
        snapshots = await self._raw_repo.find_by_sku_and_brand(sku, brand)
        for snap in snapshots:
            if snap.linked_product_uuid:
                return await self._product_repo.get_by_uuid(snap.linked_product_uuid)
        return None

    async def _find_by_vector(
        self,
        snapshot: RawProductSnapshot,
    ) -> Tuple[Optional[ProductFamily], float]:
        """Семантический поиск по вектору названия."""
        raw_name = snapshot.raw_data.get('name_original', '')
        brand = snapshot.extracted_brand or ''
        
        # Формируем текст для эмбеддинга
        search_text = f"{brand} {raw_name}".strip()
        if not search_text:
            return None, 0.0

        try:
            embedding = await self._embedding_client.generate_embedding(search_text)
            results, _ = await self._product_repo.semantic_search(
                embedding=embedding,
                limit=1,
            )
            
            if results:
                best_match = results[0]
                similarity = best_match.get('similarity', 0)
                product_uuid = best_match.get('uuid')
                
                if product_uuid and similarity >= self.VECTOR_THRESHOLD:
                    product = await self._product_repo.get_by_uuid(product_uuid)
                    return product, similarity
                    
        except Exception as e:
            logger.warning("Vector search failed", error=str(e))
        
        return None, 0.0

    async def _find_by_name(
        self,
        name: str,
        brand: Optional[str] = None,
    ) -> Optional[ProductFamily]:
        """Поиск по нормализованному имени."""
        # Формируем technical_name как в ingest
        parts = []
        if brand:
            parts.append(brand)
        parts.append(name)
        technical_name = " ".join(filter(None, parts))
        
        return await self._product_repo.get_by_name(technical_name)


# ============================================================================
# DATA MERGER
# ============================================================================

class DataMerger:
    """
    Логика слияния данных из разных источников.
    
    Приоритеты:
    - Название: сохраняем первое "чистое" (или от производителя)
    - Описание: берём самое длинное
    - Фото: объединяем из всех источников
    - Атрибуты: объединяем, новые добавляем
    - Цена: сохраняем все для сравнения
    """
    
    # Приоритет источников (меньше = лучше)
    SOURCE_PRIORITY = {
        'knauf': 10,      # Официальный сайт производителя
        'bosch': 10,
        'makita': 10,
        'petrovich': 50,  # Крупные ритейлеры
        'leroy': 50,
        'obi': 50,
        'vseinstrumenti': 60,
        'maxidom': 70,
        'unknown': 100,
    }

    def __init__(self, pool):
        self._pool = pool

    def get_source_priority(self, source_name: str) -> int:
        """Получить приоритет источника."""
        return self.SOURCE_PRIORITY.get(source_name.lower(), 100)

    async def merge_images(
        self,
        product_uuid: UUID,
        new_images: List[dict],
        source_name: str,
    ) -> List[str]:
        """
        Добавить новые изображения к товару.
        
        Returns:
            Список добавленных URL.
        """
        if not new_images:
            return []

        added = []
        async with self._pool.acquire() as conn:
            # Получаем существующие URL
            existing = await conn.fetch(
                "SELECT url FROM product_images WHERE product_uuid = $1",
                product_uuid,
            )
            existing_urls = {row['url'] for row in existing}
            
            # Определяем следующий sort_order
            max_order = await conn.fetchval(
                "SELECT COALESCE(MAX(sort_order), 0) FROM product_images WHERE product_uuid = $1",
                product_uuid,
            )
            
            for i, img in enumerate(new_images):
                url = img if isinstance(img, str) else img.get('url', '')
                if not url or url in existing_urls:
                    continue
                
                await conn.execute(
                    """
                    INSERT INTO product_images (product_uuid, url, alt_text, is_main, sort_order)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    product_uuid,
                    url,
                    f"Image from {source_name}",
                    False,  # Не меняем главную картинку
                    max_order + i + 1,
                )
                added.append(url)
                existing_urls.add(url)
        
        if added:
            logger.info(
                "Images merged",
                product_uuid=str(product_uuid),
                added_count=len(added),
                source=source_name,
            )
        
        return added

    async def merge_attributes(
        self,
        product_uuid: UUID,
        new_attributes: List[dict],
        source_name: str,
    ) -> List[str]:
        """
        Добавить новые атрибуты к товару.
        Не перезаписываем существующие, только добавляем недостающие.
        
        Returns:
            Список добавленных атрибутов.
        """
        if not new_attributes:
            return []

        added = []
        async with self._pool.acquire() as conn:
            # Получаем существующие атрибуты
            existing = await conn.fetch(
                "SELECT LOWER(name) as name FROM product_attributes WHERE product_uuid = $1",
                product_uuid,
            )
            existing_names = {row['name'] for row in existing}
            
            for attr in new_attributes:
                if not isinstance(attr, dict):
                    continue
                    
                name = attr.get('name', '').strip()
                value = attr.get('value', '').strip()
                unit = attr.get('unit', '').strip()
                
                if not name or not value:
                    continue
                
                # Нормализуем имя для сравнения
                name_lower = name.lower()
                if name_lower in existing_names:
                    continue
                
                await conn.execute(
                    """
                    INSERT INTO product_attributes (product_uuid, name, value, unit)
                    VALUES ($1, $2, $3, $4)
                    """,
                    product_uuid,
                    name,
                    value,
                    unit or None,
                )
                added.append(name)
                existing_names.add(name_lower)
        
        if added:
            logger.info(
                "Attributes merged",
                product_uuid=str(product_uuid),
                added_count=len(added),
                source=source_name,
            )
        
        return added

    async def merge_documents(
        self,
        product_uuid: UUID,
        new_documents: List[dict],
        source_name: str,
    ) -> List[str]:
        """
        Добавить новые документы к товару.
        
        Returns:
            Список добавленных документов.
        """
        if not new_documents:
            return []

        added = []
        async with self._pool.acquire() as conn:
            existing = await conn.fetch(
                "SELECT url FROM product_documents WHERE product_uuid = $1",
                product_uuid,
            )
            existing_urls = {row['url'] for row in existing}
            
            for doc in new_documents:
                if not isinstance(doc, dict):
                    continue
                    
                url = doc.get('url', '').strip()
                if not url or url in existing_urls:
                    continue
                
                await conn.execute(
                    """
                    INSERT INTO product_documents (product_uuid, document_type, title, url, format)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    product_uuid,
                    doc.get('document_type', 'manual'),
                    doc.get('title', f"Document from {source_name}"),
                    url,
                    doc.get('format'),
                )
                added.append(url)
                existing_urls.add(url)
        
        if added:
            logger.info(
                "Documents merged",
                product_uuid=str(product_uuid),
                added_count=len(added),
                source=source_name,
            )
        
        return added

    async def update_description_if_better(
        self,
        product_uuid: UUID,
        new_description: str,
        source_name: str,
    ) -> bool:
        """
        Обновить описание, если новое лучше (длиннее).
        
        Returns:
            True если описание обновлено.
        """
        if not new_description or len(new_description) < 50:
            return False

        async with self._pool.acquire() as conn:
            current = await conn.fetchval(
                "SELECT description FROM product_families WHERE uuid = $1",
                product_uuid,
            )
            
            # Обновляем если нет описания или новое значительно длиннее
            if not current or len(new_description) > len(current) * 1.5:
                await conn.execute(
                    "UPDATE product_families SET description = $2, updated_at = NOW() WHERE uuid = $1",
                    product_uuid,
                    new_description,
                )
                logger.info(
                    "Description updated",
                    product_uuid=str(product_uuid),
                    new_length=len(new_description),
                    source=source_name,
                )
                return True
        
        return False


# ============================================================================
# MANUFACTURER LINKER
# ============================================================================

class ManufacturerLinker:
    """Связывание товара с производителем."""
    
    def __init__(self, pool, crm_repo=None):
        self._pool = pool
        self._crm_repo = crm_repo

    async def link_manufacturer(
        self,
        product_uuid: UUID,
        brand_name: str,
    ) -> Optional[UUID]:
        """
        Найти или создать производителя и привязать к товару.
        
        Returns:
            UUID производителя или None.
        """
        if not brand_name:
            return None
        
        # Нормализуем имя бренда
        import re
        brand_normalized = re.sub(r'[^\w\s]', '', brand_name.lower().strip())
        
        async with self._pool.acquire() as conn:
            # Ищем производителя
            row = await conn.fetchrow(
                """
                SELECT id FROM manufacturers 
                WHERE name_normalized = $1 OR LOWER(name) = $2
                LIMIT 1
                """,
                brand_normalized,
                brand_name.lower(),
            )
            
            if row:
                manufacturer_id = row['id']
            else:
                # Создаём нового производителя
                manufacturer_id = uuid4()
                await conn.execute(
                    """
                    INSERT INTO manufacturers (id, name, name_normalized, partner_status)
                    VALUES ($1, $2, $3, 'None')
                    ON CONFLICT DO NOTHING
                    """,
                    manufacturer_id,
                    brand_name,
                    brand_normalized,
                )
                logger.info(
                    "Manufacturer created",
                    manufacturer_id=str(manufacturer_id),
                    name=brand_name,
                )
            
            # Привязываем к товару
            await conn.execute(
                """
                UPDATE product_families 
                SET manufacturer_id = $2, updated_at = NOW() 
                WHERE uuid = $1 AND manufacturer_id IS NULL
                """,
                product_uuid,
                manufacturer_id,
            )
            
            return manufacturer_id


# ============================================================================
# PRODUCT REFINERY - MAIN CLASS
# ============================================================================

class ProductRefinery:
    """
    Главный класс MDM пайплайна.
    
    Обрабатывает сырые данные от парсеров:
    1. Сохраняет снимок (ни байта не теряем)
    2. Ищет дубликаты (EAN → SKU+Brand → Vector → Name)
    3. Обогащает существующий товар ИЛИ создаёт новый
    4. Привязывает к производителю
    """

    def __init__(
        self,
        pool,
        product_repo: ProductRepositoryProtocol,
        raw_repo: RawSnapshotRepository,
        source_link_repo: ProductSourceLinkRepository,
        audit_repo: EnrichmentAuditRepository,
        embedding_client: Optional[EmbeddingClientProtocol] = None,
        default_category_id: int = 1,
    ):
        self._pool = pool
        self._product_repo = product_repo
        self._raw_repo = raw_repo
        self._source_link_repo = source_link_repo
        self._audit_repo = audit_repo
        self._embedding_client = embedding_client
        self._default_category_id = default_category_id
        
        # Компоненты
        self._dedup = DeduplicationStrategy(
            product_repo=product_repo,
            raw_repo=raw_repo,
            source_link_repo=source_link_repo,
            embedding_client=embedding_client,
        )
        self._merger = DataMerger(pool)
        self._manufacturer_linker = ManufacturerLinker(pool)

    async def process(self, raw_data: dict) -> RefineryResult:
        """
        Основной метод обработки сырых данных.
        
        Args:
            raw_data: JSON от парсера.
            
        Returns:
            RefineryResult с результатом обработки.
        """
        source_url = raw_data.get('source_url', '')
        
        if not source_url:
            return RefineryResult(
                snapshot_id=uuid4(),
                status='error',
                message='Missing source_url',
            )

        # 1. Сохраняем снимок
        try:
            snapshot = await self._raw_repo.save_snapshot(raw_data, source_url)
        except Exception as e:
            logger.error("Failed to save snapshot", error=str(e))
            return RefineryResult(
                snapshot_id=uuid4(),
                status='error',
                message=f'Failed to save snapshot: {e}',
            )

        # 2. Проверяем на полный дубль по хэшу
        existing_hash = await self._raw_repo.find_by_content_hash(snapshot.content_hash)
        if existing_hash and existing_hash.id != snapshot.id:
            await self._raw_repo.mark_processed(
                snapshot.id,
                'duplicate',
                existing_hash.linked_product_uuid,
            )
            return RefineryResult(
                snapshot_id=snapshot.id,
                status='duplicate',
                product_uuid=existing_hash.linked_product_uuid,
                message='Exact content duplicate',
            )

        # 3. Ищем дубликат товара
        existing_product, confidence, method = await self._dedup.find_duplicate(snapshot)

        if existing_product:
            # 4a. Обогащаем существующий товар
            result = await self._enrich_existing(snapshot, existing_product, method, confidence)
        else:
            # 4b. Создаём новый товар
            result = await self._create_new_product(snapshot)

        # 5. Отмечаем снимок как обработанный
        await self._raw_repo.mark_processed(
            snapshot.id,
            result.status,
            result.product_uuid,
        )

        return result

    async def _enrich_existing(
        self,
        snapshot: RawProductSnapshot,
        product: ProductFamily,
        match_method: str,
        confidence: float,
    ) -> RefineryResult:
        """Обогащение существующего товара данными из нового снимка."""
        
        enrichments = []
        raw = snapshot.raw_data
        source = snapshot.source_name
        
        logger.info(
            "Enriching existing product",
            product_uuid=str(product.uuid),
            source=source,
            match_method=match_method,
            confidence=confidence,
        )

        # Добавляем изображения
        images = raw.get('images', [])
        added_images = await self._merger.merge_images(product.uuid, images, source)
        if added_images:
            enrichments.append(f"images:{len(added_images)}")

        # Добавляем атрибуты
        attributes = raw.get('attributes', [])
        added_attrs = await self._merger.merge_attributes(product.uuid, attributes, source)
        if added_attrs:
            enrichments.append(f"attributes:{len(added_attrs)}")

        # Добавляем документы
        documents = raw.get('documents', [])
        added_docs = await self._merger.merge_documents(product.uuid, documents, source)
        if added_docs:
            enrichments.append(f"documents:{len(added_docs)}")

        # Обновляем описание если лучше
        description = raw.get('description', '')
        if await self._merger.update_description_if_better(product.uuid, description, source):
            enrichments.append("description")

        # Создаём связь с источником
        link = ProductSourceLink(
            product_uuid=product.uuid,
            source_name=source,
            source_url=snapshot.source_url,
            external_id=snapshot.external_id,
            priority=self._merger.get_source_priority(source),
            contributes_images=bool(added_images),
            contributes_attributes=bool(added_attrs),
            last_synced_at=datetime.utcnow(),
        )
        await self._source_link_repo.create_link(link)

        # Логируем в аудит
        await self._audit_repo.log_action(
            action='enriched',
            snapshot_id=snapshot.id,
            product_uuid=product.uuid,
            action_details={
                'match_method': match_method,
                'confidence': confidence,
                'source': source,
                'enrichments': enrichments,
            },
        )

        status = 'enriched' if enrichments else 'duplicate'
        
        return RefineryResult(
            snapshot_id=snapshot.id,
            status=status,
            product_uuid=product.uuid,
            message=f"Matched by {match_method}, enrichments: {enrichments}",
            enrichments=enrichments,
        )

    async def _create_new_product(self, snapshot: RawProductSnapshot) -> RefineryResult:
        """Создание нового товара из снимка."""
        
        raw = snapshot.raw_data
        source = snapshot.source_name
        
        # Формируем technical name
        name_parts = []
        if snapshot.extracted_brand:
            name_parts.append(snapshot.extracted_brand)
        name_parts.append(raw.get('name_original', 'Unknown Product'))
        name_technical = " ".join(filter(None, name_parts))
        
        if len(name_technical) > 500:
            name_technical = name_technical[:497] + "..."

        logger.info(
            "Creating new product",
            product_name=name_technical[:50],
            source=source,
            ean=snapshot.extracted_ean,
            brand=snapshot.extracted_brand,
        )

        # Создаём ProductFamily
        product = ProductFamily(
            uuid=uuid4(),
            name_technical=name_technical,
            category_id=self._default_category_id,
            quality_score=QualityScore(value=Decimal("0.3")),  # Начальный скор
            enrichment_status="pending",
        )

        # Создаём Outbox Event для дальнейшего обогащения
        event = OutboxEvent(
            aggregate_type="ProductFamily",
            aggregate_id=str(product.uuid),
            event_type="product.created",
            payload={
                "uuid": str(product.uuid),
                "name_technical": name_technical,
                "source": source,
                "source_url": snapshot.source_url,
            },
        )

        # Сохраняем товар со всеми связанными данными
        await self._product_repo.create_with_outbox(
            product=product,
            event=event,
            source_url=snapshot.source_url,
            source_name=source,
            external_id=snapshot.external_id,
            sku=snapshot.extracted_sku,
            brand=snapshot.extracted_brand,
            description=raw.get('description'),
            schema_org_data=raw.get('schema_org_data'),
            attributes=raw.get('attributes'),
            documents=raw.get('documents'),
            images=[{'url': url} for url in raw.get('images', [])],
        )

        # Привязываем к производителю (если таблица существует)
        manufacturer_id = None
        if snapshot.extracted_brand:
            try:
                manufacturer_id = await self._manufacturer_linker.link_manufacturer(
                    product.uuid,
                    snapshot.extracted_brand,
                )
            except Exception as e:
                logger.warning("Manufacturer linking skipped", error=str(e))

        # Создаём эмбеддинг для будущего поиска
        if self._embedding_client:
            try:
                embedding_text = f"{snapshot.extracted_brand or ''} {raw.get('name_original', '')}".strip()
                embedding = await self._embedding_client.generate_embedding(embedding_text)
                await self._product_repo.upsert_embedding(
                    product.uuid,
                    embedding,
                    self._embedding_client.model_name,
                )
            except Exception as e:
                logger.warning("Failed to create embedding", error=str(e))

        # Создаём связь с источником
        link = ProductSourceLink(
            product_uuid=product.uuid,
            source_name=source,
            source_url=snapshot.source_url,
            external_id=snapshot.external_id,
            priority=self._merger.get_source_priority(source),
            contributes_name=True,
            contributes_description=True,
            contributes_images=True,
            contributes_attributes=True,
            last_synced_at=datetime.utcnow(),
        )
        await self._source_link_repo.create_link(link)

        # Логируем в аудит
        await self._audit_repo.log_action(
            action='created',
            snapshot_id=snapshot.id,
            product_uuid=product.uuid,
            action_details={
                'source': source,
                'name': name_technical,
                'ean': snapshot.extracted_ean,
                'sku': snapshot.extracted_sku,
                'brand': snapshot.extracted_brand,
                'manufacturer_id': str(manufacturer_id) if manufacturer_id else None,
            },
        )

        return RefineryResult(
            snapshot_id=snapshot.id,
            status='new_product',
            product_uuid=product.uuid,
            message=f"Created from {source}",
            enrichments=['full_card'],
        )
