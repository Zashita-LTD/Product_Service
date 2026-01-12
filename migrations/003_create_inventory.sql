-- Migration: 003_create_inventory
-- Description: Create inventory table for stock tracking

CREATE TABLE inventory (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_family_uuid UUID NOT NULL REFERENCES product_families(uuid) ON DELETE CASCADE,
    warehouse_id BIGINT NOT NULL,
    quantity DECIMAL(15,3) NOT NULL DEFAULT 0,
    unit VARCHAR(20) DEFAULT 'pcs',
    reserved_quantity DECIMAL(15,3) DEFAULT 0,
    min_stock_level DECIMAL(15,3),
    max_stock_level DECIMAL(15,3),
    reorder_point DECIMAL(15,3),
    last_stock_check TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_inventory_product ON inventory(product_family_uuid);
CREATE INDEX idx_inventory_warehouse ON inventory(warehouse_id);
CREATE UNIQUE INDEX idx_inventory_product_warehouse ON inventory(product_family_uuid, warehouse_id);
CREATE INDEX idx_inventory_low_stock ON inventory(product_family_uuid)
    WHERE quantity <= min_stock_level;

COMMENT ON TABLE inventory IS 'Product inventory across warehouses';
COMMENT ON COLUMN inventory.product_family_uuid IS 'Reference to product family';
COMMENT ON COLUMN inventory.warehouse_id IS 'Reference to warehouse';
COMMENT ON COLUMN inventory.quantity IS 'Current stock quantity';
COMMENT ON COLUMN inventory.reserved_quantity IS 'Quantity reserved for orders';
