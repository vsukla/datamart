"""
Ingests HUD Fair Market Rents (FMR) at county level via the HUD User API.

Source: HUD USER API — https://www.huduser.gov/portal/dataset/fmr-api.html
Auth:   Bearer token (HUD_API_KEY in config/.env)

One request per state per year returns all counties in that state.
51 states/DC × N years = manageable call count.

FIPS: API returns a 10-digit code (5-digit county FIPS + "99999").
      We store only the 5-digit prefix.

Metrics loaded per (fips, year):
  Efficiency   → fmr_0br
  One-Bedroom  → fmr_1br
  Two-Bedroom  → fmr_2br
  Three-Bedroom → fmr_3br
  Four-Bedroom → fmr_4br

Usage:
  python ingest_hud_fmr.py                        # years 2018–2024
  python ingest_hud_fmr.py --years 2022 2023 2024
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

BASE_URL = "https://www.huduser.gov/hudapi/public/fmr/statedata/{state}"

STATE_ABBRS = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL",
    "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]

DEFAULT_YEARS = list(range(2018, 2025))


def fetch_state(session: requests.Session, token: str, state: str, year: int) -> tuple[int, list[dict]]:
    """Return (actual_year, counties) where actual_year comes from the API response."""
    url = BASE_URL.format(state=state)
    resp = session.get(url, params={"year": year},
                       headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", {})
    actual_year = int(data.get("year", year))
    return actual_year, data.get("counties", [])


def parse_counties(counties: list[dict], known_fips: set[str], year: int) -> dict[tuple, dict]:
    """Return {(fips, year): {fmr_0br, ...}} for known FIPS only."""
    records = {}
    for c in counties:
        raw_fips = str(c.get("fips_code", ""))
        if len(raw_fips) < 5:
            continue
        fips = raw_fips[:5]
        if fips not in known_fips:
            continue
        records[(fips, year)] = {
            "fmr_0br": c.get("Efficiency"),
            "fmr_1br": c.get("One-Bedroom"),
            "fmr_2br": c.get("Two-Bedroom"),
            "fmr_3br": c.get("Three-Bedroom"),
            "fmr_4br": c.get("Four-Bedroom"),
        }
    return records


def upsert(conn, records: dict[tuple, dict]) -> int:
    sql = """
        INSERT INTO hud_fmr (fips, year, fmr_0br, fmr_1br, fmr_2br, fmr_3br, fmr_4br)
        VALUES (%(fips)s, %(year)s, %(fmr_0br)s, %(fmr_1br)s, %(fmr_2br)s, %(fmr_3br)s, %(fmr_4br)s)
        ON CONFLICT (fips, year) DO UPDATE SET
            fmr_0br    = EXCLUDED.fmr_0br,
            fmr_1br    = EXCLUDED.fmr_1br,
            fmr_2br    = EXCLUDED.fmr_2br,
            fmr_3br    = EXCLUDED.fmr_3br,
            fmr_4br    = EXCLUDED.fmr_4br,
            fetched_at = NOW()
    """
    count = 0
    with conn.cursor() as cur:
        for (fips, year), data in records.items():
            cur.execute(sql, {"fips": fips, "year": year, **data})
            count += cur.rowcount
    conn.commit()
    return count


def get_already_ingested(conn, years: list[int]) -> set[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT fips, year FROM hud_fmr WHERE year = ANY(%s)",
            (years,),
        )
        return {(r[0], r[1]) for r in cur.fetchall()}


def ingest(conn, years: list[int] | None = None) -> int:
    if years is None:
        years = DEFAULT_YEARS

    token = os.environ["HUD_API_KEY"]

    with conn.cursor() as cur:
        cur.execute("SELECT fips FROM geo_entities WHERE geo_type = 'county'")
        known_fips = {r[0] for r in cur.fetchall()}

    already_done = get_already_ingested(conn, years)
    log.info("Already ingested: %d (fips, year) pairs", len(already_done))

    session = requests.Session()
    total = 0

    for year in years:
        year_count = 0
        for state in STATE_ABBRS:
            try:
                actual_year, counties = fetch_state(session, token, state, year)
            except requests.HTTPError as exc:
                log.warning("HTTP error fetching %s/%s: %s", state, year, exc)
                time.sleep(2)
                continue
            except requests.RequestException as exc:
                log.warning("Request error fetching %s/%s: %s", state, year, exc)
                continue

            records = parse_counties(counties, known_fips, actual_year)
            new_records = {k: v for k, v in records.items() if k not in already_done}

            if new_records:
                n = upsert(conn, new_records)
                already_done.update(new_records.keys())
                year_count += n

            time.sleep(0.5)  # 2 req/s — HUD free tier rate limit headroom

        log.info("Year %s: upserted %d rows", year, year_count)
        total += year_count

    log.info("Total upserted: %d rows", total)
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--years", nargs="+", type=int, default=DEFAULT_YEARS,
        help="FMR fiscal years to ingest (default: 2018–2024)",
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
