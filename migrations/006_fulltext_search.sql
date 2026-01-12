-- Migration: 006_fulltext_search
-- Description: Add full-text search support using PostgreSQL ts_vector

-- Add search_vector column for full-text search
ALTER TABLE product_families 
ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- Create GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_product_families_search 
ON product_families USING GIN(search_vector);

-- Function to update search_vector
CREATE OR REPLACE FUNCTION update_product_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('russian', COALESCE(NEW.name_technical, '')), 'A') ||
        setweight(to_tsvector('russian', COALESCE(NEW.brand, '')), 'B') ||
        setweight(to_tsvector('russian', COALESCE(NEW.description, '')), 'C') ||
        setweight(to_tsvector('russian', COALESCE(NEW.sku, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for auto-updating search_vector
CREATE TRIGGER product_search_vector_update
BEFORE INSERT OR UPDATE ON product_families
FOR EACH ROW EXECUTE FUNCTION update_product_search_vector();

-- Update existing records
UPDATE product_families SET search_vector = 
    setweight(to_tsvector('russian', COALESCE(name_technical, '')), 'A') ||
    setweight(to_tsvector('russian', COALESCE(brand, '')), 'B') ||
    setweight(to_tsvector('russian', COALESCE(description, '')), 'C') ||
    setweight(to_tsvector('russian', COALESCE(sku, '')), 'B');

COMMENT ON COLUMN product_families.search_vector IS 'Full-text search vector (auto-updated by trigger)';
