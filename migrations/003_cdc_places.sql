-- Migration 003: CDC PLACES county-level health outcomes
-- Populated by ingestion/ingest_cdc_places.py

BEGIN;

CREATE TABLE IF NOT EXISTS cdc_places (
    id                   SERIAL       PRIMARY KEY,
    fips                 VARCHAR(5)   NOT NULL REFERENCES geo_entities(fips),
    year                 SMALLINT     NOT NULL,
    pct_obesity          NUMERIC(5,1),
    pct_diabetes         NUMERIC(5,1),
    pct_smoking          NUMERIC(5,1),
    pct_hypertension     NUMERIC(5,1),
    pct_depression       NUMERIC(5,1),
    pct_no_lpa           NUMERIC(5,1),
    pct_poor_mental_health NUMERIC(5,1),
    fetched_at           TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (fips, year)
);

CREATE INDEX IF NOT EXISTS idx_cdc_places_fips       ON cdc_places (fips);
CREATE INDEX IF NOT EXISTS idx_cdc_places_year       ON cdc_places (year);

INSERT INTO schema_migrations (version, description)
VALUES (3, 'cdc_places: CDC PLACES county health outcomes')
ON CONFLICT DO NOTHING;

COMMIT;
