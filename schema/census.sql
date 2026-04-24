-- Geography reference table — one row per state or county
-- fips is 2 chars for states, 5 chars for counties (state_fips || county_code)
CREATE TABLE IF NOT EXISTS geo_entities (
    fips        VARCHAR(5)   PRIMARY KEY,
    geo_type    VARCHAR(10)  NOT NULL CHECK (geo_type IN ('state', 'county')),
    name        VARCHAR(200) NOT NULL,
    state_fips  CHAR(2)      NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_geo_entities_geo_type   ON geo_entities (geo_type);
CREATE INDEX IF NOT EXISTS idx_geo_entities_state_fips ON geo_entities (state_fips);

-- ACS 5-year estimates — one row per geography × year
-- Variables: population, income, education, housing, poverty, employment
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
    unemployment_rate   NUMERIC(5, 2),
    fetched_at          TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (fips, year)
);

CREATE INDEX IF NOT EXISTS idx_census_acs5_fips ON census_acs5 (fips);
CREATE INDEX IF NOT EXISTS idx_census_acs5_year ON census_acs5 (year);
