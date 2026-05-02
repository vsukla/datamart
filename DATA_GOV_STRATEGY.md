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

## Priority Dataset Catalog

The datasets below are the highest-value targets — selected for geographic granularity
(county or state), federal authorship, machine-readable format, active maintenance,
and cross-domain join potential. Organized by domain; tiered by ingestion priority.

**Tier 1** — ingest as soon as the pipeline is automated (high value, manageable complexity)  
**Tier 2** — ingest in Phase D–E (high value, moderate complexity or large file size)  
**Tier 3** — useful for specific verticals; ingest on demand

---

### Economy & Labor

| Dataset | Agency | Level | Key Metrics | Format | Tier |
|---|---|---|---|---|---|
| **BEA Regional Economic Accounts** | Bureau of Economic Analysis | County + State | GDP by industry, personal income per capita, compensation | CSV/API | 1 |
| **BLS QCEW** — Quarterly Census of Employment & Wages | BLS | County | Employment + wages by NAICS industry sector, establishment count | CSV | 1 |
| **Census SAIPE** — Small Area Income & Poverty Estimates | Census Bureau | County | Annual poverty rate, median income — more current than ACS5 | CSV/API | 1 |
| **IRS Statistics of Income** | IRS | ZIP→County | AGI, number of returns, income brackets, EITC recipients | CSV | 2 |
| **SBA 7(a) and 504 Loan Data** | Small Business Administration | County | Loan count, dollar volume, industry, approval rate by county | CSV | 2 |
| **FDIC Bank Branch Statistics** | FDIC | County | Number of bank branches, total deposits, bank deserts | CSV | 2 |
| **USDA Rural-Urban Continuum Codes** | USDA ERS | County | Rural/urban classification (9-tier), metro adjacency | CSV | 1 |
| **Fed Reserve Small Business Credit Survey** | Federal Reserve | State | Credit access, approval rates, fintech use | CSV | 3 |

**BEA Regional:** `https://apps.bea.gov/regional/downloadzip.cfm` — county-level GDP and personal income going back to 2001. Probably the single most valuable dataset not yet ingested. GDP per capita alone makes county economic comparisons meaningful.

**BLS QCEW:** `https://www.bls.gov/cew/downloadable-data.htm` — quarterly employment and wages by county × industry (NAICS). Enables questions like "which counties are manufacturing-dependent?" or "where are tech jobs growing?" Flat files, large (~2GB/year), but well-structured.

---

### Health & Healthcare

| Dataset | Agency | Level | Key Metrics | Format | Tier |
|---|---|---|---|---|---|
| **CDC Wonder Mortality** | CDC | County | Deaths by cause (ICD-10), age-adjusted rates, years of life lost | API | 1 |
| **CMS Medicare Geographic Variation** | CMS | County | Medicare spending per beneficiary, chronic condition prevalence, utilization | CSV | 1 |
| **HRSA HPSA / MUA** — Shortage Areas | HRSA | County | Primary care, dental, mental health professional shortage designations | CSV/API | 1 |
| **AHRQ Social Determinants of Health Database** | AHRQ | County | Compiled SDOH measures from 6 domains, 40+ variables | CSV | 1 |
| **CDC Opioid Prescribing Rates** | CDC | County | Opioid prescriptions per 100 persons, high-dosage rates | CSV | 1 |
| **SAMHSA Treatment Locator / N-SSATS** | SAMHSA | County | Substance use treatment facilities, mental health facilities | CSV | 2 |
| **CDC National Environmental Public Health Tracking** | CDC | County | Environment-health linkages: asthma, blood lead, heart disease | API | 2 |
| **CMS Hospital Compare** | CMS | County | Hospital quality ratings, readmission rates, patient safety | CSV/API | 2 |
| **BRFSS** — Behavioral Risk Factor Surveillance | CDC | State | Smoking, exercise, seatbelt use, preventive care (some county estimates) | CSV | 3 |

**CDC Wonder Mortality:** The most powerful health dataset not yet ingested. Age-adjusted death rates by county for every ICD-10 cause of death (heart disease, cancer, diabetes, drug overdose, suicide, etc.) going back to 1999. Enables research questions like "which counties have the highest drug overdose mortality trend?" Requires API access but is free.

**CMS Medicare Geographic Variation:** `https://data.cms.gov/` — spending per beneficiary by county, broken down by service type. Heavily used by health equity researchers and hospital systems. Direct CSV download available.

---

### Housing & Real Estate

| Dataset | Agency | Level | Key Metrics | Format | Tier |
|---|---|---|---|---|---|
| **FHFA House Price Index** | FHFA | Metro/County | Quarterly home price index, appreciation rates, 1975–present | CSV | 1 |
| **HUD CHAS** — Comprehensive Housing Affordability Strategy | HUD | County/Tract | Cost-burdened households, affordability gaps by income tier | CSV | 1 |
| **HMDA** — Home Mortgage Disclosure Act | CFPB | County | Mortgage originations, denials, rates, race/income of applicants | CSV | 2 |
| **Census Building Permits Survey** | Census | County | New residential construction permits, units authorized, value | CSV | 1 |
| **HUD LIHTC Database** | HUD | County | Low-income housing tax credit projects, units, income targeting | CSV | 2 |
| **HUD Picture of Subsidized Households** | HUD | County | Public housing, voucher counts, income of assisted households | CSV | 2 |
| **Eviction Lab** (Princeton) | Princeton | County | Eviction filing rates, eviction rates, 2000–2018 | CSV | 2 |

**FHFA HPI:** Quarterly house price appreciation by metro area and county. One of the most-used indicators in real estate analysis. Direct CSV at `https://www.fhfa.gov/DataTools/Downloads`. Already aligns to county FIPS.

**Building Permits:** Monthly residential permit counts by county — the earliest leading indicator of housing supply and population growth. `https://www.census.gov/construction/bps/`. Small files, clean FIPS, easy ingestion.

---

### Education

| Dataset | Agency | Level | Key Metrics | Format | Tier |
|---|---|---|---|---|---|
| **NCES Common Core of Data** | Dept of Education | School → County | Enrollment, demographics, free/reduced lunch, Title I status | CSV | 1 |
| **College Scorecard** | Dept of Education | Institution → County | Completion rates, earnings after graduation, debt loads | CSV/API | 1 |
| **IPEDS** — Integrated Postsecondary Education Data | NCES | Institution → County | Enrollment, graduation, cost, financial aid by college | CSV | 2 |
| **Head Start Program Data** | HHS | County | Enrollment slots, grantees, funding per county | CSV | 2 |
| **NAEP State Profiles** | NCES | State | Reading/math scores, achievement gaps, trend data | CSV | 3 |
| **Child Care and Development Fund (CCDF)** | HHS | State/County | Childcare subsidies, licensed capacity, cost | CSV | 3 |

**NCES CCD:** School-level data aggregable to county via LEAID → county FIPS crosswalk (same mechanism as our ED graduation rate ingestion). Covers all ~130k public schools. Enables questions like "what fraction of kids in this county are in Title I schools?"

---

### Environment & Climate

| Dataset | Agency | Level | Key Metrics | Format | Tier |
|---|---|---|---|---|---|
| **EPA TRI** — Toxic Release Inventory | EPA | Facility → County | 800+ chemicals released, by type (air, water, land), by facility | CSV | 1 |
| **FEMA National Risk Index** | FEMA | County | Composite natural hazard risk score: hurricane, flood, tornado, wildfire, earthquake | CSV | 1 |
| **EPA Superfund / CERCLA Sites** | EPA | Site → County | NPL sites, cleanup status, contaminants | CSV | 2 |
| **NOAA Climate Normals** | NOAA | Station → County | 30-year temperature and precipitation averages, extreme events | CSV | 2 |
| **USGS Natural Hazards** | USGS | County | Earthquake risk, landslide susceptibility, subsidence | CSV | 2 |
| **USDA NASS Cropland Data Layer** | USDA | County | Crop acreage by type, land use | CSV | 2 |
| **CDC Environmental Health Tracking** | CDC | County | Asthma hospitalizations, blood lead levels, environmental triggers | API | 2 |
| **EPA EnviroFacts** | EPA | Facility → County | Air permits, water permits, hazardous waste by facility | API | 3 |

**EPA TRI:** `https://www.epa.gov/toxics-release-inventory-tri-program/tri-basic-data-files-calendar-years-1987-present` — annual CSV files. Facility-level releases of 800+ toxic chemicals, aggregable to county. Extremely powerful for environmental justice analysis, insurance underwriting, and real estate risk scoring.

**FEMA NRI:** Pre-computed natural hazard risk scores for every US county. Combines 18 hazard types into a single composite score. Direct CSV download. Immediately useful for insurance, real estate, and ESG scoring.

---

### Infrastructure & Connectivity

| Dataset | Agency | Level | Key Metrics | Format | Tier |
|---|---|---|---|---|---|
| **FCC Broadband Deployment** (Form 477) | FCC | County/ZIP | % households with broadband by speed tier, ISP count | CSV | 1 |
| **FCC National Broadband Map** | FCC | Census Block | Coverage by technology type and speed, most current | API | 2 |
| **USDA ReConnect Program** | USDA | County | Rural broadband grant recipients, coverage areas | CSV | 2 |
| **DOT Highway Performance Monitoring** | DOT/FHWA | County | Lane-miles, pavement condition, bridge ratings | CSV | 2 |
| **FAA Airport Traffic Statistics** | FAA | Airport → County | Passenger enplanements, operations, aircraft | CSV | 3 |
| **EIA Electric Reliability** | EIA | State/Utility | Outage frequency, duration (SAIDI/SAIFI) | CSV | 3 |

**FCC Broadband:** `https://www.fcc.gov/form477` — county-level broadband availability and subscription rates. Critical for economic development, healthcare (telehealth access), and education research. Direct CSV by county.

---

### Crime & Justice

| Dataset | Agency | Level | Key Metrics | Format | Tier |
|---|---|---|---|---|---|
| **BJS National Prisoner Statistics** | BJS | State | Incarceration rate, prison admissions, releases | CSV | 2 |
| **Vera Institute Incarceration Trends** | Vera (Princeton) | County | Jail and prison incarceration rates 1970–2018 | CSV | 1 |
| **FBI NIBRS** — National Incident-Based Reporting | FBI | Agency → County | Offense, victim, offender, arrest data at incident level | CSV | 2 |
| **OJJDP Juvenile Justice Stats** | DOJ | State/County | Juvenile arrest rates, detention, diversion by offense | CSV | 3 |

**Vera Incarceration Trends:** Clean, FIPS-aligned, county-level incarceration rates going back to 1970. `https://github.com/vera-institute/incarceration-trends`. Already on GitHub as clean CSV. One of the highest-impact justice datasets.

---

### Agriculture & Rural

| Dataset | Agency | Level | Key Metrics | Format | Tier |
|---|---|---|---|---|---|
| **USDA Census of Agriculture** | USDA NASS | County | Farm count, acreage, sales, operator demographics (every 5 years) | CSV | 1 |
| **USDA NASS Crop Production** | USDA NASS | County | Acreage planted/harvested, yield, value by crop type | CSV | 2 |
| **USDA Farm Service Agency Programs** | USDA FSA | County | Commodity support payments, crop insurance, conservation | CSV | 2 |
| **USDA ERS Food Access Research Atlas** | USDA ERS | County | Food desert metrics (already partially ingested via Food Env Atlas) | CSV | 1 |

**USDA Census of Agriculture:** County-level farm census conducted every 5 years (2017, 2022). 500+ variables: farm count, acreage, crop types, livestock, sales, operator age/race/gender, internet access, organic production. `https://www.nass.usda.gov/AgCensus/`. Enormous value for rural economic research and agricultural lending.

---

### Business & Entrepreneurship

| Dataset | Agency | Level | Key Metrics | Format | Tier |
|---|---|---|---|---|---|
| **Census County Business Patterns** | Census | County | Establishments by NAICS, employment, payroll — annual 1986–present | CSV | 1 |
| **Census Nonemployer Statistics** | Census | County | Self-employed / gig economy businesses by industry | CSV | 2 |
| **BLS Business Employment Dynamics** | BLS | State/Metro | Establishment births, deaths, expansions, contractions | CSV | 2 |
| **Census Annual Survey of Entrepreneurs** | Census | State | Business ownership by race, gender, veteran status | CSV | 3 |

**County Business Patterns:** `https://www.census.gov/programs-surveys/cbp.html` — arguably the most fundamental business dataset. Establishment counts and employment by 6-digit NAICS industry for every county, annually since 1986. Enables questions like "how many manufacturing establishments are in this county?" and "is the service sector growing or contracting?" Clean FIPS. Annual CSV.

---

### Civic & Political

| Dataset | Agency | Level | Key Metrics | Format | Tier |
|---|---|---|---|---|---|
| **MIT Election Lab** | MIT | County | Presidential, Senate, House election results 2000–2022, vote shares | CSV | 1 |
| **FEC Campaign Finance** | FEC | County/ZIP | Individual contribution amounts, PAC spending by geography | CSV | 2 |
| **Census Voting & Registration Supplement** | Census (CPS) | State | Voter registration rates, turnout by demographics | CSV | 3 |

**MIT Election Lab:** `https://electionlab.mit.edu/data` — county-level election results for federal races going back to 2000. Clean, FIPS-aligned CSV. Enables political economy research (voting patterns vs. economic indicators), campaign targeting, and journalism.

---

### International Equivalents

When expanding globally, these are the authoritative sources by region:

| Region | Source | Entity Level | Key Datasets | Notes |
|---|---|---|---|---|
| **Global** | World Bank Open Data | Country | 1,600+ indicators: GDP, poverty, health, education, infrastructure | Free API, 200+ countries |
| **Global** | IMF World Economic Outlook | Country | GDP growth, inflation, unemployment, debt | Annual/semi-annual |
| **Global** | UN SDG Indicators | Country | 200+ Sustainable Development Goal metrics | Inconsistent coverage |
| **Global** | WHO Global Health Observatory | Country | Mortality, disease burden, health system capacity | Free API |
| **EU** | Eurostat NUTS2/NUTS3 | Regional (≈ county) | Demographics, employment, GDP, health, education for all 27 EU member states | Free API, consistent schema |
| **EU** | OECD Regional Statistics | NUTS2 | GDP per capita, employment, productivity for OECD countries | Paid API or bulk download |
| **UK** | ONS Nomis | Local Authority | Population, employment, wages, claimant count — UK equivalent of US county level | Free API |
| **UK** | UK Data Service | Local Authority | Health, deprivation indices, housing, crime | Free with registration |
| **Canada** | Statistics Canada | Census Division / CMA | Demographics, income, employment, housing | Free API |
| **Australia** | ABS (Australian Bureau of Statistics) | SA2 / LGA | Census data, economic indicators, health | Free API |
| **India** | NITI Aayog / MOSPI | District | SDG index, poverty, health, education (district = ~county equivalent) | CSV downloads |
| **Brazil** | IBGE | Municipality | Demographics, income, health, sanitation (5,570 municipalities) | Free API |
| **Germany** | Destatis / Regionalatlas | Kreis (county) | Demographics, employment, income — 400 counties | Free API |

**The global opportunity in one sentence:** Eurostat alone covers 1,100+ NUTS3 regions across 27 EU countries with a consistent schema and free API — it's essentially one ingestion pipeline that quadruples our addressable market for every international customer.

---

### Dataset Priority Stack-Rank

If limited to ingesting 20 datasets next, this is the order:

| Priority | Dataset | Why |
|---|---|---|
| 1 | BEA Regional Economic Accounts | GDP per capita by county — fills the biggest gap in current profile |
| 2 | CDC Wonder Mortality | Cause-of-death rates by county — transforms health domain depth |
| 3 | FEMA National Risk Index | Pre-computed natural hazard risk — immediately useful for insurance vertical |
| 4 | Census County Business Patterns | Industry employment structure — enables economic diversification analysis |
| 5 | CMS Medicare Geographic Variation | Healthcare spending + chronic conditions — health vertical anchor |
| 6 | FHFA House Price Index | Quarterly appreciation — real estate vertical anchor |
| 7 | FCC Broadband Deployment | Digital access divide — broadband is the new infrastructure gap |
| 8 | EPA TRI Toxic Release Inventory | Industrial pollution by county — environment + justice research |
| 9 | HRSA HPSA Shortage Areas | Healthcare deserts — CHNA compliance + health vertical |
| 10 | MIT Election Lab | County election results — civic research + political economy |
| 11 | BLS QCEW Industry Employment | Sector-level employment — economic development vertical |
| 12 | Census SAIPE | Annual poverty estimates — more current than ACS5 |
| 13 | Vera Incarceration Trends | County jail/prison rates — justice research, already clean CSV |
| 14 | Census Building Permits | Monthly construction — housing supply signal |
| 15 | USDA Census of Agriculture | Farm census — rural economy + ag lending vertical |
| 16 | HUD CHAS | Affordable housing need — housing vertical anchor |
| 17 | NCES Common Core of Data | School-level → county education depth |
| 18 | EPA Superfund Sites | Contaminated sites — environmental risk scoring |
| 19 | World Bank Open Data | Global expansion anchor — 200 countries, 1,600 indicators |
| 20 | Eurostat NUTS3 | EU regional data — one pipeline, 1,100 regions |

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
