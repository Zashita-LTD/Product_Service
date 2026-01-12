-- Migration: 001_create_product_families
-- Description: Create product_families table

CREATE TABLE product_families (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name_technical VARCHAR(500) NOT NULL,
    category_id BIGINT NOT NULL,
    quality_score DECIMAL(3,2),
    enrichment_status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_families_category ON product_families(category_id);
CREATE INDEX idx_families_uuid ON product_families(uuid);
CREATE INDEX idx_families_name ON product_families(name_technical);
CREATE INDEX idx_families_enrichment_status ON product_families(enrichment_status);
CREATE INDEX idx_families_created_at ON product_families(created_at DESC);

-- Unique constraint on technical name within category
CREATE UNIQUE INDEX idx_families_name_category ON product_families(name_technical, category_id);

COMMENT ON TABLE product_families IS 'Product families - core entity for product management';
COMMENT ON COLUMN product_families.uuid IS 'Public unique identifier';
COMMENT ON COLUMN product_families.name_technical IS 'Technical name of the product';
COMMENT ON COLUMN product_families.category_id IS 'Reference to product category';
COMMENT ON COLUMN product_families.quality_score IS 'AI-calculated quality score (0.00 - 1.00)';
COMMENT ON COLUMN product_families.enrichment_status IS 'Status of AI enrichment process';
