# Dev Tips

## Open a terminal in VS Code

`Ctrl + `` ` `` ` or **View → Terminal**

---

## Run the dev server

```bash
cd server
python manage.py runserver
```

Dashboard: http://localhost:8000/dashboard/
API root:  http://localhost:8000/api/

---

## Query the database

### Interactive psql shell

```bash
psql postgresql://vsukla@localhost:5432/datamart
```

Useful psql commands:

| Command | Description |
|---------|-------------|
| `\dt`   | List all tables |
| `\d tablename` | Describe a table's columns |
| `\q`    | Quit |

### One-liner (no shell)

```bash
psql postgresql://vsukla@localhost:5432/datamart -c "SELECT fips, pct_obesity FROM cdc_places LIMIT 10;"
```

### Django ORM shell

```bash
cd server
python manage.py shell
```

```python
from census.models import CdcPlaces, CountyProfile
CdcPlaces.objects.filter(fips="06037").values()
CountyProfile.objects.filter(state_fips="06")[:5]
```

### Via the REST API

```
http://localhost:8000/api/profile/?state_fips=06
http://localhost:8000/api/health/?fips=06037
http://localhost:8000/api/labor/?state_fips=48&year=2022
http://localhost:8000/api/food/?state_fips=06
```

All list endpoints support `?page_size=N` (max 400) and `?page=N`.

---

## Run tests

```bash
pytest tests/
pytest tests/ -v                  # verbose
pytest tests/test_api.py -v       # one file
pytest tests/ -k "health"         # filter by name
```

---

## Apply database migrations

```bash
# Load env vars first
export $(grep -v '^#' config/.env | xargs)

# Apply all pending migrations
./migrations/migrate.sh

# Fresh database (creates everything from scratch)
psql postgresql://vsukla@localhost:5432/datamart -f schema/schema.sql
```

---

## Run ingestion scripts

```bash
# Census ACS5 (states + counties, 2018-2022)
python ingestion/census_acs5.py

# Pre-computed aggregates (run after census_acs5)
python ingestion/compute_aggregates.py

# CDC PLACES health outcomes
python ingestion/ingest_cdc_places.py --year 2022

# BLS Local Area Unemployment (slow without API key — ~250 requests)
python ingestion/ingest_bls_laus.py --start 2018 --end 2022
python ingestion/ingest_bls_laus.py --start 2018 --end 2022 --api-key YOUR_KEY

# USDA Food Environment Atlas (download file from USDA ERS first)
python ingestion/ingest_usda_food_env.py --file /path/to/FoodEnvironmentAtlas.xls
python ingestion/ingest_usda_food_env.py --download   # auto-download
```

All scripts read DB credentials from `config/.env` automatically.
