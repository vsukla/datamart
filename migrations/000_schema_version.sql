-- Migration tracking table. Run this once before any numbered migrations.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER      PRIMARY KEY,
    description VARCHAR(200) NOT NULL,
    applied_at  TIMESTAMPTZ  DEFAULT NOW()
);
