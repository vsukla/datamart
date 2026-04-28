-- Datamart — complete current schema
-- Apply this to a fresh database for a clean install.
-- For incremental changes to an existing database use migrations/migrate.sh instead.
--
-- Last updated: migration 010

BEGIN;

-- ---------------------------------------------------------------------------
-- Migration tracking
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS datasets (
    id                   SERIAL       PRIMARY KEY,
    source_key           VARCHAR(30)  NOT NULL UNIQUE,
    name                 VARCHAR(100) NOT NULL,
    description          TEXT,
    source_url           TEXT,
    entity_type          VARCHAR(20)  NOT NULL DEFAULT 'county',
    update_cadence       VARCHAR(20),
    row_count            INTEGER,
    null_rates           JSONB,
    last_ingested_at     TIMESTAMPTZ,
    quality_computed_at  TIMESTAMPTZ,
    created_at           TIMESTAMPTZ  DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER     PRIMARY KEY,
    description TEXT        NOT NULL,
    applied_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Core: geography reference + Census ACS5 estimates
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS geo_entities (
    fips        VARCHAR(5)   PRIMARY KEY,
    geo_type    VARCHAR(10)  NOT NULL CHECK (geo_type IN ('state', 'county')),
    name        VARCHAR(200) NOT NULL,
    state_fips  CHAR(2)      NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_geo_entities_geo_type   ON geo_entities (geo_type);
CREATE INDEX IF NOT EXISTS idx_geo_entities_state_fips ON geo_entities (state_fips);

CREATE TABLE IF NOT EXISTS census_acs5 (
    id                  SERIAL       PRIMARY KEY,
    fips                VARCHAR(5)   NOT NULL REFERENCES geo_entities(fips),
    year                SMALLINT     NOT NULL,
    population          INTEGER,
    median_income       INTEGER,
    pct_bachelors       NUMERIC(5, 2),
    median_home_value   INTEGER,
    pct_owner_occupied  NUMERIC(5, 2),
    pct_poverty         NUMERIC(5, 2),
    unemployment_rate    NUMERIC(5, 2),
    pct_health_insured   NUMERIC(5, 2),
    mean_commute_minutes NUMERIC(5, 1),
    pct_white            NUMERIC(5, 2),
    pct_black            NUMERIC(5, 2),
    pct_hispanic         NUMERIC(5, 2),
    pct_asian            NUMERIC(5, 2),
    fetched_at           TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (fips, year)
);

CREATE INDEX IF NOT EXISTS idx_census_acs5_fips ON census_acs5 (fips);
CREATE INDEX IF NOT EXISTS idx_census_acs5_year ON census_acs5 (year);

-- ---------------------------------------------------------------------------
-- Pre-computed aggregates (recomputed daily by compute_aggregates.py)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agg_national_summary (
    id                      SERIAL       PRIMARY KEY,
    year                    SMALLINT     NOT NULL UNIQUE,
    total_population        BIGINT,
    avg_median_income       NUMERIC(10, 0),
    avg_pct_bachelors       NUMERIC(5, 2),
    avg_median_home_value   NUMERIC(10, 0),
    avg_pct_owner_occupied  NUMERIC(5, 2),
    avg_pct_poverty         NUMERIC(5, 2),
    avg_unemployment_rate   NUMERIC(5, 2),
    computed_at             TIMESTAMPTZ  DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agg_state_summary (
    id                      SERIAL       PRIMARY KEY,
    state_fips              CHAR(2)      NOT NULL,
    year                    SMALLINT     NOT NULL,
    total_population        BIGINT,
    avg_median_income       NUMERIC(10, 0),
    avg_pct_bachelors       NUMERIC(5, 2),
    avg_median_home_value   NUMERIC(10, 0),
    avg_pct_owner_occupied  NUMERIC(5, 2),
    avg_pct_poverty         NUMERIC(5, 2),
    avg_unemployment_rate   NUMERIC(5, 2),
    computed_at             TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (state_fips, year)
);

CREATE INDEX IF NOT EXISTS idx_agg_state_summary_state_year
    ON agg_state_summary (state_fips, year);

CREATE TABLE IF NOT EXISTS agg_rankings (
    id          SERIAL       PRIMARY KEY,
    fips        VARCHAR(5)   NOT NULL,
    state_fips  CHAR(2)      NOT NULL,
    geo_type    VARCHAR(10)  NOT NULL,
    year        SMALLINT     NOT NULL,
    metric      VARCHAR(30)  NOT NULL,
    value       NUMERIC(12, 2),
    rank        INTEGER,
    percentile  NUMERIC(5, 2),
    peer_count  INTEGER,
    computed_at TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (fips, year, metric)
);

CREATE INDEX IF NOT EXISTS idx_agg_rankings_geo_year_metric
    ON agg_rankings (geo_type, year, metric);
CREATE INDEX IF NOT EXISTS idx_agg_rankings_state_fips
    ON agg_rankings (state_fips);

CREATE TABLE IF NOT EXISTS agg_yoy (
    id          SERIAL       PRIMARY KEY,
    fips        VARCHAR(5)   NOT NULL,
    state_fips  CHAR(2)      NOT NULL,
    geo_type    VARCHAR(10)  NOT NULL,
    year        SMALLINT     NOT NULL,
    metric      VARCHAR(30)  NOT NULL,
    value       NUMERIC(12, 2),
    prev_value  NUMERIC(12, 2),
    change_abs  NUMERIC(12, 2),
    change_pct  NUMERIC(7, 2),
    computed_at TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (fips, year, metric)
);

CREATE INDEX IF NOT EXISTS idx_agg_yoy_geo_year_metric
    ON agg_yoy (geo_type, year, metric);
CREATE INDEX IF NOT EXISTS idx_agg_yoy_state_fips
    ON agg_yoy (state_fips);

-- ---------------------------------------------------------------------------
-- External data sources (county-level)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cdc_places (
    id                     SERIAL       PRIMARY KEY,
    fips                   VARCHAR(5)   NOT NULL REFERENCES geo_entities(fips),
    year                   SMALLINT     NOT NULL,
    pct_obesity            NUMERIC(5, 1),
    pct_diabetes           NUMERIC(5, 1),
    pct_smoking            NUMERIC(5, 1),
    pct_hypertension       NUMERIC(5, 1),
    pct_depression         NUMERIC(5, 1),
    pct_no_lpa             NUMERIC(5, 1),
    pct_poor_mental_health NUMERIC(5, 1),
    fetched_at             TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (fips, year)
);

CREATE INDEX IF NOT EXISTS idx_cdc_places_fips ON cdc_places (fips);
CREATE INDEX IF NOT EXISTS idx_cdc_places_year ON cdc_places (year);

CREATE TABLE IF NOT EXISTS bls_laus (
    id                SERIAL      PRIMARY KEY,
    fips              VARCHAR(5)  NOT NULL REFERENCES geo_entities(fips),
    year              SMALLINT    NOT NULL,
    labor_force       INTEGER,
    employed          INTEGER,
    unemployed        INTEGER,
    unemployment_rate NUMERIC(5, 1),
    fetched_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (fips, year)
);

CREATE INDEX IF NOT EXISTS idx_bls_laus_fips ON bls_laus (fips);
CREATE INDEX IF NOT EXISTS idx_bls_laus_year ON bls_laus (year);

CREATE TABLE IF NOT EXISTS usda_food_env (
    id                   SERIAL      PRIMARY KEY,
    fips                 VARCHAR(5)  NOT NULL REFERENCES geo_entities(fips),
    data_year            SMALLINT    NOT NULL,
    pct_low_food_access  NUMERIC(5, 1),
    groceries_per_1000   NUMERIC(6, 2),
    fast_food_per_1000   NUMERIC(6, 2),
    pct_snap             NUMERIC(5, 1),
    farmers_markets      INTEGER,
    fetched_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (fips, data_year)
);

CREATE INDEX IF NOT EXISTS idx_usda_food_env_fips ON usda_food_env (fips);

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

CREATE TABLE IF NOT EXISTS fbi_crime (
    id                   SERIAL       PRIMARY KEY,
    fips                 VARCHAR(5)   NOT NULL REFERENCES geo_entities(fips),
    year                 SMALLINT     NOT NULL,
    population_covered   INTEGER,
    violent_crimes       INTEGER,
    violent_crime_rate   NUMERIC(8, 1),
    property_crimes      INTEGER,
    property_crime_rate  NUMERIC(8, 1),
    fetched_at           TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (fips, year)
);

CREATE INDEX IF NOT EXISTS idx_fbi_crime_fips ON fbi_crime (fips);
CREATE INDEX IF NOT EXISTS idx_fbi_crime_year ON fbi_crime (year);

-- ---------------------------------------------------------------------------
-- Cross-source county profile view
-- ---------------------------------------------------------------------------

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

-- ---------------------------------------------------------------------------
-- Mark all migrations as applied (for fresh installs via this file)
-- ---------------------------------------------------------------------------

INSERT INTO schema_migrations (version, description) VALUES
    (1, 'initial schema: geo_entities + census_acs5'),
    (2, 'aggregate tables: national summary, state summary, rankings, yoy'),
    (3, 'cdc_places: CDC PLACES county health outcomes'),
    (4, 'bls_laus: BLS Local Area Unemployment Statistics'),
    (5, 'usda_food_env: USDA Food Environment Atlas'),
    (6, 'county_profile: cross-source view joining all county data'),
    (7, 'epa_aqi: EPA Air Quality Index county data'),
    (8, 'fbi_crime: FBI Crime Data county violent and property crime rates'),
    (9, 'datasets: source catalog with quality stats'),
    (10, 'census_acs5: health insurance, commute time, race/ethnicity columns')
ON CONFLICT DO NOTHING;

COMMIT;
