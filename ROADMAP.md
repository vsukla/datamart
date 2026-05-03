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

Added 6 new county/state datasets, range filters, automation, and bug fixes.

### 2a — Environment & Safety

| Item | Status | Notes |
|---|---|---|
| EPA Air Quality Index — `/api/aqi/` | ✅ | ZIP+CSV per year; 11 AQI metrics; FIPS matched by normalized county name |
| FBI Crime Data — `/api/crime/` | ✅ | ZIP+CSV per year; agency rows aggregated to county; violent + property rates |
| NHTSA Traffic Fatalities — `/api/traffic/` | ✅ | FARS dataset; fatalities + rate per 100k pop; migration 013 |

### 2b — Housing & Economy

| Item | Status | Notes |
|---|---|---|
| HUD Fair Market Rents — `/api/housing/` | ✅ | Annual FMR by bedroom count (0–4BR) per county; migration 011 |
| EIA Energy Consumption — `/api/energy/` | ✅ | State-level; electricity + gas BBTU by sector; migration 012 |

### 2c — Health (deeper)

| Item | Status | Notes |
|---|---|---|
| CMS Medicare utilization — `/api/medicare/` | ⬜ | Spending per beneficiary, chronic conditions |
| HRSA Health Shortage Areas — `/api/hrsa/` | ⬜ | Primary care, dental, mental health deserts |

### 2d — Education

| Item | Status | Notes |
|---|---|---|
| Dept of Education graduation rates — `/api/education/` | ✅ | EDFacts 4-year ACGR; LEAID→county_fips via Urban Institute crosswalk; migration 014 |

### 2e — Bug Fixes, Filters & Tests

| Item | Status | Notes |
|---|---|---|
| Fix `fast_food_per_1000` — was using full-service restaurant column | ✅ | Issue #24; corrected to `FFRPTH16` |
| BLS LAUS: switch to BLS Public Data API (flat files blocked by Akamai) | ✅ | Issue #23 closed; BLS_API_KEY required; 16,103 rows loaded |
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

**365 tests** (up from 177 at Phase 1 close).

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

## Immediate — Pending Issues & Bugs

Pick up here next session.

### #26 — FBI Crime: needs redesign before next run

| Field | Value |
|---|---|
| File | `ingestion/ingest_fbi_crime.py` |
| API key | ✅ `FBI_API_KEY` added to `config/.env` |
| State endpoint confirmed useless | Returns ONLY 2 entries per state (offenses + clearances) — no per-agency breakdown |
| **Design needed** | Per-ORI calls: ~18k agencies × 2 types × 5 years = ~180k calls; impractical at 1000/hr. Options: (a) NIBRS bulk extract, (b) NIBRS-participating agencies only (~50% coverage), (c) wait for better API |
| Next step | When FBI CDE API is back up: count agencies across all 51 states; pick approach |
| Current DB | 0 rows |

### #27 — `mean_commute_minutes` NULL for ~9,000 Census rows

| Field | Value |
|---|---|
| Cause | B08136 (aggregate travel time) is suppressed by Census for small/rural counties |
| Impact | ~56% of rows (mostly small counties) have `mean_commute_minutes = NULL` |
| Decision needed | Accept NULLs as expected, or find an alternative (B08135 per-mode or ACS5 subject table S0801) |

### #28 — Load data for Phase 2 sources

| Source | Command | DB status |
|---|---|---|
| HUD Fair Market Rents | `python ingestion/ingest_hud_fmr.py --start 2018 --end 2022` | 0 rows |
| EIA Energy Consumption | `python ingestion/ingest_eia_energy.py --start 2018 --end 2022` | 0 rows |
| NHTSA Traffic Fatalities | `python ingestion/ingest_nhtsa_traffic.py --start 2018 --end 2022` | 0 rows |
| Education Graduation Rates | `python ingestion/ingest_ed_graduation.py --start 2018 --end 2022` | 0 rows |

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
| #23 | BLS LAUS: switch to flat-file download | 2e | ✅ Closed — flat files blocked; switched to BLS API |
| #24 | Fix `fast_food_per_1000` column | 2e | ✅ Closed |
| #25 | Tests for cross-source dashboard features | 2e | ✅ Closed |
| #26 | FBI Crime: redesign ingestion around per-ORI API calls | immediate | ⬜ Open |
| #27 | Census `mean_commute_minutes` NULL for small counties — accept or fix | data quality | ⬜ Open |
| #28 | Load data for Phase 2 sources (HUD, EIA, NHTSA, Education) | immediate | ⬜ Open |

---

## Phase 3.6 — MCP Server & AI Interface 🔜

Make the datamart queryable by any MCP-aware AI agent. Positions the project
as a *complement* to Google Data Commons and federal agency MCP servers, not a competitor.

| Item | Status | Notes |
|---|---|---|
| `datamart-mcp` server — county profile as MCP tools | 🔜 | Expose `/api/profile/`, `/api/estimates/`, `/api/aggregates/` as MCP tool calls |
| Submit to public MCP registry | 🔜 | mcp.so or equivalent; drives organic discovery |
| Comparison benchmark post | 🔜 | "What can Claude answer about a US county with vs. without datamart-mcp?" |
| LLM evaluation harness | ⬜ | 100 datasets × 500 natural-language queries; Claude vs. Gemini vs. GPT-4 with/without MCP grounding |
| Natural language query endpoint | ⬜ | `/api/ask/?q=` — structured Claude-backed query over county data |

**Why now:** The MCP ecosystem grew from 1,200 to 9,400+ servers between Q1 2025 and April 2026.
Federal agencies (Census Bureau, CMS, Treasury, GPO) are shipping their own MCP servers.
A `datamart-mcp` that wraps our normalized, governance-tracked multi-source profile
is a differentiated complement to single-source agency servers — not a replacement.

---

## Phase 3.7 — Civic Data Preservation 🔜

Federal statistical agencies have experienced significant workforce disruption in 2025–2026,
with documented slowdowns in data publication cadence and quality. Our provenance
architecture — file hashes, schema snapshots, immutable ingestion runs — is exactly
the right infrastructure for a trusted, versioned archive of federal datasets.

| Item | Status | Notes |
|---|---|---|
| Versioned dataset archive (hash-verified snapshots) | 🔜 | Already built in `ingestion_runs`; surface as public archive |
| Public dataset freshness dashboard | 🔜 | Show last-known-good version, hash, and download timestamp per source |
| "Data availability monitor" — alert on publication delays | ⬜ | Compare expected vs. actual release dates; alert on slippage |
| Foundation grant application (Knight / Sloan / MacArthur) | ⬜ | Civic archive framing; open-source infrastructure for journalists + researchers |
| data.gov catalog scrape — Phase A | 🔜 | Paginate CKAN API → score 500k datasets → publish top-200 list as blog post |

---

## 90-Day Action Plan

Concrete week-level targets based on strategic assessment.

| Weeks | Action | Deliverable |
|---|---|---|
| 1–2 | data.gov CKAN catalog scrape + scoring function | Blog post: top-200 scored federal datasets |
| 3–4 | `datamart-mcp` server + MCP registry submission | Comparison post: Claude with vs. without datamart-mcp |
| 5–8 | County Statistical Profile UI (Phase 3.5) | Working fingerprint + radar + peers at `/county-profile/` |
| 9–12 | Customer discovery sprint | 30 cold contacts in one vertical (CHNA or civic archive); 5 conversations |

**Decision gate at month 9:** Does any one of these hold?
- A paying customer or pre-commitment
- Three identified prospects in a single vertical with the same specific pain
- A public artifact (MCP server, benchmark, archive) that materially increased professional optionality

If yes to any → continue and narrow. If no to all → declare learning victory, archive the repo cleanly.

---

## Guiding principles for sequencing

1. **Depth before breadth** — fully cover county geography before adding new entity types.
2. **Pattern before platform** — repeat the ingestion pattern manually until it's painful, then abstract.
3. **Data before features** — more datasets in the profile is more valuable than more API capabilities until the profile is comprehensive.
4. **Tests always** — every new dataset ships with ingestion unit tests and API integration tests.
5. **Complement, don't compete** — position as a governance-tracked, multi-source layer on top of federal MCP servers and Google Data Commons, not a replacement for either.
6. **Ship publicly** — blog posts, MCP registry submissions, and benchmark artifacts compound as reputation and optionality; private code does not.
