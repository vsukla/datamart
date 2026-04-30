-- Migration 014: Education graduation rates at county level
-- Populated by ingestion/ingest_ed_graduation.py

BEGIN;

CREATE TABLE IF NOT EXISTS ed_graduation (
    id             SERIAL      PRIMARY KEY,
    fips           VARCHAR(5)  NOT NULL REFERENCES geo_entities(fips),
    school_year    SMALLINT    NOT NULL,
    grad_rate_all  NUMERIC(5,1),
    grad_rate_ecd  NUMERIC(5,1),
    cohort_all     INTEGER,
    num_districts  SMALLINT,
    fetched_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (fips, school_year)
);

CREATE INDEX IF NOT EXISTS idx_ed_graduation_fips ON ed_graduation (fips);
CREATE INDEX IF NOT EXISTS idx_ed_graduation_year ON ed_graduation (school_year);

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
    c.unemployment_rate  AS census_unemployment_rate,
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
    a.ozone_days,
    -- FBI Crime (most recent year)
    f.year          AS crime_year,
    f.violent_crimes,
    f.violent_crime_rate,
    f.property_crimes,
    f.property_crime_rate,
    -- HUD Fair Market Rents (most recent year)
    h.year          AS hud_year,
    h.fmr_0br,
    h.fmr_1br,
    h.fmr_2br,
    h.fmr_3br,
    h.fmr_4br,
    -- NHTSA Traffic Fatalities (most recent year)
    t.year          AS traffic_year,
    t.fatalities,
    t.fatality_rate,
    -- Education graduation rates (most recent school year)
    e.school_year   AS grad_year,
    e.grad_rate_all,
    e.grad_rate_ecd,
    e.cohort_all,
    e.num_districts
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
LEFT JOIN LATERAL (
    SELECT * FROM hud_fmr WHERE fips = g.fips ORDER BY year DESC LIMIT 1
) h ON TRUE
LEFT JOIN LATERAL (
    SELECT * FROM nhtsa_traffic WHERE fips = g.fips ORDER BY year DESC LIMIT 1
) t ON TRUE
LEFT JOIN LATERAL (
    SELECT * FROM ed_graduation WHERE fips = g.fips ORDER BY school_year DESC LIMIT 1
) e ON TRUE
WHERE g.geo_type = 'county';

INSERT INTO datasets (source_key, name, description, source_url, entity_type, update_cadence)
VALUES (
    'ed_graduation',
    'Education Graduation Rates (EDFacts)',
    'County-level 4-year adjusted cohort graduation rates aggregated from district-level EDFacts ACGR data. Includes overall rate and economically disadvantaged subgroup.',
    'https://www2.ed.gov/about/inits/ed/edfacts/data-files/index.html',
    'county',
    'annual'
) ON CONFLICT (source_key) DO NOTHING;

INSERT INTO schema_migrations (version, description)
VALUES (14, 'ed_graduation: Education 4-year graduation rates at county level')
ON CONFLICT DO NOTHING;

COMMIT;
