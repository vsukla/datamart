# Datamart — Roadmap

Status legend: ✅ Done · 🔄 In progress · 🔜 Next · ⬜ Planned · 🔭 Future

---

## Phase 1 — Geographic Foundation ✅

Core architecture, Census data, first external sources, dashboard.

| Item | Status |
|---|---|
| `geo_entities` table (3,283 states + counties) | ✅ |
| Census ACS5 ingestion (2018–2022) | ✅ |
| Aggregate batch job (national, state rollups, rankings, YoY) | ✅ |
| REST API: `/api/geo/`, `/api/estimates/`, `/api/aggregates/*` | ✅ |
| CDC PLACES health outcomes + `/api/health/` | ✅ |
| BLS LAUS unemployment + `/api/labor/` | ✅ |
| USDA Food Environment Atlas + `/api/food/` | ✅ |
| `county_profile` cross-source view + `/api/profile/` | ✅ |
| Dashboard — Census national trend, state/county ranking, YoY | ✅ |
| Dashboard — county drill-down (Census + health + food panels) | ✅ |
| Dashboard — health/food metrics in state-level ranking dropdown | ✅ |
| Dashboard — cross-source scatter chart (any metric × any metric) | ✅ |
| Dashboard — county data table (all sources, sortable) | ✅ |
| `schema/schema.sql` canonical DDL + migration runner | ✅ |
| 177 tests | ✅ |

---

## Phase 2 — Geographic Expansion ✅

Added 2 new county/state datasets, range filters, automation, and bug fixes.

### 2a — Environment & Safety

| Item | Status | Notes |
|---|---|---|
| EPA Air Quality Index — `/api/aqi/` | ✅ | ZIP+CSV per year; 11 AQI metrics; FIPS matched by normalized county name |
| FBI Crime Data — `/api/crime/` | ✅ | ZIP+CSV per year; agency rows aggregated to county; violent + property rates |
| NHTSA Traffic Fatalities — `/api/traffic/` | ⬜ | FARS dataset; fatalities per 100k pop |

### 2b — Housing & Economy

| Item | Status | Notes |
|---|---|---|
| HUD Fair Market Rents — `/api/housing/` | ⬜ | Annual FMR by bedroom count per county |
| EIA Energy Consumption — `/api/energy/` | ⬜ | State-level; electricity + gas by sector |

### 2c — Health (deeper)

| Item | Status | Notes |
|---|---|---|
| CMS Medicare utilization — `/api/medicare/` | ⬜ | Spending per beneficiary, chronic conditions |
| HRSA Health Shortage Areas — `/api/hrsa/` | ⬜ | Primary care, dental, mental health deserts |

### 2d — Education

| Item | Status | Notes |
|---|---|---|
| Dept of Education graduation rates — `/api/education/` | ⬜ | State-level; district-to-county crosswalk |

### 2e — Bug Fixes, Filters & Tests

| Item | Status | Notes |
|---|---|---|
| Fix `fast_food_per_1000` — was using full-service restaurant column | ✅ | Issue #24; corrected to `FFRPTH16` |
| BLS LAUS: switch to flat-file download (no rate limit) | ✅ | Issue #23; now ~3,100 counties per year, no API key |
| Range filters on `/api/estimates/` (e.g. `pct_poverty__gte=20`) | ✅ | Issue #14; 12 supported metrics |
| Tests for cross-source dashboard features | ✅ | Issue #25; scatter, county table, health/food ranking |
| EPA air quality + FBI crime fields in county profile | ✅ | Both sources in `county_profile` view + `/api/profile/` |
| Scheduled nightly `compute_aggregates.py` via GitHub Actions | ✅ | Issue #18; see Phase 3 |

---

## Phase 3 — Ingestion Platform ✅

Infrastructure to make adding new datasets fast and reliable.

| Item | Status | Notes |
|---|---|---|
| `datasets` catalog table + `/api/datasets/` endpoint | ✅ | Name, source URL, entity type, update cadence; seeded with 6 sources |
| Data quality tracking (null rates, row counts per dataset) | ✅ | `compute_data_quality.py`; stored in `datasets.null_rates` + `row_count` |
| Common ingestion base class (`ingestion/base.py`) | ✅ | `BaseIngestion`: fetch → parse → upsert → mark_ingested; CLI built-in |
| Dataset catalog panel in dashboard | ✅ | Row count, freshness badge, completeness progress bar per source |
| GitHub Actions CI + nightly cron | ✅ | `ci.yml` (tests on push/PR); `nightly_aggregates.yml` (daily 06:00 UTC) |
| Additional Census variables (health insurance, commute, race) | ✅ | Issue #15; migration 010; 6 new columns in `census_acs5` |
| Ingestion failure alerting (GitHub issue or webhook) | ⬜ | |

**291 tests** (up from 177 at Phase 1 close).

---

## Phase 4 — New Entity Types ⬜

Extend beyond county/state. Each new entity type links back to FIPS.

| Item | Status | Notes |
|---|---|---|
| ZIP-to-county crosswalk (Census ZCTA) | ⬜ | Enables ZIP-level data to roll up to county |
| Census tract support | ⬜ | Finer geographic granularity |
| Schools entity (NCES IDs) + `/api/schools/` | ⬜ | Enrollment, Title I, graduation, test scores |
| Hospitals entity (CMS Provider IDs) + `/api/hospitals/` | ⬜ | Quality ratings, capacity, services |
| Congressional district entity | ⬜ | Political geography crosswalk |
| Extended entity table design | ⬜ | Generic `entities(entity_type, entity_id, parent_fips)` |

---

## Phase 5 — Query Layer & Developer Experience 🔭

| Item | Status | Notes |
|---|---|---|
| Dynamic cross-source query API `/api/query/` | 🔭 | Client specifies fields; server builds join |
| Bulk export `/api/export/` (CSV / Parquet) | 🔭 | For data science workflows |
| Token-based auth + rate limiting | 🔭 | Issue #17 |
| Field-level provenance in API responses | 🔭 | `_source`, `_vintage` per field group |
| Versioned API (`/api/v2/`) | 🔭 | Breaking-change path |
| Python client library (`pip install datamart-client`) | 🔭 | Pandas DataFrame output |
| World Bank country-level data | 🔭 | Issue #16; requires country entity type |

---

## Backlog (unscheduled)

Issues tracked in GitHub: https://github.com/vsukla/datamart/issues

| # | Title | Phase | Status |
|---|---|---|---|
| #14 | Range filters on `/api/estimates/` | 2e | ✅ Closed |
| #15 | Additional Census variables | 3 | ✅ Closed |
| #16 | World Bank data source | 5 | ⬜ Open |
| #17 | Token-based auth + rate limiting | 5 | ⬜ Open |
| #18 | Schedule compute_aggregates.py via GitHub Actions | 3 | ✅ Closed |
| #22 | Cross-source dynamic query API `/api/query/` | 5 | ⬜ Open |
| #23 | BLS LAUS: switch to flat-file download | 2e | ✅ Closed |
| #24 | Fix `fast_food_per_1000` column | data quality | ✅ Closed |
| #25 | Tests for cross-source dashboard features | 2e | ✅ Closed |

---

## Guiding principles for sequencing

1. **Depth before breadth** — fully cover county geography before adding new entity types.
2. **Pattern before platform** — repeat the ingestion pattern manually until it's painful, then abstract.
3. **Data before features** — more datasets in the profile is more valuable than more API capabilities until the profile is comprehensive.
4. **Tests always** — every new dataset ships with ingestion unit tests and API integration tests.
