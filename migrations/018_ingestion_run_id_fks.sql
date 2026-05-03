-- Migration 018: add ingestion_run_id FK to all source tables
-- Nullable — existing rows have no run record. New rows set it on upsert.
-- Enables: "show me every row loaded in run #42" and chain-of-custody queries.

BEGIN;

ALTER TABLE census_acs5   ADD COLUMN IF NOT EXISTS ingestion_run_id INTEGER REFERENCES ingestion_runs(id);
ALTER TABLE cdc_places    ADD COLUMN IF NOT EXISTS ingestion_run_id INTEGER REFERENCES ingestion_runs(id);
ALTER TABLE bls_laus      ADD COLUMN IF NOT EXISTS ingestion_run_id INTEGER REFERENCES ingestion_runs(id);
ALTER TABLE usda_food_env ADD COLUMN IF NOT EXISTS ingestion_run_id INTEGER REFERENCES ingestion_runs(id);
ALTER TABLE epa_aqi       ADD COLUMN IF NOT EXISTS ingestion_run_id INTEGER REFERENCES ingestion_runs(id);
ALTER TABLE fbi_crime     ADD COLUMN IF NOT EXISTS ingestion_run_id INTEGER REFERENCES ingestion_runs(id);
ALTER TABLE hud_fmr       ADD COLUMN IF NOT EXISTS ingestion_run_id INTEGER REFERENCES ingestion_runs(id);
ALTER TABLE eia_energy    ADD COLUMN IF NOT EXISTS ingestion_run_id INTEGER REFERENCES ingestion_runs(id);
ALTER TABLE nhtsa_traffic ADD COLUMN IF NOT EXISTS ingestion_run_id INTEGER REFERENCES ingestion_runs(id);
ALTER TABLE ed_graduation ADD COLUMN IF NOT EXISTS ingestion_run_id INTEGER REFERENCES ingestion_runs(id);

INSERT INTO schema_migrations (version, description)
VALUES (18, 'governance: ingestion_run_id FK on all source tables')
ON CONFLICT DO NOTHING;

COMMIT;
