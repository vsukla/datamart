"""
Ingests CDC PLACES county-level health outcomes from the CDC Socrata API.

Source: CDC PLACES – Local Data for Better Health, County Data
URL:    https://chronicdata.cdc.gov/resource/i46a-9kgh.json

Measures fetched (crude prevalence):
  OBESITY   → pct_obesity
  DIABETES  → pct_diabetes
  CSMOKING  → pct_smoking
  BPHIGH    → pct_hypertension
  DEPRESSION→ pct_depression
  LPA       → pct_no_lpa          (no leisure-time physical activity)
  MHLTH     → pct_poor_mental_health

Usage:
  python ingest_cdc_places.py [--year 2022]
"""

import argparse
import logging
import os
import time
from collections import defaultdict

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../config/.env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

SOCRATA_URL = "https://chronicdata.cdc.gov/resource/i46a-9kgh.json"
MEASURE_MAP = {
    "OBESITY":    "pct_obesity",
    "DIABETES":   "pct_diabetes",
    "CSMOKING":   "pct_smoking",
    "BPHIGH":     "pct_hypertension",
    "DEPRESSION": "pct_depression",
    "LPA":        "pct_no_lpa",
    "MHLTH":      "pct_poor_mental_health",
}
PAGE_LIMIT = 50_000


def fetch_places(year: int, app_token: str | None = None) -> list[dict]:
    """Fetch all county PLACES records for the given year from Socrata."""
    where = (
        f"year={year} AND geo_level='County' AND data_value_type='Crude prevalence'"
        f" AND measureid in ({','.join(repr(m) for m in MEASURE_MAP)})"
    )
    params = {
        "$where": where,
        "$limit": PAGE_LIMIT,
        "$select": "locationid,year,measureid,data_value",
    }
    headers = {}
    if app_token:
        headers["X-App-Token"] = app_token

    all_rows = []
    offset = 0
    while True:
        params["$offset"] = offset
        log.info("Fetching PLACES offset=%d...", offset)
        resp = requests.get(SOCRATA_URL, params=params, headers=headers, timeout=60)
        resp.raise_for_status()
        batch = resp.json()
        all_rows.extend(batch)
        if len(batch) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
        time.sleep(0.5)

    return all_rows


def pivot(rows: list[dict], year: int) -> dict[str, dict]:
    """Group raw Socrata rows into {fips: {col: value}} dicts."""
    by_fips: dict[str, dict] = defaultdict(lambda: {"year": year})
    for row in rows:
        fips = str(row.get("locationid", "")).zfill(5)
        measure = row.get("measureid")
        raw_val = row.get("data_value")
        if measure in MEASURE_MAP and raw_val is not None:
            try:
                by_fips[fips][MEASURE_MAP[measure]] = float(raw_val)
            except (ValueError, TypeError):
                pass
    return by_fips


def upsert(conn, records: dict[str, dict], known_fips: set[str]) -> int:
    sql = """
        INSERT INTO cdc_places
            (fips, year, pct_obesity, pct_diabetes, pct_smoking,
             pct_hypertension, pct_depression, pct_no_lpa, pct_poor_mental_health)
        VALUES
            (%(fips)s, %(year)s, %(pct_obesity)s, %(pct_diabetes)s, %(pct_smoking)s,
             %(pct_hypertension)s, %(pct_depression)s, %(pct_no_lpa)s, %(pct_poor_mental_health)s)
        ON CONFLICT (fips, year) DO UPDATE SET
            pct_obesity          = EXCLUDED.pct_obesity,
            pct_diabetes         = EXCLUDED.pct_diabetes,
            pct_smoking          = EXCLUDED.pct_smoking,
            pct_hypertension     = EXCLUDED.pct_hypertension,
            pct_depression       = EXCLUDED.pct_depression,
            pct_no_lpa           = EXCLUDED.pct_no_lpa,
            pct_poor_mental_health = EXCLUDED.pct_poor_mental_health,
            fetched_at           = NOW()
    """
    count = 0
    with conn.cursor() as cur:
        for fips, data in records.items():
            if fips not in known_fips:
                continue  # skip geographies not in our geo_entities table
            row = {
                "fips": fips,
                "year": data["year"],
                "pct_obesity":           data.get("pct_obesity"),
                "pct_diabetes":          data.get("pct_diabetes"),
                "pct_smoking":           data.get("pct_smoking"),
                "pct_hypertension":      data.get("pct_hypertension"),
                "pct_depression":        data.get("pct_depression"),
                "pct_no_lpa":            data.get("pct_no_lpa"),
                "pct_poor_mental_health": data.get("pct_poor_mental_health"),
            }
            cur.execute(sql, row)
            count += cur.rowcount
    conn.commit()
    return count


def ingest(conn, year: int, app_token: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT fips FROM geo_entities WHERE geo_type = 'county'")
        known_fips = {r[0] for r in cur.fetchall()}

    raw = fetch_places(year, app_token)
    log.info("Fetched %d raw rows from CDC PLACES", len(raw))

    records = pivot(raw, year)
    log.info("Pivoted into %d county records", len(records))

    count = upsert(conn, records, known_fips)
    log.info("Upserted %d rows into cdc_places", count)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2022)
    parser.add_argument("--app-token", default=os.environ.get("CDC_APP_TOKEN"))
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
    )
    try:
        ingest(conn, args.year, args.app_token)
        log.info("Done.")
    finally:
        conn.close()
