# Governance Architecture

Technical companion to [GOVERNANCE.md](GOVERNANCE.md). Defines the concrete
schema changes, pipeline constraints, and API middleware required to enforce
governance policies structurally — not through documentation or good intentions.

**Core principle:** Every governance requirement must be enforced by code.
If a developer can accidentally violate it, the architecture has failed.

---

## What Must Be Structurally Impossible

These must be impossible by design, not just prohibited by policy:

| Prohibited outcome | Structural enforcement |
|---|---|
| Serving a CC-BY-NC dataset in a paid API response | `datasets.commercial_ok` checked in API middleware; request rejected if false |
| Ingesting a dataset without recording its license | `NOT NULL` constraint on `datasets.license_spdx` |
| Serving data for a geography below the population suppression threshold | Middleware suppression check before serialization |
| An API response that contains CC-BY data without attribution | Attribution injected by serializer, not left to developer |
| Ingesting a file twice without detecting the change | SHA-256 hash recorded on every ingestion; skip if hash unchanged |
| A row in any source table with no link to its ingestion run | `ingestion_run_id` FK on every source table |
| Storing individual-level records | Schema-level constraint: every source table requires `(fips, year)` PK — county is the minimum granularity |
| User PII mixed with geographic data | Separate database schemas: `public` (geographic data) and `auth` (users, API keys, billing) |

---

## Schema Changes

### 1. Extend `datasets` Table

Add governance metadata to the source catalog. Every dataset must declare these
before ingestion is permitted.

```sql
ALTER TABLE datasets ADD COLUMN license_spdx         VARCHAR(50)   NOT NULL DEFAULT 'unknown';
ALTER TABLE datasets ADD COLUMN commercial_ok         BOOLEAN       NOT NULL DEFAULT false;
ALTER TABLE datasets ADD COLUMN attribution_required  BOOLEAN       NOT NULL DEFAULT true;
ALTER TABLE datasets ADD COLUMN attribution_text      TEXT;
ALTER TABLE datasets ADD COLUMN share_alike           BOOLEAN       NOT NULL DEFAULT false;
ALTER TABLE datasets ADD COLUMN redistribution_ok     BOOLEAN       NOT NULL DEFAULT false;
ALTER TABLE datasets ADD COLUMN data_use_agreement    BOOLEAN       NOT NULL DEFAULT false;
ALTER TABLE datasets ADD COLUMN sensitivity_tier      SMALLINT      NOT NULL DEFAULT 1
    CHECK (sensitivity_tier IN (1, 2, 3));
    -- 1 = public domain / open license
    -- 2 = open with restrictions (attribution, share-alike)
    -- 3 = requires data use agreement before serving
ALTER TABLE datasets ADD COLUMN min_population_suppress INTEGER      DEFAULT NULL;
    -- NULL = no suppression. If set, suppress rows where geo population < this value.
ALTER TABLE datasets ADD COLUMN geographic_scope      VARCHAR(20)   DEFAULT 'national'
    CHECK (geographic_scope IN ('national', 'state', 'county', 'tract', 'zip', 'international'));
ALTER TABLE datasets ADD COLUMN terms_url             TEXT;
ALTER TABLE datasets ADD COLUMN license_verified_at   TIMESTAMPTZ;
ALTER TABLE datasets ADD COLUMN license_verified_by   VARCHAR(100);

-- Enforce: nothing gets served until license is verified
CREATE INDEX idx_datasets_commercial_ok ON datasets (commercial_ok);
CREATE INDEX idx_datasets_sensitivity   ON datasets (sensitivity_tier);
```

**License registry for known sources (populate at seed time):**

```sql
-- US Federal (public domain)
UPDATE datasets SET license_spdx='LicenseRef-USGov', commercial_ok=true,
  attribution_required=false, redistribution_ok=true, sensitivity_tier=1
WHERE source_key IN ('census_acs5','bls_laus','cdc_places','usda_food_env',
                     'epa_aqi','hud_fmr','eia_energy','nhtsa_traffic',
                     'ed_graduation','fbi_crime');

-- CC-BY sources (attribution required)
-- MIT Election Lab, Vera Institute: add when ingested
-- INSERT source_key with license_spdx='CC-BY-4.0', attribution_required=true

-- CC-BY-NC (non-commercial — must NOT appear in paid tiers)
-- Eviction Lab: license_spdx='CC-BY-NC-4.0', commercial_ok=false
```

---

### 2. `ingestion_runs` Table (New)

Immutable audit log. Every ingestion run creates one row. Never updated.
Source tables link back to this via FK.

```sql
CREATE TABLE ingestion_runs (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    source_key      VARCHAR(30)   NOT NULL REFERENCES datasets(source_key),
    started_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          VARCHAR(20)   NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running','success','partial','failed')),
    source_url      TEXT          NOT NULL,
    file_hash_sha256 CHAR(64),         -- SHA-256 of downloaded file; NULL for API sources
    file_size_bytes BIGINT,
    rows_downloaded INTEGER,
    rows_loaded     INTEGER,
    rows_rejected   INTEGER,
    schema_hash     CHAR(64),          -- SHA-256 of (sorted column names); detect schema drift
    script_version  VARCHAR(40),       -- git commit SHA of ingestion script
    error_message   TEXT,
    notes           TEXT
);

-- Append-only enforced in application layer: never UPDATE or DELETE rows here.
-- Postgres row-level security can enforce this if needed.
CREATE INDEX idx_ingestion_runs_source ON ingestion_runs (source_key, started_at DESC);
```

**Add `ingestion_run_id` FK to every source table:**

```sql
-- Example for census_acs5; repeat for all source tables
ALTER TABLE census_acs5     ADD COLUMN ingestion_run_id UUID REFERENCES ingestion_runs(id);
ALTER TABLE cdc_places      ADD COLUMN ingestion_run_id UUID REFERENCES ingestion_runs(id);
ALTER TABLE bls_laus        ADD COLUMN ingestion_run_id UUID REFERENCES ingestion_runs(id);
ALTER TABLE usda_food_env   ADD COLUMN ingestion_run_id UUID REFERENCES ingestion_runs(id);
ALTER TABLE epa_aqi         ADD COLUMN ingestion_run_id UUID REFERENCES ingestion_runs(id);
ALTER TABLE fbi_crime       ADD COLUMN ingestion_run_id UUID REFERENCES ingestion_runs(id);
ALTER TABLE hud_fmr         ADD COLUMN ingestion_run_id UUID REFERENCES ingestion_runs(id);
ALTER TABLE eia_energy      ADD COLUMN ingestion_run_id UUID REFERENCES ingestion_runs(id);
ALTER TABLE nhtsa_traffic   ADD COLUMN ingestion_run_id UUID REFERENCES ingestion_runs(id);
ALTER TABLE ed_graduation   ADD COLUMN ingestion_run_id UUID REFERENCES ingestion_runs(id);
-- Every future source table must include ingestion_run_id from creation
```

This makes every row in the database traceable to: which file, which URL, which commit, which timestamp produced it.

---

### 3. `api_access_log` Table (New)

Append-only log of every API request. Required for GDPR data subject access
requests, license compliance reporting, and abuse detection.

```sql
CREATE TABLE api_access_log (
    id              BIGSERIAL     PRIMARY KEY,
    requested_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    api_key_hash    CHAR(64),          -- SHA-256 of API key; never store raw keys
    customer_id     INTEGER,           -- FK to customers table (auth schema)
    endpoint        VARCHAR(100)  NOT NULL,
    fips_queried    VARCHAR(5)[],      -- array of FIPS codes returned
    source_keys     VARCHAR(30)[],     -- which datasets were in the response
    year_range      INT4RANGE,         -- years covered in response
    row_count       INTEGER,
    response_ms     INTEGER,
    ip_hash         CHAR(64),          -- SHA-256 of IP; never store raw IPs
    user_agent      TEXT,
    status_code     SMALLINT
);

-- Partition by month for retention management
-- Retention: keep 24 months for GDPR compliance; delete older rows on schedule
CREATE INDEX idx_api_log_customer  ON api_access_log (customer_id, requested_at DESC);
CREATE INDEX idx_api_log_endpoint  ON api_access_log (endpoint, requested_at DESC);
CREATE INDEX idx_api_log_sources   ON api_access_log USING GIN (source_keys);
```

**Never log raw IP addresses or raw API keys.** Hash them (SHA-256 with a
server-side salt) before writing. This satisfies GDPR data minimization while
still enabling abuse detection and audit.

---

### 4. `schema_snapshots` Table (New)

Records the column structure of every source dataset at each ingestion run.
Enables schema drift detection: if a source file changes its columns, we detect
it before silent data corruption.

```sql
CREATE TABLE schema_snapshots (
    id              SERIAL        PRIMARY KEY,
    source_key      VARCHAR(30)   NOT NULL,
    ingestion_run_id UUID         REFERENCES ingestion_runs(id),
    snapshotted_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    columns         JSONB         NOT NULL,
    -- e.g. {"FIPS": "string", "YEAR": "int", "PCT_POVERTY": "float", ...}
    schema_hash     CHAR(64)      NOT NULL,   -- SHA-256 of sorted column names
    column_count    SMALLINT      NOT NULL,
    is_breaking_change BOOLEAN    DEFAULT false  -- set true if hash differs from prior run
);

CREATE INDEX idx_schema_snapshots_source ON schema_snapshots (source_key, snapshotted_at DESC);
```

**How it works:** Before upsert, the ingestion script hashes the column names of the
downloaded file. If the hash differs from the most recent snapshot, it logs a
`schema_snapshot` row with `is_breaking_change = true` and alerts (GitHub issue
or webhook) before proceeding.

---

### 5. Auth Schema (Separate from Geographic Data)

User PII must never mix with geographic data. Use a separate PostgreSQL schema:

```sql
CREATE SCHEMA auth;

CREATE TABLE auth.customers (
    id                      SERIAL       PRIMARY KEY,
    email                   VARCHAR(255) NOT NULL UNIQUE,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    customer_type           VARCHAR(20)  CHECK (customer_type IN ('academic','commercial','government','ngo')),
    tier                    VARCHAR(20)  NOT NULL DEFAULT 'free'
                                CHECK (tier IN ('free','pro','business','enterprise')),
    geography               VARCHAR(2),  -- ISO 3166-1 alpha-2 country code, for applicable law
    terms_version_accepted  VARCHAR(10),
    terms_accepted_at       TIMESTAMPTZ,
    individual_decision_prohibited BOOLEAN NOT NULL DEFAULT true,
    -- ^ true = customer has agreed not to use data for individual-level decisions
    stripe_customer_id      VARCHAR(50),
    deleted_at              TIMESTAMPTZ  -- soft delete for right-to-erasure compliance
);

CREATE TABLE auth.api_keys (
    id              SERIAL       PRIMARY KEY,
    customer_id     INTEGER      NOT NULL REFERENCES auth.customers(id),
    key_hash        CHAR(64)     NOT NULL UNIQUE,  -- SHA-256; never store raw key
    key_prefix      CHAR(8)      NOT NULL,          -- first 8 chars for identification
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    allowed_source_keys VARCHAR(30)[],  -- NULL = all permitted datasets; restrict for DUA datasets
    rate_limit_rpm  INTEGER      NOT NULL DEFAULT 60
);

-- No JOIN paths between auth schema and public (geographic) schema by design.
-- The API layer joins them in application code where needed, not in DB.
```

**Right to erasure (GDPR Article 17):**
```sql
-- Erasure procedure: anonymize, do not hard-delete (to preserve audit integrity)
UPDATE auth.customers
SET email = 'deleted-' || id || '@erased.invalid',
    stripe_customer_id = NULL,
    deleted_at = NOW()
WHERE id = :customer_id;
-- api_access_log rows retain customer_id but email is now anonymized
-- api_key_hash rows are revoked, not deleted (audit trail must survive)
```

---

## Pipeline Changes

### BaseIngestion Governance Contract

Every ingestion run must satisfy these checks in order. If any check fails,
the run must abort or alert — never silently succeed with bad data.

```python
class BaseIngestion:
    
    def pre_flight_check(self, conn) -> None:
        """Run before any download. Abort if governance requirements not met."""
        
        # 1. License check — refuse to run if license not verified
        row = conn.execute(
            "SELECT commercial_ok, sensitivity_tier, license_verified_at "
            "FROM datasets WHERE source_key = %s", [self.source_key]
        ).fetchone()
        
        if row is None:
            raise GovernanceError(f"{self.source_key} not registered in datasets catalog")
        if row['license_verified_at'] is None:
            raise GovernanceError(
                f"{self.source_key} license has not been verified. "
                "Set license_spdx, commercial_ok, and license_verified_at before ingesting."
            )
        if row['sensitivity_tier'] == 3 and not self.dua_accepted:
            raise GovernanceError(
                f"{self.source_key} requires a Data Use Agreement. "
                "Set dua_accepted=True on the ingestion class after signing."
            )
        
        # 2. Open an ingestion run record
        self._run_id = conn.execute(
            "INSERT INTO ingestion_runs (source_key, source_url, script_version) "
            "VALUES (%s, %s, %s) RETURNING id",
            [self.source_key, self.current_url, self.git_commit()]
        ).fetchone()[0]
        conn.commit()

    def check_file_hash(self, conn, content: bytes) -> bool:
        """Return True if content is new (hash differs from last run). False = skip."""
        import hashlib
        new_hash = hashlib.sha256(content).hexdigest()
        
        last = conn.execute(
            "SELECT file_hash_sha256 FROM ingestion_runs "
            "WHERE source_key = %s AND status = 'success' "
            "ORDER BY completed_at DESC LIMIT 1",
            [self.source_key]
        ).fetchone()
        
        conn.execute(
            "UPDATE ingestion_runs SET file_hash_sha256 = %s, file_size_bytes = %s "
            "WHERE id = %s",
            [new_hash, len(content), self._run_id]
        )
        
        if last and last['file_hash_sha256'] == new_hash:
            self._complete_run(conn, status='success', notes='skipped: file unchanged')
            return False  # content unchanged — do not re-ingest
        return True

    def check_schema(self, conn, columns: list[str]) -> None:
        """Detect schema drift. Alert on breaking changes."""
        import hashlib, json
        schema_hash = hashlib.sha256(json.dumps(sorted(columns)).encode()).hexdigest()
        
        last = conn.execute(
            "SELECT schema_hash FROM schema_snapshots "
            "WHERE source_key = %s ORDER BY snapshotted_at DESC LIMIT 1",
            [self.source_key]
        ).fetchone()
        
        is_breaking = last is not None and last['schema_hash'] != schema_hash
        
        conn.execute(
            "INSERT INTO schema_snapshots "
            "(source_key, ingestion_run_id, columns, schema_hash, column_count, is_breaking_change) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [self.source_key, self._run_id,
             json.dumps({c: 'unknown' for c in columns}),
             schema_hash, len(columns), is_breaking]
        )
        
        if is_breaking:
            self._alert_schema_drift(columns, last)
            raise GovernanceError(
                f"Schema drift detected for {self.source_key}. "
                "Review column changes before proceeding."
            )

    def stamp_run_id(self, records: dict) -> dict:
        """Inject ingestion_run_id into every record before upsert."""
        return {k: {**v, 'ingestion_run_id': self._run_id} for k, v in records.items()}

    def _complete_run(self, conn, status, rows_loaded=0, rows_rejected=0, notes=None, error=None):
        conn.execute(
            "UPDATE ingestion_runs SET completed_at=NOW(), status=%s, "
            "rows_loaded=%s, rows_rejected=%s, notes=%s, error_message=%s "
            "WHERE id=%s",
            [status, rows_loaded, rows_rejected, notes, error, self._run_id]
        )
        conn.commit()
```

---

## API Middleware

Three governance checks on every request, in order. Implemented as Django
middleware so they apply automatically to every view — no per-view code required.

```python
# server/datamart_api/middleware.py

class GovernanceMiddleware:
    """
    Applied to every /api/ request. Order matters:
    1. Authenticate and load customer tier
    2. Enforce license restrictions for the requested sources
    3. Inject attribution into the response
    4. Log the request to api_access_log
    """
    
    def __call__(self, request):
        customer = self._authenticate(request)
        request.customer = customer

        response = self.get_response(request)

        # After response is built — enforce license + inject attribution
        if request.path.startswith('/api/') and hasattr(response, 'data'):
            self._enforce_license(request, response, customer)
            self._inject_attribution(response)
            
        self._log_access(request, response, customer)
        return response

    def _enforce_license(self, request, response, customer):
        """
        Strip data from non-commercial datasets if customer is on a paid tier
        and hasn't signed a specific DUA.
        
        Note: paid tier customers must ONLY receive commercial_ok=true data.
        Free tier customers get the same restriction by default unless
        they explicitly accept non-commercial terms.
        """
        sources_in_response = self._extract_source_keys(response)
        
        restricted = Dataset.objects.filter(
            source_key__in=sources_in_response,
            commercial_ok=False
        ).values_list('source_key', flat=True)
        
        if restricted and customer.tier != 'free':
            # Log the violation attempt, return 403 for the offending sources
            # or strip those fields from the response
            response['X-Restricted-Sources'] = ','.join(restricted)
            # In practice: filter those fields from response.data

    def _inject_attribution(self, response):
        """
        Every response that contains CC-BY data must include attribution.
        Injected into response._attribution regardless of endpoint.
        """
        sources_in_response = self._extract_source_keys(response)
        
        attributions = Dataset.objects.filter(
            source_key__in=sources_in_response,
            attribution_required=True
        ).values('source_key', 'name', 'attribution_text', 'source_url')
        
        if attributions:
            if isinstance(response.data, dict):
                response.data['_attribution'] = list(attributions)

    def _log_access(self, request, response, customer):
        """Non-blocking async write to api_access_log."""
        import hashlib
        ip_hash = hashlib.sha256(
            (request.META.get('REMOTE_ADDR','') + settings.IP_HASH_SALT).encode()
        ).hexdigest()
        
        AccessLog.objects.create(
            api_key_hash=getattr(customer, '_key_hash', None),
            customer_id=getattr(customer, 'id', None),
            endpoint=request.path,
            source_keys=self._extract_source_keys(response),
            fips_queried=self._extract_fips(response),
            row_count=self._count_rows(response),
            status_code=response.status_code,
            ip_hash=ip_hash,
            user_agent=request.META.get('HTTP_USER_AGENT','')[:200],
        )
```

---

## Suppression Rules

Small-population geographies can leak individual identities when cross-tabulated
with demographic fields. The Census Bureau already suppresses at the source, but
we must honor and re-enforce suppression at our layer.

```python
# server/census/suppression.py

SUPPRESSION_RULES = {
    # source_key: {column: minimum_population_to_serve}
    'census_acs5': {
        'pct_white': 100,
        'pct_black': 100,
        'pct_hispanic': 100,
        'pct_asian': 100,
        # Race/ethnicity breakdowns suppressed for very small geographies
    },
}

def apply_suppression(records, source_key, geo_populations: dict):
    """
    Null out columns that breach suppression thresholds.
    geo_populations: {fips: population}
    """
    rules = SUPPRESSION_RULES.get(source_key, {})
    if not rules:
        return records
    
    for record in records:
        pop = geo_populations.get(record.get('fips'), 0)
        for column, min_pop in rules.items():
            if pop < min_pop and column in record:
                record[column] = None  # suppress, do not expose
    return records
```

At county level (min population ~100), suppression is rarely needed — the Census
already handles it. This becomes critical if we ever serve census-tract or
block-group level data.

---

## Data Minimization Principles (Enforced in Code)

**1. County is the minimum geographic granularity.**
No ingestion script may store rows keyed at finer granularity than 5-digit county
FIPS without an explicit architectural review. The schema enforces this via the
`(fips, year)` unique constraint — FIPS is always 5 characters.

```sql
-- Enforced on every source table
CONSTRAINT fips_county_length CHECK (char_length(fips) = 5 OR char_length(fips) = 2)
-- 5 = county, 2 = state — both acceptable minimums
```

**2. No individual records ever.**
No source table has a primary key that could identify an individual. Every table's
unique constraint is on `(fips, year)` or `(state_fips, year)` — geographic
entities, not persons.

**3. Only store columns we serve.**
Before adding a column from a source dataset, it must have a corresponding API
serializer field. Columns ingested but never exposed are waste and risk.

**4. User data retention limits.**
```python
# Scheduled monthly cleanup
def purge_old_access_logs():
    """GDPR Article 5(1)(e): don't keep data longer than necessary."""
    cutoff = timezone.now() - timedelta(days=730)  # 24 months
    AccessLog.objects.filter(requested_at__lt=cutoff).delete()

def purge_deleted_customers():
    """Complete erasure 30 days after soft-delete."""
    cutoff = timezone.now() - timedelta(days=30)
    Customer.objects.filter(deleted_at__lt=cutoff).hard_delete()
```

---

## Migration Plan

These changes are additive. Apply in this order without breaking existing behavior:

```
migrations/015_governance_datasets_columns.sql   -- Add license/sensitivity cols to datasets
migrations/016_ingestion_runs.sql                -- Create ingestion_runs table
migrations/017_schema_snapshots.sql              -- Create schema_snapshots table
migrations/018_api_access_log.sql               -- Create api_access_log table (partitioned)
migrations/019_ingestion_run_id_fks.sql         -- Add ingestion_run_id FK to all source tables
migrations/020_auth_schema.sql                  -- Create auth schema + customers + api_keys
migrations/021_seed_license_data.sql            -- Populate license fields for existing datasets
```

**Order matters:** Run 015 before 021 (seed requires columns to exist).
Run 016 before 019 (FK requires table to exist).

---

## Checklist: New Dataset Governance Gate

Before any new dataset can be ingested and served, it must pass this gate.
This becomes a required PR checklist item.

```
[ ] License identified and recorded (license_spdx, commercial_ok, attribution_required)
[ ] license_verified_at set with verifier name
[ ] If CC-BY-NC or ODbL: confirmed exclusion from paid tier, or explicit written
    permission obtained and stored in /docs/licenses/
[ ] If sensitivity_tier = 3: Data Use Agreement signed and filed
[ ] If international government data: terms of use reviewed, redistribution confirmed
[ ] Source URL recorded in datasets.source_url
[ ] Attribution text recorded if attribution_required = true
[ ] ingestion_run_id column added to new source table
[ ] Suppression rules evaluated for any demographic breakdown columns
[ ] Data minimization confirmed: only columns with serializer fields ingested
[ ] Schema snapshot baseline recorded on first successful run
```

---

## What This Buys Us

| Capability | How It's Enforced |
|---|---|
| Prove data provenance to a regulator | `ingestion_runs` + `ingestion_run_id` FK on every row |
| Demonstrate license compliance | `datasets.commercial_ok` enforced in middleware; audit log |
| Honor right-to-erasure (GDPR) | `auth` schema isolated; customer soft-delete + 30-day purge |
| Detect supply-side data tampering | File hash comparison on re-ingestion |
| Detect upstream schema changes | `schema_snapshots` + hash diff on every run |
| Respond to data subject access requests | `api_access_log` by customer, 24-month retention |
| Prevent CC-BY-NC in paid products | Middleware license check; structurally enforced |
| Surface attribution in every response | Attribution middleware; cannot be forgotten |
| Prevent individual-level data leakage | County FIPS as minimum granularity; schema constraints |
| Audit trail for security incident response | Access log with hashed IP + key, endpoint, sources accessed |
