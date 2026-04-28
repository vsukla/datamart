-- Migration 009: datasets catalog — tracks all ingested sources with quality stats
-- Populated by ingestion scripts and compute_data_quality.py

BEGIN;

CREATE TABLE IF NOT EXISTS datasets (
    id                   SERIAL       PRIMARY KEY,
    source_key           VARCHAR(30)  NOT NULL UNIQUE,
    name                 VARCHAR(100) NOT NULL,
    description          TEXT,
    source_url           TEXT,
    entity_type          VARCHAR(20)  NOT NULL DEFAULT 'county',
    update_cadence       VARCHAR(20),
    -- quality stats (updated by compute_data_quality.py)
    row_count            INTEGER,
    null_rates           JSONB,
    last_ingested_at     TIMESTAMPTZ,
    quality_computed_at  TIMESTAMPTZ,
    created_at           TIMESTAMPTZ  DEFAULT NOW()
);

-- Seed the known sources
INSERT INTO datasets (source_key, name, description, source_url, entity_type, update_cadence) VALUES
    ('census_acs5',
     'Census ACS 5-Year Estimates',
     'American Community Survey 5-year estimates: population, income, education, housing, poverty.',
     'https://api.census.gov/data/2022/acs/acs5',
     'county', 'annual'),
    ('cdc_places',
     'CDC PLACES',
     'CDC PLACES: county-level health outcomes including obesity, diabetes, smoking, hypertension.',
     'https://data.cdc.gov/resource/cwsq-ngmh.json',
     'county', 'annual'),
    ('bls_laus',
     'BLS Local Area Unemployment Statistics',
     'BLS LAUS: annual average labor force, employment, and unemployment by county.',
     'https://www.bls.gov/lau/',
     'county', 'annual'),
    ('usda_food_env',
     'USDA Food Environment Atlas',
     'USDA ERS: food access, grocery stores, fast food, SNAP participation, farmers markets.',
     'https://www.ers.usda.gov/data-products/food-environment-atlas/',
     'county', 'biennial'),
    ('epa_aqi',
     'EPA Air Quality Index',
     'EPA AQS: annual AQI summary — median, max, good/moderate/unhealthy days, PM2.5, ozone.',
     'https://aqs.epa.gov/aqsweb/airdata/',
     'county', 'annual'),
    ('fbi_crime',
     'FBI Crime Data',
     'FBI UCR/NIBRS: county-level violent and property crime counts and rates per 100k population.',
     'https://cde.ucr.cjis.gov/',
     'county', 'annual')
ON CONFLICT (source_key) DO NOTHING;

INSERT INTO schema_migrations (version, description)
VALUES (9, 'datasets: source catalog with quality stats')
ON CONFLICT DO NOTHING;

COMMIT;
