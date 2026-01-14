-- Migration: 011_raw_data.sql
-- Description: Raw product snapshots for MDM (Master Data Management)
-- Date: 2026-01-14
--
-- Храним ВСЕ сырые данные от парсеров. Ни байта информации не теряем.
-- Это основа для дедупликации, обогащения и аудита качества данных.

-- ============================================================================
-- 1. RAW PRODUCT SNAPSHOTS (Сырые снимки товаров)
-- ============================================================================
-- Каждый раз, когда парсер отдаёт данные о товаре, мы сохраняем полный снимок.
-- Это позволяет:
-- - Видеть историю изменений цен/описаний
-- - Пересобирать карточки при улучшении AI
-- - Отлаживать проблемы с парсингом

CREATE TABLE IF NOT EXISTS raw_product_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Источник данных
    source_name VARCHAR(50) NOT NULL,           -- 'petrovich', 'leroy', 'vseinstrumenti'
    source_url VARCHAR(500) NOT NULL,           -- Полный URL страницы товара
    external_id VARCHAR(100),                   -- ID товара на сайте донора
    
    -- Сырой JSON — ВЕСЬ ответ парсера
    raw_data JSONB NOT NULL,                    -- Содержит: name, brand, attributes, images, price, html-snippets и т.д.
    
    -- Контрольные хэши для быстрой дедупликации
    content_hash VARCHAR(64),                   -- SHA256 от raw_data (для отсечения полных дублей)
    
    -- Извлечённые идентификаторы для поиска дублей
    extracted_ean VARCHAR(20),                  -- Штрих-код (EAN-13/EAN-8) если удалось извлечь
    extracted_sku VARCHAR(50),                  -- Артикул производителя если удалось извлечь
    extracted_brand VARCHAR(100),               -- Бренд для нормализации
    
    -- Статус обработки
    processed BOOLEAN DEFAULT FALSE,            -- Обработан ли снимок пайплайном MDM
    processed_at TIMESTAMP WITH TIME ZONE,      -- Когда обработан
    processing_result VARCHAR(50),              -- 'new_product', 'enriched', 'duplicate', 'error'
    linked_product_uuid UUID,                   -- Ссылка на созданный/обновлённый ProductFamily
    
    -- Метаданные
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    parser_version VARCHAR(20)                  -- Версия парсера для отладки
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_raw_snapshots_source_url ON raw_product_snapshots(source_url);
CREATE INDEX IF NOT EXISTS idx_raw_snapshots_source_name ON raw_product_snapshots(source_name);
CREATE INDEX IF NOT EXISTS idx_raw_snapshots_external_id ON raw_product_snapshots(source_name, external_id);
CREATE INDEX IF NOT EXISTS idx_raw_snapshots_content_hash ON raw_product_snapshots(content_hash);
CREATE INDEX IF NOT EXISTS idx_raw_snapshots_processed ON raw_product_snapshots(processed) WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_raw_snapshots_ean ON raw_product_snapshots(extracted_ean) WHERE extracted_ean IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_snapshots_sku ON raw_product_snapshots(extracted_sku) WHERE extracted_sku IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_snapshots_brand ON raw_product_snapshots(extracted_brand);
CREATE INDEX IF NOT EXISTS idx_raw_snapshots_created ON raw_product_snapshots(created_at DESC);

-- GIN индекс для поиска по JSONB
CREATE INDEX IF NOT EXISTS idx_raw_snapshots_raw_data ON raw_product_snapshots USING GIN (raw_data);

-- ============================================================================
-- 2. PRODUCT SOURCE LINKS (Связь товара с источниками)
-- ============================================================================
-- Один ProductFamily может быть связан с несколькими источниками
-- (Петрович, Леруа, ВсеИнструменты — один и тот же товар)

CREATE TABLE IF NOT EXISTS product_source_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_uuid UUID NOT NULL REFERENCES product_families(uuid) ON DELETE CASCADE,
    
    -- Источник
    source_name VARCHAR(50) NOT NULL,
    source_url VARCHAR(500) NOT NULL,
    external_id VARCHAR(100),
    
    -- Приоритет источника (чем меньше, тем приоритетнее)
    priority INTEGER DEFAULT 100,
    
    -- Какие данные взяты из этого источника
    contributes_name BOOLEAN DEFAULT FALSE,
    contributes_description BOOLEAN DEFAULT FALSE,
    contributes_images BOOLEAN DEFAULT FALSE,
    contributes_price BOOLEAN DEFAULT FALSE,
    contributes_attributes BOOLEAN DEFAULT FALSE,
    
    -- Статус
    is_active BOOLEAN DEFAULT TRUE,
    last_synced_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(product_uuid, source_name, source_url)
);

CREATE INDEX IF NOT EXISTS idx_product_sources_product ON product_source_links(product_uuid);
CREATE INDEX IF NOT EXISTS idx_product_sources_source ON product_source_links(source_name, source_url);

-- ============================================================================
-- 3. ENRICHMENT AUDIT LOG (Лог обогащения для отладки)
-- ============================================================================
-- Записываем каждое действие MDM пайплайна для аудита

CREATE TABLE IF NOT EXISTS enrichment_audit_log (
    id BIGSERIAL PRIMARY KEY,
    
    snapshot_id UUID REFERENCES raw_product_snapshots(id),
    product_uuid UUID REFERENCES product_families(uuid),
    
    action VARCHAR(50) NOT NULL,                -- 'created', 'merged', 'enriched_images', 'enriched_attributes', 'linked_manufacturer'
    action_details JSONB,                       -- Детали: что именно было добавлено/изменено
    
    -- AI контекст (если использовался)
    ai_model VARCHAR(50),
    ai_confidence DECIMAL(5,4),                 -- Уверенность AI (0.0000 - 1.0000)
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_enrichment_audit_product ON enrichment_audit_log(product_uuid);
CREATE INDEX IF NOT EXISTS idx_enrichment_audit_snapshot ON enrichment_audit_log(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_enrichment_audit_action ON enrichment_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_enrichment_audit_created ON enrichment_audit_log(created_at DESC);

-- ============================================================================
-- 4. ДОБАВЛЯЕМ СВЯЗЬ ТОВАРА С ПРОИЗВОДИТЕЛЕМ
-- ============================================================================

ALTER TABLE product_families 
    ADD COLUMN IF NOT EXISTS manufacturer_id UUID REFERENCES manufacturers(id);

CREATE INDEX IF NOT EXISTS idx_product_families_manufacturer 
    ON product_families(manufacturer_id) WHERE manufacturer_id IS NOT NULL;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE raw_product_snapshots IS 'Сырые данные от парсеров. Храним всё для истории и пересборки.';
COMMENT ON COLUMN raw_product_snapshots.raw_data IS 'Полный JSON от парсера: имя, бренд, атрибуты, картинки, цена, html-куски';
COMMENT ON COLUMN raw_product_snapshots.content_hash IS 'SHA256 хэш raw_data для быстрого отсечения полных дубликатов';
COMMENT ON COLUMN raw_product_snapshots.extracted_ean IS 'EAN штрих-код, извлечённый из raw_data для точной дедупликации';

COMMENT ON TABLE product_source_links IS 'Связь товара с источниками. Один товар = много магазинов.';
COMMENT ON COLUMN product_source_links.priority IS 'Приоритет источника. 1 = официальный сайт, 100 = агрегатор';
COMMENT ON COLUMN product_source_links.contributes_name IS 'TRUE если название товара взято из этого источника';

COMMENT ON TABLE enrichment_audit_log IS 'Аудит всех действий MDM пайплайна для отладки и аналитики';
