-- Migration: Add source_url and raw_data columns to product_families
-- For tracking scraped products and storing original data

-- Add source_url column for deduplication
ALTER TABLE product_families
ADD COLUMN IF NOT EXISTS source_url VARCHAR(2048) UNIQUE;

-- Add raw_data column for storing original scraped data (JSONB for efficient querying)
ALTER TABLE product_families
ADD COLUMN IF NOT EXISTS raw_data JSONB;

-- Add brand column extracted from raw data
ALTER TABLE product_families
ADD COLUMN IF NOT EXISTS brand VARCHAR(255);

-- Create index for fast source_url lookups
CREATE INDEX IF NOT EXISTS idx_product_families_source_url
ON product_families (source_url)
WHERE source_url IS NOT NULL;

-- Create index for brand searches
CREATE INDEX IF NOT EXISTS idx_product_families_brand
ON product_families (brand)
WHERE brand IS NOT NULL;

-- Create GIN index for raw_data JSONB queries
CREATE INDEX IF NOT EXISTS idx_product_families_raw_data
ON product_families USING GIN (raw_data jsonb_path_ops)
WHERE raw_data IS NOT NULL;

-- Comment on columns
COMMENT ON COLUMN product_families.source_url IS 'Original URL from where the product was scraped';
COMMENT ON COLUMN product_families.raw_data IS 'Original scraped data in JSON format';
COMMENT ON COLUMN product_families.brand IS 'Product brand name';
