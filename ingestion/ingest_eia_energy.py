"""
Ingests EIA State Energy Data System (SEDS) electricity and natural gas
consumption at the state level.

Source: EIA API v2 — https://api.eia.gov/v2/seds/data/
Auth:   None required (uses DEMO_KEY; add EIA_API_KEY to .env for higher limits)

All 8 series for all 51 states/DC are fetched in a single API call per year.
Values are in Billion Btu.

Series loaded:
  ESRCB → elec_res_bbtu    (electricity, residential)
  ESCCB → elec_com_bbtu    (electricity, commercial)
  ESICB → elec_ind_bbtu    (electricity, industrial)
  ESTCB → elec_total_bbtu  (electricity, total end-use)
  NGRCB → gas_res_bbtu     (natural gas, residential)
  NGCCB → gas_com_bbtu     (natural gas, commercial)
  NGICB → gas_ind_bbtu     (natural gas, industrial)
  NGTCB → gas_total_bbtu   (natural gas, total)

Usage:
  python ingest_eia_energy.py                      # years 2018–2024
  python ingest_eia_energy.py --years 2022 2023
"""

import argparse
import logging
import os
import time

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

EIA_URL = "https://api.eia.gov/v2/seds/data/"

SERIES = {
    "ESRCB": "elec_res_bbtu",
    "ESCCB": "elec_com_bbtu",
    "ESICB": "elec_ind_bbtu",
    "ESTCB": "elec_total_bbtu",
    "NGRCB": "gas_res_bbtu",
    "NGCCB": "gas_com_bbtu",
    "NGICB": "gas_ind_bbtu",
    "NGTCB": "gas_total_bbtu",
}

STATE_ABBR_TO_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
    "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
    "WY": "56",
}

DEFAULT_YEARS = list(range(2018, 2025))


def _safe_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def fetch_year(api_key: str, year: int) -> list[dict]:
    params = {
        "api_key": api_key,
        "data[]": "value",
        "frequency": "annual",
        "start": str(year),
        "end": str(year),
        "length": 5000,
    }
    for sid in SERIES:
        params.setdefault("facets[seriesId][]", [])
        if isinstance(params["facets[seriesId][]"], list):
            params["facets[seriesId][]"].append(sid)

    # requests doesn't handle list params with [] keys well; build manually
    parts = [
        ("api_key", api_key),
        ("data[]", "value"),
        ("frequency", "annual"),
        ("start", str(year)),
        ("end", str(year)),
        ("length", "5000"),
    ]
    for sid in SERIES:
        parts.append(("facets[seriesId][]", sid))

    resp = requests.get(EIA_URL, params=parts, timeout=30)
    resp.raise_for_status()
    return resp.json()["response"]["data"]


def pivot(rows: list[dict]) -> dict[tuple, dict]:
    """Return {(state_fips, year): {col: value}} pivoting series into columns."""
    records: dict[tuple, dict] = {}
    for r in rows:
        abbr = r.get("stateId", "")
        fips = STATE_ABBR_TO_FIPS.get(abbr)
        if fips is None:
            continue  # skip US total and any unknown codes
        try:
            year = int(r["period"])
        except (ValueError, TypeError, KeyError):
            continue
        col = SERIES.get(r.get("seriesId", ""))
        if col is None:
            continue
        key = (fips, year)
        records.setdefault(key, {})[col] = _safe_int(r.get("value"))
    return records


def upsert(conn, records: dict[tuple, dict]) -> int:
    sql = """
        INSERT INTO eia_energy
            (state_fips, year,
             elec_res_bbtu, elec_com_bbtu, elec_ind_bbtu, elec_total_bbtu,
             gas_res_bbtu,  gas_com_bbtu,  gas_ind_bbtu,  gas_total_bbtu)
        VALUES
            (%(state_fips)s, %(year)s,
             %(elec_res_bbtu)s, %(elec_com_bbtu)s, %(elec_ind_bbtu)s, %(elec_total_bbtu)s,
             %(gas_res_bbtu)s,  %(gas_com_bbtu)s,  %(gas_ind_bbtu)s,  %(gas_total_bbtu)s)
        ON CONFLICT (state_fips, year) DO UPDATE SET
            elec_res_bbtu   = EXCLUDED.elec_res_bbtu,
            elec_com_bbtu   = EXCLUDED.elec_com_bbtu,
            elec_ind_bbtu   = EXCLUDED.elec_ind_bbtu,
            elec_total_bbtu = EXCLUDED.elec_total_bbtu,
            gas_res_bbtu    = EXCLUDED.gas_res_bbtu,
            gas_com_bbtu    = EXCLUDED.gas_com_bbtu,
            gas_ind_bbtu    = EXCLUDED.gas_ind_bbtu,
            gas_total_bbtu  = EXCLUDED.gas_total_bbtu,
            fetched_at      = NOW()
    """
    count = 0
    with conn.cursor() as cur:
        for (state_fips, year), data in records.items():
            cur.execute(sql, {
                "state_fips":      state_fips,
                "year":            year,
                "elec_res_bbtu":   data.get("elec_res_bbtu"),
                "elec_com_bbtu":   data.get("elec_com_bbtu"),
                "elec_ind_bbtu":   data.get("elec_ind_bbtu"),
                "elec_total_bbtu": data.get("elec_total_bbtu"),
                "gas_res_bbtu":    data.get("gas_res_bbtu"),
                "gas_com_bbtu":    data.get("gas_com_bbtu"),
                "gas_ind_bbtu":    data.get("gas_ind_bbtu"),
                "gas_total_bbtu":  data.get("gas_total_bbtu"),
            })
            count += cur.rowcount
    conn.commit()
    return count


def get_already_ingested(conn, years: list[int]) -> set[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT state_fips, year FROM eia_energy WHERE year = ANY(%s)",
            (years,),
        )
        return {(r[0], r[1]) for r in cur.fetchall()}


def ingest(conn, years: list[int] | None = None) -> int:
    if years is None:
        years = DEFAULT_YEARS

    api_key = os.environ.get("EIA_API_KEY", "DEMO_KEY")
    already_done = get_already_ingested(conn, years)
    log.info("Already ingested: %d (state, year) pairs", len(already_done))

    total = 0
    for year in years:
        try:
            rows = fetch_year(api_key, year)
        except requests.RequestException as exc:
            log.error("Failed to fetch year %s: %s", year, exc)
            continue

        records = pivot(rows)
        new_records = {k: v for k, v in records.items() if k not in already_done}

        if new_records:
            n = upsert(conn, new_records)
            already_done.update(new_records.keys())
            total += n
            log.info("Year %s: upserted %d rows", year, n)
        else:
            log.info("Year %s: all rows already ingested", year)

        time.sleep(0.2)

    log.info("Total upserted: %d rows", total)
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--years", nargs="+", type=int, default=DEFAULT_YEARS,
        help="Years to ingest (default: 2018–2024)",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
    )
    try:
        ingest(conn, args.years)
        log.info("Done.")
    finally:
        conn.close()
