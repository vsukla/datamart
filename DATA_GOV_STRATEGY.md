# Data.gov Scale-Up Strategy

**Goal:** Ingest a meaningful subset of data.gov's 500k+ datasets, align them on common entities (primarily county FIPS), and expose them through a unified query API — over 6–10 months on a low-thousands budget.

**Status:** Living document. Assumptions will be wrong. Update it as we learn.

---

## Reality Check First

data.gov is a catalog, not a clean data warehouse. The 500k datasets include:
- PDFs and Word docs published as "data"
- City-level permits for one zip code
- Deprecated datasets that haven't been updated since 2014
- Dozens of agencies publishing the same underlying Census numbers with different column names

**Our target is not 500k datasets. It is probably 500–2,000 datasets that are:**
1. Machine-readable (CSV, JSON, Excel)
2. County- or state-level geographic coverage
3. Updated within the last 3 years
4. Published by a federal agency (not a local municipality)

Getting from 500k → 500 usable datasets is the first hard problem. Everything else follows.

---

## The Five Hard Problems

### 1. Discovery: Which 1% is worth ingesting?

data.gov has a CKAN API with rich metadata per dataset:
- `spatial` — geographic scope ("United States", "County", a bounding box)
- `accrualPeriodicity` — update cadence (annual, monthly, etc.)
- `resources[].format` — CSV, JSON, XLS, PDF, shapefile
- `groups` — 14 topic categories (Health, Education, Climate, etc.)
- `tags` — free-text keywords
- `temporal` — year range covered
- `organization` — publishing agency (CDC, Census, BLS, EPA, etc.)
- `resources[].size` — file size in bytes

A scoring function on these fields can get us from 500k → 5k candidates cheaply, without downloading a single file. Then human review narrows to 500. This is where to start.

**Blocker:** The `spatial` field is inconsistently filled — many county-level datasets don't say so. Tag analysis and agency inference will be necessary.

### 2. Schema Understanding: What's in each file?

Column names across 500k datasets are a tower of Babel:
- `FIPS`, `fips_code`, `GEO_ID`, `geoid`, `CountyFIPS`, `county_fips`, `STCOU` — all FIPS codes
- `MEDIAN_INCOME`, `med_hh_inc`, `B19013_001E`, `Median_HH_Income_2021` — all median income
- `PCT_POVERTY`, `poverty_rate`, `SAIPE_POV_ALL`, `pct_below_poverty` — all poverty rate

Human-readable column names + 3–5 sample rows are enough context for an LLM to classify: what entity does this row represent? what are the metric columns? what is the join key?

**This is the core bet:** Claude API + structured prompts can reliably classify ~80% of schemas. The other 20% get flagged for human review.

**Cost estimate:** 5,000 datasets × ~2,000 tokens/call = ~10M tokens. At Haiku 4.5 pricing (~$0.80/1M input tokens), this is ~$8 for classification passes. Even at Sonnet pricing it's under $50. Schema inference is cheap.

### 3. Entity Alignment: The Join Problem

Every dataset uses a different identifier for the same real-world entity.

**Geographic entities (our current focus):**

| Source identifier | Coverage | Crosswalk needed |
|---|---|---|
| FIPS code (5-digit) | Most federal datasets | Already have in `geo_entities` |
| State + county name text | Common in older datasets | Fuzzy name matcher → FIPS |
| ZIP code | USPS-based, not FIPS-aligned | ZIP→FIPS crosswalk (Census ZCTA) |
| Census GEOID (11-digit) | Census datasets | Truncate to 5-digit county |
| State abbreviation only | State-level data | Already have |
| MSA / CBSA codes | Metro area data | CBSA→FIPS crosswalk |

**Non-geographic entities (future):**

| Entity | Key | Crosswalk |
|---|---|---|
| Schools | NCES ID (LEAID / NCESSCH) | NCES → county FIPS |
| Hospitals | CMS Provider ID (NPI) | CMS → county FIPS |
| Congressional districts | GEOID | Census TIGER |
| Businesses | EIN / NAICS | No universal crosswalk |

**Key insight:** We already have FIPS as the spine. 80% of federal datasets with geographic data have a path to FIPS. Start there. Non-geographic joins are a Phase 5+ problem.

### 4. Ingestion at Scale: Volume and Automation

Each dataset that passes schema classification needs to be:
1. Downloaded (raw file → S3/local)
2. Parsed (CSV/Excel/JSON → normalized rows)
3. FIPS-aligned (entity key detected and mapped)
4. Column-mapped (source column names → canonical names)
5. Upserted into PostgreSQL (or rejected with a quality report)

The existing `BaseIngestion` pattern handles steps 1–2 and 5. Steps 3–4 need automation.

**Column mapping is the hardest step.** Two approaches:
- **Exact match + alias table:** Maintain a dictionary of known column name variants. Fast, brittle.
- **LLM-assisted mapping:** Given (source_column_name, sample_values) → canonical_column_name. Slower, more robust, needs validation.

In practice: exact match handles 60% of cases (federal datasets reuse column names a lot). LLM handles the rest. A validation step compares distributions against already-ingested data to catch mismatches.

### 5. Sync: Keeping Up With Updates

data.gov `metadata_modified` timestamps tell us when a dataset record changed. But they also fire when metadata-only changes happen (description edits, tag updates) — not just data changes.

Better approach: content hash of the downloaded file. If hash changes, re-ingest. If not, skip.

Some datasets update daily (BLS), some annually (Census), some never. The sync cadence should match the `accrualPeriodicity` field, with a weekly fallback for datasets that don't declare one.

---

## Phased Plan

### Phase A — Catalog Mining (Month 1–2)
*Understand the landscape before downloading anything*

**Work:**
- Paginate the data.gov CKAN API (`/api/3/action/package_search`) and store all ~500k dataset metadata records in a local `data_gov_catalog` table
- Build a scoring function (0–100) on metadata fields:
  - +30 if `resources[].format` includes CSV/JSON/XLS
  - +20 if `organization` is a known federal data agency (CDC, Census, BLS, EPA, HUD, USDA, DOT, DOE, DOJ, CMS, HRSA)
  - +20 if `tags` or `groups` suggest geographic/demographic data
  - +15 if `accrualPeriodicity` is populated (dataset is actively maintained)
  - +15 if `temporal` covers 2018 or later
  - −20 if all resources are PDF/shapefile/zip with no CSV fallback
- Score all 500k, sort descending, manually review top 200
- Calibrate the scoring function against the manual review
- Deliverable: a curated list of ~3,000–5,000 candidate datasets with confidence scores

**Cost:** Minimal. CKAN API is free. Storage for 500k metadata records ≈ 1–2 GB.

**What we'll learn:** How many federal county-level datasets actually exist. (Hypothesis: ~2,000–4,000.)

---

### Phase B — LLM Schema Classification (Month 2–3)
*Download samples, classify schemas, find the join key*

**Work:**
- For the top 3,000–5,000 scored datasets: download a sample (first 500 rows or 500KB, whichever comes first)
- Run each sample through a Claude API call with a structured prompt:
  ```
  Given these column headers and 5 sample rows from a federal dataset:
  [headers + rows]
  
  Answer:
  1. What geographic entity does each row represent? (county, state, ZIP, tract, nation, none)
  2. What column is the geographic join key? (column name or "none found")
  3. What type of join key is it? (FIPS, state_name, county_name, ZIP, GEOID, CBSA, other)
  4. What year(s) does this data represent? (or "unknown")
  5. List the metric columns and a one-sentence description of each
  6. Overall quality assessment: high / medium / low / unusable
  ```
- Store structured responses in a `dataset_schemas` table
- Deliverable: ~3,000–5,000 classified schemas; filter to ~500–1,000 county/state-level, high/medium quality

**Cost:** ~$50–200 in LLM API calls at Sonnet pricing. Well within budget.

**What we'll learn:** How many datasets have a reliable FIPS or FIPS-derivable key. (Hypothesis: ~40–60% of county-level datasets have a FIPS column; another 20–30% have state+county name.)

---

### Phase C — Entity Detection & FIPS Alignment (Month 3–4)
*Build the join infrastructure*

**Work:**
- For datasets where the join key is county name text (not raw FIPS): build a fuzzy name-to-FIPS matcher
  - Normalize: strip "County", "Parish", "Borough", "Census Area"; lowercase; strip punctuation
  - Match against `geo_entities.name` via trigram similarity (pg_trgm already in Postgres)
  - Confidence threshold: require ≥ 0.92 similarity; flag the rest for manual review
- Build crosswalk tables as needed:
  - ZIP → FIPS (Census ZCTA crosswalk — one-time download, ~40k rows)
  - CBSA → FIPS (OMB delineation files)
  - GEOID → FIPS (truncation, already works)
- Add a `fips_alignment` step to the ingestion pipeline: before upsert, map each row's join key to a FIPS
- Deliverable: FIPS alignment working for 80%+ of candidate datasets

---

### Phase D — Automated Ingestion (Month 4–6)
*Get data into the database*

**Work:**
- For the ~500 high-quality, FIPS-aligned datasets: build automated ingestion
- Pipeline per dataset:
  1. Download full file (S3 staging)
  2. Parse (CSV/Excel/JSON → DataFrame)
  3. FIPS-align rows (entity detection from Phase C)
  4. Column mapping:
     - Try exact match against a growing canonical alias table
     - LLM-assisted mapping for unmatched columns
     - Store mappings so they don't need to be re-inferred next sync
  5. Quality gate: require ≥ 60% FIPS match rate, ≥ 50% non-null on key columns
  6. Upsert to per-source tables or a generic `metric_values(fips, year, source_key, metric_name, value)` EAV table
  7. Register in `datasets` catalog, compute data quality stats
- Deliverable: 100–300 datasets loaded; API endpoints queryable

**Architecture decision (important):** Should each new dataset get its own table (current pattern), or should we use a generic EAV table? 

- **Per-table:** Clean schemas, fast queries, but doesn't scale to 500 tables without automation.
- **EAV table:** `(fips, year, source_key, metric_name, value NUMERIC)` — scales infinitely, queries are ugly, aggregation is slow.
- **Hybrid:** Per-domain wide tables (e.g., `county_metrics_health`, `county_metrics_economy`) with ~50 columns each, auto-extended by migration. Probably the right answer for this phase.

---

### Phase E — Discovery & Query Layer (Month 6–8)
*Make the data explorable without knowing the schema*

**Work:**
- `GET /api/query/` — client specifies `fips`, `metrics[]`, `year`; server builds the join across all source tables automatically
- Dataset search: `GET /api/datasets/search/?q=income&entity=county` — returns which datasets have income-related columns
- Metric catalog: `GET /api/metrics/` — flat list of all ~2,000 ingested metric columns with source, description, unit, vintage range
- Correlation discovery endpoint: given a metric, return the top-N other metrics with the highest Pearson r across counties (computed offline nightly)
- County profile v2: loads all available metrics for a county, not just the 18 hardcoded ones
- Deliverable: a developer can discover and query any dataset by metric name without knowing source table schemas

---

### Phase F — Sync & Maintenance (Month 8–10)
*Zero-touch freshness*

**Work:**
- Nightly sync job: check `metadata_modified` for all tracked datasets; re-download if changed
- Content hash check before re-processing (avoid redundant ingestion)
- Schema drift detection: re-run column classification if column count changes; alert on breaking changes
- Automated re-ingestion for schema-compatible updates; human review queue for schema changes
- `accrualPeriodicity`-aware scheduling: daily datasets run daily, annual datasets run monthly checks
- Deliverable: all 100–300 ingested datasets stay fresh automatically

---

## Budget Model

| Item | Est. Cost | Notes |
|---|---|---|
| CKAN API catalog scrape | $0 | Free API |
| S3 storage for raw files | $50–200/mo | ~500 datasets × avg 100MB = 50GB |
| LLM schema classification (Phase B) | $100–300 one-time | Sonnet at 5k datasets |
| LLM column mapping (ongoing) | $20–50/mo | Per new dataset ingestion |
| PostgreSQL RDS (db.t3.medium) | $60–100/mo | Scales to ~500GB |
| EC2 for ingestion workers (t3.small) | $15–30/mo | Spot instances for batch jobs |
| **Total over 10 months** | **~$1,500–3,500** | Well within thousands budget |

The bottleneck is engineering time, not cloud cost.

---

## Key Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Fewer county-level FIPS datasets than expected | Medium | Phase A tells us the real number before we commit |
| LLM schema classification < 80% accurate | Medium | Validation step compares distributions; human review queue for low-confidence |
| Column semantics are ambiguous (same name, different metric) | High | Require agency + vintage in the canonical name; never merge across agencies without a human sign-off |
| data.gov datasets have poor documentation | High | Use sample values + column names together, not just column names |
| A dataset's schema changes between vintages | Medium | Treat each vintage as a separate schema; detect diffs on re-download |
| Scale to 500 tables breaks the Django model layer | Medium | Move to generic EAV or wide domain tables before 100 datasets |
| data.gov API has rate limits or downtime | Low | Polite crawl (1 req/sec), cache all metadata locally |

---

## What To Do First (This Week)

1. **Scrape the CKAN catalog.** Run a paginated fetch of all dataset metadata and store it locally. This is one Python script (~100 lines). The output is a SQLite or PostgreSQL table with 500k rows. Fast and free — and it tells us what we're actually working with before we commit to any architecture.

2. **Build the scoring function.** Score all 500k on format, agency, tags, temporal coverage. Sort descending and look at the top 500 manually. This calibrates everything downstream.

3. **Pick 10 datasets manually.** From the top 500 scored, pick 10 that look genuinely valuable and county-level. Try to ingest them with the current pipeline. This surfaces the real friction — column mapping, FIPS alignment — before we automate anything.

The first two weeks are pure research. We should not write ingestion code until we know what we're ingesting.

---

## Open Questions (Revisit as We Learn)

- **Storage architecture:** Wide tables per domain vs EAV vs Parquet/DuckDB for analytics queries? Decide after seeing actual data volumes in Phase D.
- **Deduplication:** How many data.gov datasets are republications of the same underlying Census/CDC/BLS data we already have? Probably a lot — need a fingerprinting approach.
- **Non-county data:** What do we do with state-only, ZIP-only, or tract-level datasets? Exclude, or build parallel entity tables?
- **LLM column mapping validation:** How do we know a column mapping is wrong? Distribution comparison is the best automated signal but needs a baseline.
- **How many datasets is "enough"?** A county profile with 50 well-chosen metrics is more valuable than 500 noisy ones. Quality threshold matters more than count.

---

## Success Definition (10 Months)

A researcher can:
1. Go to `/api/metrics/` and see 500+ county-level metrics from 100+ datasets
2. Query any combination of those metrics for any county in a single API call
3. Trust that the data was ingested correctly (quality scores, provenance per row)
4. See the data automatically refresh when the source agency publishes new data

That's the bar. Everything in this document is in service of that.
