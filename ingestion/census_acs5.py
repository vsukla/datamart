"""
Fetches ACS 5-year estimates from the Census API for all states and counties
across multiple years and loads them into PostgreSQL.

Variables pulled (B/C-series detailed tables):
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
  C27001_001E - civilian noninstitutionalized population (health insurance universe)
  C27001_002E - with health insurance coverage
  B08136_001E - aggregate travel time to work in minutes (non-WFH workers)
  B08301_001E - total workers 16+
  B08301_021E - workers who worked from home
  B02001_001E - total population (race universe)
  B02001_002E - white alone
  B02001_003E - Black or African American alone
  B02001_005E - Asian alone
  B03003_001E - Hispanic or Latino origin universe
  B03003_003E - Hispanic or Latino

Usage:
  python census_acs5.py                    # fetch default years (2018–2022)
  python census_acs5.py --years 2021 2022  # fetch specific years
"""

import argparse
import logging
import os
import time
import requests
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../config/.env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

CENSUS_API_KEY = os.environ["CENSUS_API_KEY"]
CENSUS_BASE_URL = "https://api.census.gov/data"
DEFAULT_YEARS = list(range(2018, 2023))  # ACS5 available: 2018–2022
SENTINEL = "-666666666"  # Census placeholder for missing/suppressed values
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds; doubled on each retry

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
    "C27001_001E",  # health insurance universe
    "C27001_002E",  # with health insurance
    "B08136_001E",  # aggregate travel time to work (minutes, non-WFH)
    "B08301_001E",  # total workers 16+
    "B08301_021E",  # worked from home
    "B02001_001E",  # total population (race universe)
    "B02001_002E",  # white alone
    "B02001_003E",  # Black or African American alone
    "B02001_005E",  # Asian alone
    "B03003_001E",  # Hispanic/Latino universe
    "B03003_003E",  # Hispanic or Latino
]


def _fetch(year: int, geo_for: str) -> list[dict]:
    url = f"{CENSUS_BASE_URL}/{year}/acs/acs5"
    params = {
        "get": ",".join(VARIABLES),
        "for": geo_for,
        "key": CENSUS_API_KEY,
    }
    delay = RETRY_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
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
        except RuntimeError:
            raise  # key errors are permanent, don't retry
        except Exception as exc:
            if attempt == MAX_RETRIES:
                log.error("Failed to fetch year=%s geo=%s after %d attempts: %s", year, geo_for, MAX_RETRIES, exc)
                raise
            log.warning("Attempt %d/%d failed for year=%s geo=%s: %s — retrying in %ds",
                        attempt, MAX_RETRIES, year, geo_for, exc, delay)
            time.sleep(delay)
            delay *= 2


def _int(val) -> int | None:
    if val is None or str(val).strip() == SENTINEL:
        return None
    try:
        v = int(val)
        # Census uses several negative codes (e.g. -666666666, -999999999) to
        # indicate suppressed or unavailable data — treat all negatives as NULL.
        return None if v < 0 else v
    except (ValueError, TypeError):
        return None


def _pct(numerator, denominator) -> float | None:
    n, d = _int(numerator), _int(denominator)
    if n is None or not d:
        return None
    return round(n / d * 100, 2)


def _mean_commute(agg_minutes, total_workers, wfh_workers) -> float | None:
    """Mean commute in minutes for workers who commute (excludes WFH)."""
    agg = _int(agg_minutes)
    total = _int(total_workers)
    wfh = _int(wfh_workers) or 0
    commuters = (total or 0) - wfh
    if agg is None or commuters <= 0:
        return None
    return round(agg / commuters, 1)


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
        "pct_health_insured": _pct(raw["C27001_002E"], raw["C27001_001E"]),
        "mean_commute_minutes": _mean_commute(
            raw["B08136_001E"], raw["B08301_001E"], raw["B08301_021E"]
        ),
        "pct_white": _pct(raw["B02001_002E"], raw["B02001_001E"]),
        "pct_black": _pct(raw["B02001_003E"], raw["B02001_001E"]),
        "pct_hispanic": _pct(raw["B03003_003E"], raw["B03003_001E"]),
        "pct_asian": _pct(raw["B02001_005E"], raw["B02001_001E"]),
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
                         unemployment_rate, pct_health_insured, mean_commute_minutes,
                         pct_white, pct_black, pct_hispanic, pct_asian)
                    VALUES
                        (%(fips)s, %(year)s, %(population)s, %(median_income)s,
                         %(pct_bachelors)s, %(median_home_value)s,
                         %(pct_owner_occupied)s, %(pct_poverty)s,
                         %(unemployment_rate)s, %(pct_health_insured)s,
                         %(mean_commute_minutes)s,
                         %(pct_white)s, %(pct_black)s, %(pct_hispanic)s, %(pct_asian)s)
                    ON CONFLICT (fips, year) DO UPDATE SET
                        population           = EXCLUDED.population,
                        median_income        = EXCLUDED.median_income,
                        pct_bachelors        = EXCLUDED.pct_bachelors,
                        median_home_value    = EXCLUDED.median_home_value,
                        pct_owner_occupied   = EXCLUDED.pct_owner_occupied,
                        pct_poverty          = EXCLUDED.pct_poverty,
                        unemployment_rate    = EXCLUDED.unemployment_rate,
                        pct_health_insured   = EXCLUDED.pct_health_insured,
                        mean_commute_minutes = EXCLUDED.mean_commute_minutes,
                        pct_white            = EXCLUDED.pct_white,
                        pct_black            = EXCLUDED.pct_black,
                        pct_hispanic         = EXCLUDED.pct_hispanic,
                        pct_asian            = EXCLUDED.pct_asian,
                        fetched_at           = NOW()
                    """,
                    estimates,
                    page_size=500,
                )
        log.info("Loaded %d geographies, %d estimates.", len(geos), len(estimates))
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Census ACS5 data into PostgreSQL.")
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=DEFAULT_YEARS,
        metavar="YEAR",
        help=f"Years to fetch (default: {DEFAULT_YEARS[0]}–{DEFAULT_YEARS[-1]})",
    )
    args = parser.parse_args()

    all_geos: dict[str, dict] = {}
    all_estimates: list[dict] = []

    for year in args.years:
        log.info("Fetching %d...", year)
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

        log.info("  %d: %d states, %d counties", year, len(state_rows), len(county_rows))

    log.info("Loading %d unique geographies, %d total estimates...", len(all_geos), len(all_estimates))
    load(list(all_geos.values()), all_estimates)
    log.info("Done.")
