-- Migration: 002_create_prices
-- Description: Create prices table for product family pricing

CREATE TABLE prices (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_family_uuid UUID NOT NULL REFERENCES product_families(uuid) ON DELETE CASCADE,
    amount DECIMAL(15,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'RUB',
    supplier_id BIGINT,
    valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_to TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_prices_product ON prices(product_family_uuid);
CREATE INDEX idx_prices_supplier ON prices(supplier_id) WHERE supplier_id IS NOT NULL;
CREATE INDEX idx_prices_active ON prices(product_family_uuid, is_active) WHERE is_active = true;
CREATE INDEX idx_prices_validity ON prices(valid_from, valid_to);

COMMENT ON TABLE prices IS 'Product prices from various suppliers';
COMMENT ON COLUMN prices.product_family_uuid IS 'Reference to product family';
COMMENT ON COLUMN prices.amount IS 'Price amount';
COMMENT ON COLUMN prices.currency IS 'ISO 4217 currency code';
COMMENT ON COLUMN prices.supplier_id IS 'Reference to supplier';
