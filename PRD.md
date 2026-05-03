# Datamart — Product Requirements Document

## Vision

Make public data useful. Government agencies publish thousands of high-quality datasets, but they are fragmented across portals, inconsistently formatted, and nearly impossible to join. Datamart ingests these datasets, normalizes them around shared entities (geographies, institutions, organizations), and exposes them through a clean REST API and an interactive dashboard — so analysts, researchers, and developers can ask cross-source questions without writing one-off ETL scripts.

**Strategic posture:** Datamart is a complement to Google Data Commons, the Census Bureau API, and the emerging wave of federal agency MCP servers — not a competitor to any of them. Where those platforms are single-source (one agency's data) or general-purpose knowledge graphs, Datamart is a governance-tracked, multi-source profile layer: normalized, licensed, attributed, and queryable by any MCP-aware AI agent. The goal is to be the curated, trusted data layer that AI agents reach for when they need county-level context that isn't available from any single federal source.

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

### Phase 1 — Geographic Foundation ✅
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

**Both issues closed:** BLS LAUS switched to BLS Public Data API (16,103 rows); `fast_food_per_1000` corrected to `FFRPTH16` column.

**Success criteria:** A researcher can query all county-level indicators in a single API call and get a complete socioeconomic + health + food profile.

---

### Phase 2 — Geographic Expansion ✅
*Entity: U.S. county and state (same FIPS foundation)*

Add more county/state-level datasets from data.gov and federal APIs — no architectural changes required. Deepen the county profile.

**Delivered:**

| Dataset | Agency | Key metrics | Status |
|---|---|---|---|
| Air Quality Index | EPA AQS | County AQI, PM2.5, ozone days | ✅ |
| Crime rates | FBI Crime Data Explorer | Violent/property crime per 100k | ✅ (schema, 0 rows — see #26) |
| Traffic fatalities | NHTSA FARS | Fatalities per 100k, per 100M VMT | ✅ |
| Fair Market Rents | HUD | 1BR–4BR FMR by county | ✅ |
| Energy consumption | EIA | Electricity/gas by sector (state-level) | ✅ |
| School performance | Dept of Education | 4-year ACGR graduation rates | ✅ |

**Pending (schema exists, 0 rows loaded — see issue #28):** HUD, EIA, NHTSA, Education scripts need to be run.

**Success criteria met:** `county_profile` covers health, labor, food, environment, crime, housing, and education for every U.S. county.

---

### Phase 3 — Dataset Registry and Ingestion Platform ✅
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

### Phase 3.6 — MCP Server & AI Interface 🔜
*Make Datamart queryable by any MCP-aware AI agent*

The Model Context Protocol is the dominant AI agent integration layer in 2026. Federal agencies (Census Bureau, CMS, Treasury, GPO) are shipping their own MCP servers. A `datamart-mcp` server wrapping our normalized, governance-tracked, multi-source county profile is a differentiated complement — not a competitor — to single-agency MCP servers.

**Deliverables:**
- `datamart-mcp` server exposing `/api/profile/`, `/api/estimates/`, `/api/aggregates/` as MCP tool calls
- Published to mcp.so or equivalent public MCP registry
- Comparison benchmark post: "What can Claude answer about a US county with vs. without datamart-mcp?"
- LLM evaluation harness: 100 counties × 50 natural-language queries; Claude with/without MCP grounding

**Why now:** The MCP ecosystem grew from ~1,200 to 9,400+ servers between Q1 2025 and April 2026. The window to be one of the first curated public-data MCP servers is open now, not in 12 months.

**Success criteria:** An AI agent with `datamart-mcp` can answer "What are the top 10 counties by income growth with below-average unemployment?" without any SQL.

---

### Phase 3.7 — Civic Data Preservation 🔜
*Use our provenance architecture as a trusted archive of federal data*

Federal statistical agencies have experienced significant workforce disruption in 2025–2026, with documented slowdowns in data publication cadence. Our provenance architecture — file hashes, schema snapshots, immutable ingestion run logs — is purpose-built for trusted archival. This phase surfaces that capability publicly.

**Deliverables:**
- Public dataset freshness dashboard: last-known-good version, SHA-256 hash, and download timestamp per source
- Versioned dataset archive: every ingested file hash-verified and permanently retained
- "Data availability monitor" alerting on publication delays (expected vs. actual release dates)
- data.gov CKAN catalog scrape → score 500k datasets → publish top-200 ranked list as a blog post

**Commercial wedge — healthcare:** Community Health Needs Assessments (CHNAs) are a legal requirement for nonprofit hospitals every 3 years. They need exactly what we have: normalized, multi-source county profiles covering health outcomes, social determinants, demographics, and access. This is the most defensible paying customer segment: specific, recurring need, modest budget ($5k–$20k/year), and no adequate free alternative.

**Success criteria:** At least one external organization (journalist, researcher, or nonprofit) cites Datamart as their authoritative source for a federal dataset version.

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

### Phase 3.5 — County Statistical Profile

*A single-county deep-dive view exposing the full multi-source attribute fingerprint*

**Problem:** The current dashboard supports one comparison at a time — you pick a metric, then compare counties on that metric. A researcher studying Mecklenburg County must switch metrics 18 times to understand its full profile. There is no view that answers: "Across everything we know about this county, where does it stand — and which of its attributes are anomalies?"

**Solution:** A dedicated County Statistical Profile page that loads all attributes for one county simultaneously and presents them as a coherent statistical portrait.

**Core interactions:**
1. Select state → county → year → Load
2. See domain scores (economy, education, health, housing, environment, safety, food) as percentile cards
3. Radar chart comparing domain-level scores to the national median
4. **Attribute Fingerprint** — every metric as a horizontal percentile bar, grouped by domain, color-coded green (strong) to red (weak), with national median line
5. **Statistical Outliers** — top-N strengths and weaknesses (metrics furthest from median)
6. **Statistical Peers** — counties with the most similar attribute profile, ranked by Euclidean distance on normalized metrics
7. **Cross-attribute correlations** — how metrics co-move within a peer group (e.g., income × education r = 0.82)

**Key design decisions:**
- **Percentile direction normalization:** For metrics where lower = better (poverty, obesity, crime rate), the displayed percentile always means "better than X% of counties." This lets the fingerprint be read uniformly: a long bar is always good.
- **Peer group for correlations:** Computed within a peer cohort (same urban/rural classification or population tier) so correlations are meaningful, not dominated by the rural/urban split.
- **No new backend required at launch:** All data is already in `county_profile` view + individual source tables. Percentiles can be pre-computed via `agg_rankings` (already exists). Correlations are static, pre-computed from the full dataset.

**New backend work needed:**
- `GET /api/profile/<fips>/` — single-county full profile (exists already as `/api/profile/?fips=`)
- `GET /api/stats/percentiles/` — percentile ranks for all metrics for a given fips × year (can derive from `agg_rankings`)
- `GET /api/stats/peers/<fips>/` — top-N nearest neighbors by normalized Euclidean distance (new)
- `GET /api/stats/correlations/` — pre-computed Pearson r matrix for a given peer group (new, computed offline)
- New Django view at `/county-profile/`

**Success criteria:** A researcher can type a county name, see its complete statistical portrait in under 3 seconds, identify its top 3 strengths and weaknesses, and find 5 similar counties — without writing any SQL.

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

## Strategic Decision Gate (Month 9)

At the 9-month mark, evaluate whether any one of these holds:

1. A paying customer or pre-commitment (even $1k/year for a CHNA report)
2. Three identified prospects in a single vertical (e.g., three nonprofit hospital systems) with the same specific pain
3. A public artifact (MCP server, benchmark, archive page) that materially increased professional optionality (inbound inquiries, speaking invitations, GitHub stars > 500, press mention)

**If yes to any:** continue and narrow. Double down on the vertical or artifact that showed traction.

**If no to all:** declare learning victory. Archive the repo cleanly, write up the findings, and redirect time to other projects. The skills and code built have standalone value regardless of the commercial outcome.

This is not a failure condition — it is a real-options framework. The cost of finding out is low. The cost of continuing without signal is high.

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
