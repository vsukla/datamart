-- Migration 015: add governance metadata to datasets table
-- Every dataset must declare license, commercial use, and sensitivity tier.

BEGIN;

ALTER TABLE datasets ADD COLUMN license_spdx          VARCHAR(50)  NOT NULL DEFAULT 'unknown';
ALTER TABLE datasets ADD COLUMN commercial_ok          BOOLEAN      NOT NULL DEFAULT false;
ALTER TABLE datasets ADD COLUMN attribution_required   BOOLEAN      NOT NULL DEFAULT true;
ALTER TABLE datasets ADD COLUMN attribution_text       TEXT;
ALTER TABLE datasets ADD COLUMN sensitivity_tier       SMALLINT     NOT NULL DEFAULT 1
    CHECK (sensitivity_tier IN (1, 2, 3));
    -- 1 = public domain / open license (no restrictions)
    -- 2 = open with restrictions (attribution, share-alike)
    -- 3 = requires data use agreement before serving
ALTER TABLE datasets ADD COLUMN min_population_suppress INTEGER     DEFAULT NULL;
    -- NULL = no suppression. If set, suppress rows where geo population < this value.

INSERT INTO schema_migrations (version, description)
VALUES (15, 'governance: license and sensitivity columns on datasets')
ON CONFLICT DO NOTHING;

COMMIT;
