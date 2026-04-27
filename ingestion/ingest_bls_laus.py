"""
Ingests BLS Local Area Unemployment Statistics (LAUS) at county level.

Source: BLS Public Data API v2
URL:    https://api.bls.gov/publicAPI/v2/timeseries/data/

Series IDs are constructed as: LAUCN{state_fips(2)}{county_fips(3)}0000000{type(2)}
Series types:
  03 = unemployment rate
  04 = unemployed persons
  05 = employed persons
  06 = labor force

Fetches annual averages (period M13) for the requested year range.
Counties are batched 50 series per API request (BLS limit without a key;
with a registered key the limit is 500 series and rate limits are higher).

Usage:
  python ingest_bls_laus.py [--start 2018] [--end 2022] [--api-key KEY]
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

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
SERIES_TYPES = {"003": "unemployment_rate", "004": "unemployed", "005": "employed", "006": "labor_force"}
BATCH_SIZE_UNREGISTERED = 50
BATCH_SIZE_REGISTERED = 500


def build_series_id(fips: str, series_type: str) -> str:
    # Format: LAUCN + 5-digit FIPS + 0000000 + 3-digit series type
    return f"LAUCN{fips}0000000{series_type}"


def parse_fips_from_series(series_id: str) -> tuple[str, str]:
    """Return (fips, series_type) from a LAUS series ID."""
    # LAUCN(5) + fips(5) + 0000000(7) + type(3) = 20 chars
    fips = series_id[5:10]
    stype = series_id[-3:]
    return fips, stype


def fetch_batch(series_ids: list[str], start: int, end: int, api_key: str | None) -> dict:
    payload = {
        "seriesid": series_ids,
        "startyear": str(start),
        "endyear": str(end),
        "annualaverage": True,
    }
    if api_key:
        payload["registrationkey"] = api_key

    resp = requests.post(BLS_API_URL, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def parse_bls_response(data: dict) -> dict[tuple[str, int], dict]:
    """Returns {(fips, year): {col: value}}."""
    records: dict[tuple[str, int], dict] = defaultdict(dict)
    for series in data.get("Results", {}).get("series", []):
        fips, stype = parse_fips_from_series(series["seriesID"])
        col = SERIES_TYPES.get(stype)
        if not col:
            continue
        for obs in series.get("data", []):
            if obs.get("period") != "M13":  # annual average only
                continue
            try:
                year = int(obs["year"])
                raw = obs["value"].replace(",", "")
                value = float(raw) if col == "unemployment_rate" else int(float(raw))
                records[(fips, year)][col] = value
            except (KeyError, ValueError):
                pass
    return records


def upsert(conn, records: dict[tuple[str, int], dict]) -> int:
    sql = """
        INSERT INTO bls_laus
            (fips, year, labor_force, employed, unemployed, unemployment_rate)
        VALUES
            (%(fips)s, %(year)s, %(labor_force)s, %(employed)s,
             %(unemployed)s, %(unemployment_rate)s)
        ON CONFLICT (fips, year) DO UPDATE SET
            labor_force       = EXCLUDED.labor_force,
            employed          = EXCLUDED.employed,
            unemployed        = EXCLUDED.unemployed,
            unemployment_rate = EXCLUDED.unemployment_rate,
            fetched_at        = NOW()
    """
    count = 0
    with conn.cursor() as cur:
        for (fips, year), data in records.items():
            row = {
                "fips": fips,
                "year": year,
                "labor_force":       data.get("labor_force"),
                "employed":          data.get("employed"),
                "unemployed":        data.get("unemployed"),
                "unemployment_rate": data.get("unemployment_rate"),
            }
            cur.execute(sql, row)
            count += cur.rowcount
    conn.commit()
    return count


def ingest(conn, start: int, end: int, api_key: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT fips FROM geo_entities WHERE geo_type = 'county' ORDER BY fips")
        county_fips = [r[0] for r in cur.fetchall()]

    log.info("Building series IDs for %d counties...", len(county_fips))
    all_series = [
        build_series_id(fips, stype)
        for fips in county_fips
        for stype in SERIES_TYPES  # keys are "003", "004", "005", "006"
    ]

    batch_size = BATCH_SIZE_REGISTERED if api_key else BATCH_SIZE_UNREGISTERED
    all_records: dict[tuple[str, int], dict] = defaultdict(dict)

    for i in range(0, len(all_series), batch_size):
        batch = all_series[i : i + batch_size]
        log.info("Fetching batch %d/%d (%d series)...",
                 i // batch_size + 1, (len(all_series) + batch_size - 1) // batch_size, len(batch))
        try:
            data = fetch_batch(batch, start, end, api_key)
            if data.get("status") != "REQUEST_SUCCEEDED":
                log.warning("BLS API status: %s — %s",
                            data.get("status"), data.get("message", []))
            parsed = parse_bls_response(data)
            for key, vals in parsed.items():
                all_records[key].update(vals)
        except requests.RequestException as exc:
            log.error("Batch %d failed: %s", i // batch_size + 1, exc)
        time.sleep(1.0)

    log.info("Parsed %d county×year records", len(all_records))
    count = upsert(conn, all_records)
    log.info("Upserted %d rows into bls_laus", count)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2018)
    parser.add_argument("--end",   type=int, default=2022)
    parser.add_argument("--api-key", default=os.environ.get("BLS_API_KEY"))
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
    )
    try:
        ingest(conn, args.start, args.end, args.api_key)
        log.info("Done.")
    finally:
        conn.close()
