-- Migration 010: add health insurance, commute, and race/ethnicity columns to census_acs5
-- Variables: C27001 (health insurance), B08136/B08301 (commute), B02001/B03003 (race/ethnicity)

BEGIN;

ALTER TABLE census_acs5
    ADD COLUMN IF NOT EXISTS pct_health_insured  NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS mean_commute_minutes NUMERIC(5, 1),
    ADD COLUMN IF NOT EXISTS pct_white            NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS pct_black            NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS pct_hispanic         NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS pct_asian            NUMERIC(5, 2);

-- Rebuild county_profile view to include the new census columns
-- DROP required because CREATE OR REPLACE cannot insert columns mid-list
DROP VIEW IF EXISTS county_profile;
CREATE VIEW county_profile AS
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
    c.unemployment_rate         AS census_unemployment_rate,
    c.pct_health_insured,
    c.mean_commute_minutes,
    c.pct_white,
    c.pct_black,
    c.pct_hispanic,
    c.pct_asian,
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
    b.unemployment_rate         AS bls_unemployment_rate,
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
    a.ozone_days,
    -- FBI Crime (most recent year)
    f.year          AS crime_year,
    f.violent_crimes,
    f.violent_crime_rate,
    f.property_crimes,
    f.property_crime_rate
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
LEFT JOIN LATERAL (
    SELECT * FROM fbi_crime WHERE fips = g.fips ORDER BY year DESC LIMIT 1
) f ON TRUE
WHERE g.geo_type = 'county';

INSERT INTO schema_migrations (version, description)
VALUES (10, 'census_acs5: health insurance, commute time, race/ethnicity columns')
ON CONFLICT DO NOTHING;

COMMIT;
