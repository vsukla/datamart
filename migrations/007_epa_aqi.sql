-- Migration 007: EPA Air Quality Index county-level data
-- Populated by ingestion/ingest_epa_aqi.py

BEGIN;

CREATE TABLE IF NOT EXISTS epa_aqi (
    id                       SERIAL       PRIMARY KEY,
    fips                     VARCHAR(5)   NOT NULL REFERENCES geo_entities(fips),
    year                     SMALLINT     NOT NULL,
    days_with_aqi            SMALLINT,
    good_days                SMALLINT,
    moderate_days            SMALLINT,
    unhealthy_sensitive_days SMALLINT,
    unhealthy_days           SMALLINT,
    very_unhealthy_days      SMALLINT,
    hazardous_days           SMALLINT,
    max_aqi                  SMALLINT,
    median_aqi               NUMERIC(6, 1),
    pm25_days                SMALLINT,
    ozone_days               SMALLINT,
    fetched_at               TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (fips, year)
);

CREATE INDEX IF NOT EXISTS idx_epa_aqi_fips ON epa_aqi (fips);
CREATE INDEX IF NOT EXISTS idx_epa_aqi_year ON epa_aqi (year);

-- Extend county_profile view to include EPA AQI
CREATE OR REPLACE VIEW county_profile AS
SELECT
    g.fips,
    g.name          AS county_name,
    g.state_fips,
    -- Census ACS5 (most recent year)
    c.year          AS census_year,
    c.population,
    c.median_income,
    c.pct_bachelors,
    c.median_home_value,
    c.pct_owner_occupied,
    c.pct_poverty,
    c.unemployment_rate AS census_unemployment_rate,
    -- CDC PLACES (most recent year)
    p.year          AS places_year,
    p.pct_obesity,
    p.pct_diabetes,
    p.pct_smoking,
    p.pct_hypertension,
    p.pct_depression,
    p.pct_no_lpa,
    p.pct_poor_mental_health,
    -- BLS LAUS (most recent year)
    b.year          AS bls_year,
    b.labor_force,
    b.employed,
    b.unemployed,
    b.unemployment_rate AS bls_unemployment_rate,
    -- USDA Food Environment (most recent year)
    u.data_year     AS usda_year,
    u.pct_low_food_access,
    u.groceries_per_1000,
    u.fast_food_per_1000,
    u.pct_snap,
    u.farmers_markets,
    -- EPA AQI (most recent year)
    a.year          AS aqi_year,
    a.median_aqi,
    a.max_aqi,
    a.good_days,
    a.moderate_days,
    a.unhealthy_sensitive_days,
    a.unhealthy_days,
    a.very_unhealthy_days,
    a.hazardous_days,
    a.pm25_days,
    a.ozone_days
FROM geo_entities g
LEFT JOIN LATERAL (
    SELECT * FROM census_acs5 WHERE fips = g.fips ORDER BY year DESC LIMIT 1
) c ON TRUE
LEFT JOIN LATERAL (
    SELECT * FROM cdc_places WHERE fips = g.fips ORDER BY year DESC LIMIT 1
) p ON TRUE
LEFT JOIN LATERAL (
    SELECT * FROM bls_laus WHERE fips = g.fips ORDER BY year DESC LIMIT 1
) b ON TRUE
LEFT JOIN LATERAL (
    SELECT * FROM usda_food_env WHERE fips = g.fips ORDER BY data_year DESC LIMIT 1
) u ON TRUE
LEFT JOIN LATERAL (
    SELECT * FROM epa_aqi WHERE fips = g.fips ORDER BY year DESC LIMIT 1
) a ON TRUE
WHERE g.geo_type = 'county';

INSERT INTO schema_migrations (version, description)
VALUES (7, 'epa_aqi: EPA Air Quality Index county data')
ON CONFLICT DO NOTHING;

COMMIT;
