"""
Fetches ACS 5-year state-level estimates from the Census API and loads them
into PostgreSQL. Variables pulled:
  B01003_001E - total population
  B19013_001E - median household income
  B15003_022E - bachelor's degree holders (25+)
  B15003_001E - total population 25+ (denominator for pct_bachelors)
"""

import os
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../config/.env"))

CENSUS_API_KEY = os.environ["CENSUS_API_KEY"]
CENSUS_BASE_URL = "https://api.census.gov/data"
YEAR = 2022

VARIABLES = [
    "NAME",
    "B01003_001E",  # total population
    "B19013_001E",  # median household income
    "B15003_022E",  # bachelor's degree (25+)
    "B15003_001E",  # total pop 25+ (for pct calc)
]


def fetch_state_data(year: int) -> list[dict]:
    url = f"{CENSUS_BASE_URL}/{year}/acs/acs5"
    params = {
        "get": ",".join(VARIABLES),
        "for": "state:*",
        "key": CENSUS_API_KEY,
    }
    response = requests.get(url, params=params, timeout=30, allow_redirects=False)

    if response.status_code in (301, 302) or response.headers.get("X-DataWebAPI-KeyError"):
        raise RuntimeError("Census API key is invalid or not yet activated. Check your email for a confirmation link.")

    response.raise_for_status()
    rows = response.json()
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:]]


def normalize(raw: dict, year: int) -> dict:
    pop_25_plus = int(raw["B15003_001E"] or 0)
    bachelors = int(raw["B15003_022E"] or 0)
    pct_bachelors = round(bachelors / pop_25_plus * 100, 2) if pop_25_plus > 0 else None

    income = int(raw["B19013_001E"]) if raw["B19013_001E"] not in (None, "-666666666") else None

    return {
        "state_fips": raw["state"].zfill(2),
        "state_name": raw["NAME"],
        "year": year,
        "population": int(raw["B01003_001E"]) if raw["B01003_001E"] else None,
        "median_income": income,
        "pct_bachelors": pct_bachelors,
    }


def load(records: list[dict]) -> None:
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
    )
    try:
        with conn:
            with conn.cursor() as cur:
                for rec in records:
                    cur.execute(
                        """
                        INSERT INTO census_acs5_states
                            (state_fips, state_name, year, population, median_income, pct_bachelors)
                        VALUES
                            (%(state_fips)s, %(state_name)s, %(year)s,
                             %(population)s, %(median_income)s, %(pct_bachelors)s)
                        ON CONFLICT (state_fips, year) DO UPDATE SET
                            population    = EXCLUDED.population,
                            median_income = EXCLUDED.median_income,
                            pct_bachelors = EXCLUDED.pct_bachelors,
                            fetched_at    = NOW()
                        """,
                        rec,
                    )
        print(f"Loaded {len(records)} state records for {YEAR}.")
    finally:
        conn.close()


if __name__ == "__main__":
    print(f"Fetching ACS5 state data for {YEAR}...")
    raw_rows = fetch_state_data(YEAR)
    normalized = [normalize(row, YEAR) for row in raw_rows]
    load(normalized)
