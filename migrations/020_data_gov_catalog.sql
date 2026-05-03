-- Migration 020: data_gov_catalog — metadata store for data.gov CKAN scrape
-- Populated by ingestion/scrape_data_gov.py. One row per CKAN dataset record.
-- Scored 0-100; top-N are candidates for ingestion.

BEGIN;

CREATE TABLE IF NOT EXISTS data_gov_catalog (
    id                   SERIAL        PRIMARY KEY,
    ckan_id              VARCHAR(100)  NOT NULL UNIQUE,
    name                 VARCHAR(300),          -- CKAN slug
    title                TEXT,
    org_name             VARCHAR(150),          -- organization.name
    publisher            TEXT,                  -- extras.publisher (human-readable)
    formats              TEXT[],                -- resources[].format (deduplicated)
    group_names          TEXT[],                -- groups[].name
    tag_names            TEXT[],                -- tags[].name
    access_level         VARCHAR(30),           -- extras.accessLevel
    periodicity          VARCHAR(50),           -- extras.accrualPeriodicity (ISO 8601)
    modified_date        DATE,                  -- extras.modified
    has_spatial          BOOLEAN DEFAULT FALSE, -- extras.spatial is present
    num_resources        INTEGER,
    score                SMALLINT,              -- 0-100 after scoring pass
    metadata_modified    TIMESTAMPTZ,
    scraped_at           TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_gov_catalog_score    ON data_gov_catalog (score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_data_gov_catalog_org      ON data_gov_catalog (org_name);
CREATE INDEX IF NOT EXISTS idx_data_gov_catalog_modified ON data_gov_catalog (modified_date DESC NULLS LAST);

INSERT INTO schema_migrations (version, description)
VALUES (20, 'data_gov_catalog: metadata store for data.gov CKAN scrape')
ON CONFLICT DO NOTHING;

COMMIT;
