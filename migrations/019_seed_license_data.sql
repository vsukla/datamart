-- Migration 019: seed license metadata for all existing federal datasets
-- All current sources are US government works (17 USC 105), effectively public domain.
-- CC0-1.0 is used as the closest SPDX identifier; commercial_ok=true for all.

BEGIN;

UPDATE datasets SET
    license_spdx        = 'CC0-1.0',
    commercial_ok       = true,
    attribution_required = false,
    sensitivity_tier    = 1
WHERE source_key IN (
    'census_acs5',
    'cdc_places',
    'bls_laus',
    'usda_food_env',
    'epa_aqi',
    'fbi_crime',
    'nhtsa_traffic',
    'hud_fmr',
    'eia_energy',
    'ed_graduation'
);

INSERT INTO schema_migrations (version, description)
VALUES (19, 'governance: seed license data for existing federal datasets')
ON CONFLICT DO NOTHING;

COMMIT;
