# Datamart — Product Requirements Document

## Vision

Make public data useful. Government agencies publish thousands of high-quality datasets, but they are fragmented across portals, inconsistently formatted, and nearly impossible to join. Datamart ingests these datasets, normalizes them around shared entities (geographies, institutions, organizations), and exposes them through a clean REST API and an interactive dashboard — so analysts, researchers, and developers can ask cross-source questions without writing one-off ETL scripts.

---

## Problem

Public data is abundant but inaccessible in practice:

- **Fragmented** — CDC health data, BLS labor data, USDA food data, EPA air quality data all live on separate portals with different schemas, update schedules, and access patterns.
- **Unjoinable** — datasets use different identifiers (FIPS codes, NCES IDs, CMS provider IDs, ZIP codes) making cross-source analysis hard.
- **Inconsistently formatted** — APIs return JSON, CSV, Excel, or XML with no common structure. Sentinel values, null representations, and column naming conventions vary by agency.
- **Ephemeral** — download links change, APIs are deprecated, and there is no persistent queryable copy.

The result: analysts who want to ask "how does county-level obesity correlate with food access and income?" spend most of their time on data wrangling, not analysis.

---

## Target Users

| User | Goal | How Datamart helps |
|---|---|---|
| **Policy researcher** | Compare health, economic, and environmental outcomes across counties | Single API with normalized, joinable county profiles |
| **Journalist / analyst** | Find counties where multiple negative indicators cluster | Cross-source ranking and filtering without ETL |
| **Developer** | Build an app or model on top of public data | Stable REST API with consistent schemas and pagination |
| **Data scientist** | Train models on multi-source features | Bulk export via API; consistent null handling |
| **Internal team** | Monitor data freshness and coverage | Dataset catalog with completeness and update metadata |

---

## Non-Goals

- **Real-time data** — Datamart targets datasets with daily-to-annual update cadences. Streaming or sub-hourly data is out of scope.
- **Private data** — All ingested data is public. Enterprise private-data integration is a future extension, not a core requirement.
- **Analysis layer** — Datamart provides normalized data; it does not run statistical models or generate insights automatically.
- **Full data warehouse replacement** — Datamart is optimized for public, entity-linked datasets. It is not a general-purpose OLAP platform.

---

## Core Principles

1. **Entity-first** — Every dataset attaches to a known entity (county, school, hospital). The entity is the join key across all sources.
2. **Idempotent ingestion** — Every script can be re-run without duplicating data. Upserts, not inserts.
3. **Schema stability** — API consumers should not break when new columns are added. Additive changes only.
4. **Transparent provenance** — Every row knows its source, vintage year, and when it was fetched.
5. **Iterative, not big-bang** — Each new dataset follows the same pattern: migration → ingestion script → API endpoint → tests. Ship frequently.

---

## Phases

### Phase 1 — Geographic Foundation (current)
*Entity: U.S. county and state (FIPS codes)*

Build the core architecture around U.S. geographic entities. Establish the ingestion pattern, API conventions, aggregate computation, and dashboard.

**Delivered:**
- `geo_entities` — 3,283 states and counties with FIPS codes
- Census ACS5 — income, education, housing, poverty, employment (2018–2022)
- CDC PLACES — county-level health outcomes (obesity, diabetes, smoking, hypertension, depression, physical activity, mental health); 2,956 counties for 2023 vintage
- BLS LAUS — county-level annual unemployment and labor force; 880 counties loaded (rate-limited; see issue #23)
- USDA Food Environment Atlas — food access, grocery density, restaurant density, SNAP, farmers markets; 3,153 counties for 2018 vintage
- Pre-computed aggregates: national summary, state rollups, rankings, year-over-year changes
- REST API: `/api/geo/`, `/api/estimates/`, `/api/aggregates/`, `/api/health/`, `/api/labor/`, `/api/food/`, `/api/profile/`
- Cross-source county profile view (`county_profile`) joining all sources at most-recent year per source
- Interactive dashboard:
  - All-states mode: national trend, state ranking, YoY for Census + health + food metrics
  - County drill-down: county ranking, YoY, CDC PLACES health panel, USDA food panel
  - Cross-source scatter chart — any metric vs any metric across all sources
  - County data table — all sources in one sortable table (11 columns)

**Known gaps:** BLS LAUS data is partial (880/3,231 counties) due to API rate limits — see issue #23. Column `fast_food_per_1000` actually contains full-service restaurant data — see issue #24.

**Success criteria:** A researcher can query all county-level indicators in a single API call and get a complete socioeconomic + health + food profile.

---

### Phase 2 — Geographic Expansion
*Entity: U.S. county and state (same FIPS foundation)*

Add more county/state-level datasets from data.gov and federal APIs — no architectural changes required. Deepen the county profile.

**Target datasets:**

| Dataset | Agency | Key metrics | Status |
|---|---|---|---|
| Air Quality Index | EPA AQS | County AQI, PM2.5, ozone days | 🔜 Next |
| Crime rates | FBI Crime Data Explorer | Violent/property crime per 100k | 🔜 Next |
| Traffic fatalities | NHTSA FARS | Fatalities per 100k, per 100M VMT | ⬜ Planned |
| Fair Market Rents | HUD | 1BR–4BR FMR by county | ⬜ Planned |
| Energy consumption | EIA | Electricity/gas by sector (state-level) | ⬜ Planned |
| Medicare utilization | CMS | Spending per beneficiary, chronic conditions | ⬜ Planned |
| Health Shortage Areas | HRSA | Primary care, dental, mental health deserts | ⬜ Planned |
| School performance | Dept of Education | Graduation rates, mapped to county | ⬜ Planned |

**Deliverables:**
- 6–8 new ingestion scripts following the existing pattern
- Corresponding migrations, models, serializers, views, URL endpoints
- `county_profile` view extended with new columns
- Dashboard: additional metric options in health/food panels; new EPA air quality panel

**Success criteria:** `county_profile` covers health, labor, food, environment, crime, housing, and education for every U.S. county.

---

### Phase 3 — Dataset Registry and Ingestion Platform
*Infrastructure to scale beyond manual one-off scripts*

As the number of datasets grows past ~10, manual management becomes a bottleneck. Build platform capabilities to make adding new datasets fast and self-service.

**Deliverables:**

- **Dataset catalog** — `datasets` table tracking name, source URL, entity type, update frequency, last ingested, row count, null rates per key column. Exposed at `/api/datasets/`.
- **Ingestion base class** — common Python module standardizing the fetch → validate → upsert → log lifecycle. New sources inherit from it and implement only `fetch()` and `normalize()`.
- **Scheduled ingestion** — GitHub Actions cron jobs running each script on its natural update cadence (daily for BLS, annual for Census, etc.).
- **Data quality dashboard** — A "catalog" page in the dashboard showing dataset freshness, completeness, and last update time.
- **Alerting** — Ingestion failures post to a GitHub issue or Slack webhook.

**Success criteria:** Adding a new dataset requires writing ~50 lines (fetch + normalize) and a SQL migration. Everything else (logging, scheduling, catalog registration, testing scaffold) is inherited.

---

### Phase 4 — New Entity Types
*Extend beyond county/state to schools, hospitals, ZIP codes, and more*

The FIPS-only model runs out of headroom when datasets key on non-geographic entities. This phase extends the entity model to support multiple entity types while preserving join-ability back to geography.

**New entity types:**

| Entity | Key | Source | Linkage |
|---|---|---|---|
| School | NCES ID | NCES Common Core of Data | → county FIPS |
| Hospital | CMS Provider ID | CMS Hospital Compare | → county FIPS |
| ZIP code | ZIP | USPS / Census ZCTA crosswalk | → county FIPS (via crosswalk) |
| Census tract | GEOID | Census TIGER | → county FIPS |
| Congressional district | GEOID | Census | → state FIPS |

**Deliverables:**
- Extended `geo_entities` or parallel `entities` table supporting typed entity records with optional `parent_fips`
- NCES school data: enrollment, Title I status, graduation rate, test scores — `/api/schools/`
- CMS hospital data: quality ratings, bed count, emergency services — `/api/hospitals/`
- ZIP-to-county crosswalk enabling ZIP-level data to roll up to county
- Cross-entity profile: given a county, return linked schools and hospitals

**Success criteria:** A developer can query all schools in a county alongside the county's Census and health data in two API calls.

---

### Phase 5 — Query Layer and Developer Experience
*Make Datamart a platform, not just a data store*

**Deliverables:**
- **Dynamic cross-source query API** — `/api/query/` accepting a list of fields from any source; server builds the join dynamically. Eliminates the need to pre-build every profile view.
- **Bulk export** — `/api/export/` returning CSV or Parquet for a filtered dataset; for data science workflows.
- **Token-based auth** — rate limiting for public access; private scopes for enterprise customers who want to upload proprietary data alongside public sources.
- **Field-level provenance** — every API response includes `_source` and `_vintage` metadata per field group.
- **Versioned API** — `/api/v2/` path so breaking changes can be introduced without disrupting existing consumers.
- **SDK / client library** — a lightweight Python client (`pip install datamart-client`) wrapping the REST API with pandas DataFrame output.

**Success criteria:** A data scientist can `pip install datamart-client` and get a DataFrame of 50 county-level features in 3 lines of Python.

---

## Success Metrics (platform-level)

| Metric | Phase 2 target | Phase 3 target | Phase 5 target |
|---|---|---|---|
| Datasets ingested | 12 | 20 | 50+ |
| Entity types supported | 1 (county/state) | 1 | 5+ |
| API endpoints | 12 | 20 | 10 (consolidated) |
| Test coverage | >95% | >95% | >95% |
| Ingestion failure rate | <5% | <1% | <1% |
| Time to add new dataset | ~1 day | ~2 hours | ~30 min |
