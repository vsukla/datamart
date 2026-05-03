-- Migration 017: schema_snapshots — detect upstream column drift between vintages
-- Captured once per ingestion run on the first successful parse.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_snapshots (
    id               SERIAL       PRIMARY KEY,
    source_key       VARCHAR(30)  NOT NULL REFERENCES datasets(source_key),
    ingestion_run_id INTEGER      REFERENCES ingestion_runs(id),
    captured_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    column_names     TEXT[]       NOT NULL,
    schema_hash      CHAR(64)     NOT NULL  -- SHA-256 of sorted column names
);

CREATE INDEX IF NOT EXISTS idx_schema_snapshots_source_key ON schema_snapshots (source_key, captured_at DESC);

INSERT INTO schema_migrations (version, description)
VALUES (17, 'governance: schema_snapshots for column drift detection')
ON CONFLICT DO NOTHING;

COMMIT;
