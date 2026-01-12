-- Migration: 006_category_service
-- Description: Create categories and category_mappings tables for unified taxonomy

-- Единая таксономия категорий
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    parent_id INTEGER REFERENCES categories(id),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,  -- 0=root, 1=L1, 2=L2, 3=L3
    path_ids INTEGER[] NOT NULL DEFAULT '{}',  -- Materialized path [1,5,23]
    path_names TEXT[] NOT NULL DEFAULT '{}',  -- ['Стройматериалы', 'Кирпич', 'Керамический']
    product_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Маппинг категорий от источников
CREATE TABLE category_mappings (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,  -- petrovich.ru, leroymerlin.ru
    source_path TEXT[] NOT NULL,  -- Оригинальный breadcrumb ['Стройматериалы', 'Кирпичи']
    source_path_hash VARCHAR(64) NOT NULL,  -- SHA256 для быстрого поиска
    category_id INTEGER REFERENCES categories(id),
    confidence DECIMAL(3,2) DEFAULT 1.0,  -- 0.0-1.0, для AI-маппинга
    is_manual BOOLEAN DEFAULT FALSE,  -- Ручной маппинг или автоматический
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(source_name, source_path_hash)
);

-- Индексы
CREATE INDEX idx_categories_parent ON categories(parent_id);
CREATE INDEX idx_categories_slug ON categories(slug);
CREATE INDEX idx_categories_path ON categories USING GIN(path_ids);
CREATE INDEX idx_category_mappings_hash ON category_mappings(source_path_hash);
CREATE INDEX idx_category_mappings_source ON category_mappings(source_name);

-- Комментарии
COMMENT ON TABLE categories IS 'Unified category taxonomy for all products';
COMMENT ON TABLE category_mappings IS 'Mappings from source categories to unified taxonomy';
COMMENT ON COLUMN categories.path_ids IS 'Materialized path as array of category IDs';
COMMENT ON COLUMN categories.path_names IS 'Materialized path as array of category names';
COMMENT ON COLUMN category_mappings.source_path_hash IS 'SHA256 hash of source_path for fast lookup';
COMMENT ON COLUMN category_mappings.confidence IS 'Confidence score for AI-based mappings (0.0-1.0)';
