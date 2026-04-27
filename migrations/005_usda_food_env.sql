-- Migration 005: USDA Food Environment Atlas county-level data
-- Populated by ingestion/ingest_usda_food_env.py

BEGIN;

CREATE TABLE IF NOT EXISTS usda_food_env (
    id                   SERIAL      PRIMARY KEY,
    fips                 VARCHAR(5)  NOT NULL REFERENCES geo_entities(fips),
    data_year            SMALLINT    NOT NULL,
    pct_low_food_access  NUMERIC(5,1),
    groceries_per_1000   NUMERIC(6,2),
    fast_food_per_1000   NUMERIC(6,2),
    pct_snap             NUMERIC(5,1),
    farmers_markets      INTEGER,
    fetched_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (fips, data_year)
);

CREATE INDEX IF NOT EXISTS idx_usda_food_env_fips ON usda_food_env (fips);

INSERT INTO schema_migrations (version, description)
VALUES (5, 'usda_food_env: USDA Food Environment Atlas')
ON CONFLICT DO NOTHING;

COMMIT;
