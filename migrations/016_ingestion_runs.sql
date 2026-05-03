-- Migration 016: ingestion_runs — immutable audit log of every ingestion attempt
-- One row per script execution. Never updated after status is set to success/error.

BEGIN;

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id              SERIAL       PRIMARY KEY,
    source_key      VARCHAR(30)  NOT NULL REFERENCES datasets(source_key),
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ,
    status          VARCHAR(20)  NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'success', 'error')),
    rows_loaded     INTEGER,
    rows_rejected   INTEGER,
    file_hash       CHAR(64),    -- SHA-256 hex of the last downloaded raw file
    raw_file_url    TEXT,        -- URL downloaded (for traceability)
    notes           TEXT,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_source_key ON ingestion_runs (source_key);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_started_at ON ingestion_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_status     ON ingestion_runs (status);

INSERT INTO schema_migrations (version, description)
VALUES (16, 'governance: ingestion_runs audit log table')
ON CONFLICT DO NOTHING;

COMMIT;
