"""
Fetches ACS 5-year estimates from the Census API for all states and counties
across multiple years and loads them into PostgreSQL.

Variables pulled (B-series detailed tables):
  B01003_001E - total population
  B19013_001E - median household income
  B15003_022E - bachelor's degree holders (25+)
  B15003_001E - total population 25+ (education denominator)
  B25077_001E - median home value
  B25003_001E - total occupied housing units
  B25003_002E - owner-occupied housing units
  B17001_002E - population below poverty level
  B17001_001E - poverty universe (poverty denominator)
  B23025_005E - unemployed persons in labor force
  B23025_002E - total in labor force (employment denominator)
"""

import os
import requests
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../config/.env"))

CENSUS_API_KEY = os.environ["CENSUS_API_KEY"]
CENSUS_BASE_URL = "https://api.census.gov/data"
YEARS = list(range(2018, 2023))  # ACS5 available: 2018–2022
SENTINEL = "-666666666"  # Census placeholder for missing/suppressed values

VARIABLES = [
    "NAME",
    "B01003_001E",  # total population
    "B19013_001E",  # median household income
    "B15003_022E",  # bachelor's degree (25+)
    "B15003_001E",  # total pop 25+ (education denominator)
    "B25077_001E",  # median home value
    "B25003_001E",  # total occupied housing units
    "B25003_002E",  # owner-occupied housing units
    "B17001_002E",  # below poverty level
    "B17001_001E",  # poverty universe
    "B23025_005E",  # unemployed
    "B23025_002E",  # in labor force
]


def _fetch(year: int, geo_for: str) -> list[dict]:
    url = f"{CENSUS_BASE_URL}/{year}/acs/acs5"
    params = {
        "get": ",".join(VARIABLES),
        "for": geo_for,
        "key": CENSUS_API_KEY,
    }
    resp = requests.get(url, params=params, timeout=60, allow_redirects=False)
    if resp.status_code in (301, 302) or resp.headers.get("X-DataWebAPI-KeyError"):
        raise RuntimeError(
            "Census API key invalid or not yet activated. "
            "Check your email for a confirmation link."
        )
    resp.raise_for_status()
    rows = resp.json()
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:]]


def _int(val) -> int | None:
    if val is None or str(val).strip() == SENTINEL:
        return None
    try:
        v = int(val)
        return None if v < 0 else v
    except (ValueError, TypeError):
        return None


def _pct(numerator, denominator) -> float | None:
    n, d = _int(numerator), _int(denominator)
    if n is None or not d:
        return None
    return round(n / d * 100, 2)


def _normalize(raw: dict, year: int, fips: str, geo_type: str, state_fips: str) -> tuple[dict, dict]:
    geo = {
        "fips": fips,
        "geo_type": geo_type,
        "name": raw["NAME"],
        "state_fips": state_fips,
    }
    estimate = {
        "fips": fips,
        "year": year,
        "population": _int(raw["B01003_001E"]),
        "median_income": _int(raw["B19013_001E"]),
        "pct_bachelors": _pct(raw["B15003_022E"], raw["B15003_001E"]),
        "median_home_value": _int(raw["B25077_001E"]),
        "pct_owner_occupied": _pct(raw["B25003_002E"], raw["B25003_001E"]),
        "pct_poverty": _pct(raw["B17001_002E"], raw["B17001_001E"]),
        "unemployment_rate": _pct(raw["B23025_005E"], raw["B23025_002E"]),
    }
    return geo, estimate


def normalize_state(raw: dict, year: int) -> tuple[dict, dict]:
    fips = raw["state"].zfill(2)
    return _normalize(raw, year, fips, "state", fips)


def normalize_county(raw: dict, year: int) -> tuple[dict, dict]:
    state_fips = raw["state"].zfill(2)
    fips = state_fips + raw["county"].zfill(3)
    return _normalize(raw, year, fips, "county", state_fips)


def load(geos: list[dict], estimates: list[dict]) -> None:
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
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    INSERT INTO geo_entities (fips, geo_type, name, state_fips)
                    VALUES (%(fips)s, %(geo_type)s, %(name)s, %(state_fips)s)
                    ON CONFLICT (fips) DO UPDATE SET
                        name       = EXCLUDED.name,
                        state_fips = EXCLUDED.state_fips
                    """,
                    geos,
                    page_size=500,
                )
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    INSERT INTO census_acs5
                        (fips, year, population, median_income, pct_bachelors,
                         median_home_value, pct_owner_occupied, pct_poverty,
                         unemployment_rate)
                    VALUES
                        (%(fips)s, %(year)s, %(population)s, %(median_income)s,
                         %(pct_bachelors)s, %(median_home_value)s,
                         %(pct_owner_occupied)s, %(pct_poverty)s,
                         %(unemployment_rate)s)
                    ON CONFLICT (fips, year) DO UPDATE SET
                        population         = EXCLUDED.population,
                        median_income      = EXCLUDED.median_income,
                        pct_bachelors      = EXCLUDED.pct_bachelors,
                        median_home_value  = EXCLUDED.median_home_value,
                        pct_owner_occupied = EXCLUDED.pct_owner_occupied,
                        pct_poverty        = EXCLUDED.pct_poverty,
                        unemployment_rate  = EXCLUDED.unemployment_rate,
                        fetched_at         = NOW()
                    """,
                    estimates,
                    page_size=500,
                )
        print(f"Loaded {len(geos)} geographies, {len(estimates)} estimates.")
    finally:
        conn.close()


if __name__ == "__main__":
    all_geos: dict[str, dict] = {}
    all_estimates: list[dict] = []

    for year in YEARS:
        print(f"Fetching {year}...")
        state_rows = _fetch(year, "state:*")
        county_rows = _fetch(year, "county:*")

        for raw in state_rows:
            geo, est = normalize_state(raw, year)
            all_geos[geo["fips"]] = geo
            all_estimates.append(est)

        for raw in county_rows:
            geo, est = normalize_county(raw, year)
            all_geos[geo["fips"]] = geo
            all_estimates.append(est)

        print(f"  {year}: {len(state_rows)} states, {len(county_rows)} counties")

    print(f"Loading {len(all_geos)} unique geographies, {len(all_estimates)} total estimates...")
    load(list(all_geos.values()), all_estimates)
    print("Done.")
