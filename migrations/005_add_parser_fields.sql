-- Migration: 005_add_parser_fields
-- Description: Add fields for parser data and related tables for attributes, documents, and images

-- Add parser-related fields to product_families
ALTER TABLE product_families 
ADD COLUMN IF NOT EXISTS source_url TEXT,
ADD COLUMN IF NOT EXISTS source_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS external_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS sku VARCHAR(255),
ADD COLUMN IF NOT EXISTS brand VARCHAR(255),
ADD COLUMN IF NOT EXISTS description TEXT,
ADD COLUMN IF NOT EXISTS schema_org_data JSONB;

-- Add unique constraint on source_url (partial index to allow multiple NULLs)
CREATE UNIQUE INDEX IF NOT EXISTS idx_product_families_source_url 
ON product_families(source_url) WHERE source_url IS NOT NULL;

-- Indexes for filtering and searching
CREATE INDEX IF NOT EXISTS idx_product_families_brand 
ON product_families(brand) WHERE brand IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_product_families_sku 
ON product_families(sku) WHERE sku IS NOT NULL;

-- Table for product attributes
CREATE TABLE IF NOT EXISTS product_attributes (
    id SERIAL PRIMARY KEY,
    product_uuid UUID NOT NULL REFERENCES product_families(uuid) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    value TEXT NOT NULL,
    unit VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(product_uuid, name)
);

CREATE INDEX IF NOT EXISTS idx_product_attributes_product_uuid 
ON product_attributes(product_uuid);

-- Table for product documents (certificates, manuals)
CREATE TABLE IF NOT EXISTS product_documents (
    id SERIAL PRIMARY KEY,
    product_uuid UUID NOT NULL REFERENCES product_families(uuid) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    url TEXT NOT NULL,
    format VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_product_documents_product_uuid 
ON product_documents(product_uuid);

CREATE INDEX IF NOT EXISTS idx_product_documents_type 
ON product_documents(document_type);

-- Table for product images
CREATE TABLE IF NOT EXISTS product_images (
    id SERIAL PRIMARY KEY,
    product_uuid UUID NOT NULL REFERENCES product_families(uuid) ON DELETE CASCADE,
    url TEXT NOT NULL,
    alt_text VARCHAR(500),
    is_main BOOLEAN DEFAULT FALSE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_product_images_product_uuid 
ON product_images(product_uuid);

CREATE INDEX IF NOT EXISTS idx_product_images_is_main 
ON product_images(product_uuid, is_main) WHERE is_main = TRUE;

-- Comments for documentation
COMMENT ON COLUMN product_families.source_url IS 'Original URL from parser (used for deduplication)';
COMMENT ON COLUMN product_families.source_name IS 'Name of the source (e.g., manufacturer website)';
COMMENT ON COLUMN product_families.external_id IS 'External ID from the source system';
COMMENT ON COLUMN product_families.sku IS 'Stock Keeping Unit from parser';
COMMENT ON COLUMN product_families.brand IS 'Brand/manufacturer name';
COMMENT ON COLUMN product_families.description IS 'Product description from parser';
COMMENT ON COLUMN product_families.schema_org_data IS 'Schema.org structured data in JSON format';

COMMENT ON TABLE product_attributes IS 'Product attributes (key-value pairs)';
COMMENT ON TABLE product_documents IS 'Product documents (certificates, manuals, etc.)';
COMMENT ON TABLE product_images IS 'Product images with metadata';
