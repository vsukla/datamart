-- Migration 002: pre-computed aggregate tables
-- Populated daily by ingestion/compute_aggregates.py

BEGIN;

-- Population-weighted national averages per year (from state-level data)
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

-- Population-weighted county rollups per state per year
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

-- Rank + percentile per geography x year x metric within peer group
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

-- Year-over-year absolute and % change per geography x metric
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

INSERT INTO schema_migrations (version, description)
VALUES (2, 'aggregate tables: national summary, state summary, rankings, yoy')
ON CONFLICT DO NOTHING;

COMMIT;
