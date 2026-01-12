-- Migration: 004_create_outbox
-- Description: Create outbox table for reliable event publishing (Outbox Pattern)

CREATE TABLE outbox_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    retry_count INT DEFAULT 0,
    last_error TEXT
);

-- Indexes for outbox processing
CREATE INDEX idx_outbox_unprocessed ON outbox_events(created_at)
    WHERE processed_at IS NULL;
CREATE INDEX idx_outbox_aggregate ON outbox_events(aggregate_type, aggregate_id);
CREATE INDEX idx_outbox_event_type ON outbox_events(event_type);

-- Partial index for failed events that need retry
CREATE INDEX idx_outbox_retry ON outbox_events(created_at)
    WHERE processed_at IS NULL AND retry_count > 0;

COMMENT ON TABLE outbox_events IS 'Outbox table for reliable event publishing';
COMMENT ON COLUMN outbox_events.aggregate_type IS 'Type of aggregate (e.g., product_family)';
COMMENT ON COLUMN outbox_events.aggregate_id IS 'ID of the aggregate';
COMMENT ON COLUMN outbox_events.event_type IS 'Type of event (e.g., product_family.created)';
COMMENT ON COLUMN outbox_events.payload IS 'JSON payload of the event';
COMMENT ON COLUMN outbox_events.processed_at IS 'When the event was published to Kafka';
