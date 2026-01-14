-- Migration: 008_add_vector_embeddings
-- Description: Enable pgvector and store semantic embeddings for products

-- Ensure pgvector extension is available
CREATE EXTENSION IF NOT EXISTS vector;

-- Table for product embeddings
CREATE TABLE IF NOT EXISTS product_embeddings (
    product_uuid UUID PRIMARY KEY REFERENCES product_families(uuid) ON DELETE CASCADE,
    embedding vector(768) NOT NULL,
    model VARCHAR(100) NOT NULL DEFAULT 'text-embedding-004',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Track changes to embeddings
CREATE INDEX IF NOT EXISTS idx_product_embeddings_updated_at
    ON product_embeddings(updated_at DESC);

-- Approximate nearest-neighbour index for semantic search
CREATE INDEX IF NOT EXISTS idx_product_embeddings_embedding
    ON product_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

COMMENT ON TABLE product_embeddings IS 'Semantic embeddings for product families';
COMMENT ON COLUMN product_embeddings.embedding IS 'pgvector embedding generated from product data';
COMMENT ON COLUMN product_embeddings.model IS 'Model identifier used to generate the embedding';