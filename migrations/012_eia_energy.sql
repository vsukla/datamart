-- Migration 012: EIA State Energy Data System — electricity and natural gas
-- Populated by ingestion/ingest_eia_energy.py
-- State-level only (not county); not included in county_profile view.

BEGIN;

CREATE TABLE IF NOT EXISTS eia_energy (
    id              SERIAL     PRIMARY KEY,
    state_fips      CHAR(2)    NOT NULL REFERENCES geo_entities(fips),
    year            SMALLINT   NOT NULL,
    elec_res_bbtu   INTEGER,
    elec_com_bbtu   INTEGER,
    elec_ind_bbtu   INTEGER,
    elec_total_bbtu INTEGER,
    gas_res_bbtu    INTEGER,
    gas_com_bbtu    INTEGER,
    gas_ind_bbtu    INTEGER,
    gas_total_bbtu  INTEGER,
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (state_fips, year)
);

CREATE INDEX IF NOT EXISTS idx_eia_energy_state_fips ON eia_energy (state_fips);
CREATE INDEX IF NOT EXISTS idx_eia_energy_year       ON eia_energy (year);

INSERT INTO datasets (source_key, name, description, source_url, entity_type, update_cadence)
VALUES (
    'eia_energy',
    'EIA State Energy Data System',
    'Annual electricity and natural gas consumption by sector (residential, commercial, industrial) per state, in Billion Btu.',
    'https://api.eia.gov/v2/seds/data/',
    'state',
    'annual'
) ON CONFLICT (source_key) DO NOTHING;

INSERT INTO schema_migrations (version, description)
VALUES (12, 'eia_energy: EIA electricity and natural gas consumption by state')
ON CONFLICT DO NOTHING;

COMMIT;
