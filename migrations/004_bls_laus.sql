-- Migration 004: BLS Local Area Unemployment Statistics (annual averages)
-- Populated by ingestion/ingest_bls_laus.py

BEGIN;

CREATE TABLE IF NOT EXISTS bls_laus (
    id                SERIAL      PRIMARY KEY,
    fips              VARCHAR(5)  NOT NULL REFERENCES geo_entities(fips),
    year              SMALLINT    NOT NULL,
    labor_force       INTEGER,
    employed          INTEGER,
    unemployed        INTEGER,
    unemployment_rate NUMERIC(5,1),
    fetched_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (fips, year)
);

CREATE INDEX IF NOT EXISTS idx_bls_laus_fips ON bls_laus (fips);
CREATE INDEX IF NOT EXISTS idx_bls_laus_year ON bls_laus (year);

INSERT INTO schema_migrations (version, description)
VALUES (4, 'bls_laus: BLS Local Area Unemployment Statistics')
ON CONFLICT DO NOTHING;

COMMIT;
