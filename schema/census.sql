CREATE TABLE IF NOT EXISTS census_acs5_states (
    id              SERIAL PRIMARY KEY,
    state_fips      CHAR(2)        NOT NULL,
    state_name      VARCHAR(100)   NOT NULL,
    year            SMALLINT       NOT NULL,
    population      INTEGER,
    median_income   INTEGER,
    pct_bachelors   NUMERIC(5, 2),
    fetched_at      TIMESTAMPTZ    DEFAULT NOW(),
    UNIQUE (state_fips, year)
);
