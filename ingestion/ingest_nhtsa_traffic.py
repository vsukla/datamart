"""
Ingests NHTSA FARS (Fatality Analysis Reporting System) traffic fatality data
at the county level.

Source: NHTSA static downloads — https://static.nhtsa.gov/nhtsa/downloads/FARS/
No API key required.

One ZIP per year; extracts accident.csv and aggregates FATALS by county FIPS.
Fatality rate (per 100k) is computed using census_acs5 population from the DB.
Counties with COUNTY=0 or COUNTY=999 (unknown) are excluded.

Metrics stored per (fips, year):
  fatalities    — total traffic deaths in that county that year
  fatality_rate — fatalities per 100,000 population (NULL if no census population)

Usage:
  python ingest_nhtsa_traffic.py                       # years 2018–2023
  python ingest_nhtsa_traffic.py --years 2021 2022 2023
"""

import argparse
import csv
import io
import logging
import os
import zipfile
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

FARS_URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/{year}/National/FARS{year}NationalCSV.zip"

DEFAULT_YEARS = list(range(2018, 2024))


def download_zip(year: int) -> bytes:
    url = FARS_URL.format(year=year)
    log.info("Downloading FARS %s from %s ...", year, url)
    resp = requests.get(url, timeout=180, stream=True)
    resp.raise_for_status()
    chunks = []
    for chunk in resp.iter_content(chunk_size=1 << 20):
        chunks.append(chunk)
    return b"".join(chunks)


def parse_accident_csv(zip_bytes: bytes, year: int) -> dict[str, int]:
    """Return {fips: fatality_count} aggregated from accident.csv."""
    fatals: dict[str, int] = defaultdict(int)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        accident_name = next(
            (n for n in zf.namelist() if n.lower().endswith("accident.csv")), None
        )
        if not accident_name:
            raise ValueError(f"accident.csv not found in FARS {year} ZIP")
        with zf.open(accident_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"))
            # First column may have BOM; strip it to get consistent key
            fieldnames = reader.fieldnames or []
            state_col = fieldnames[0] if fieldnames else "STATE"

            for row in reader:
                try:
                    state = int(row[state_col])
                    county = int(row["COUNTY"])
                except (ValueError, KeyError):
                    continue
                if county in (0, 999):
                    continue
                fips = f"{state:02d}{county:03d}"
                try:
                    fatals[fips] += int(row["FATALS"])
                except (ValueError, KeyError):
                    pass

    return dict(fatals)


def load_population(conn, years: list[int]) -> dict[tuple, int]:
    """Return {(fips, year): population} using ACS5 data.

    For each requested year, use the closest available census year (capped at max).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT fips, year, population FROM census_acs5 WHERE population IS NOT NULL"
        )
        census_rows = cur.fetchall()

    # Build {(fips, census_year): population}
    by_fips_year: dict[tuple, int] = {(r[0], r[1]): r[2] for r in census_rows}

    # Unique census years available
    census_years = sorted({r[1] for r in census_rows})
    if not census_years:
        return {}

    population: dict[tuple, int] = {}
    for fips_val in {r[0] for r in census_rows}:
        for year in years:
            # Use the closest census year <= requested year; if none, use the oldest
            matched = max((cy for cy in census_years if cy <= year), default=census_years[0])
            pop = by_fips_year.get((fips_val, matched))
            if pop:
                population[(fips_val, year)] = pop

    return population


def upsert(conn, records: list[dict]) -> int:
    sql = """
        INSERT INTO nhtsa_traffic (fips, year, fatalities, fatality_rate)
        VALUES (%(fips)s, %(year)s, %(fatalities)s, %(fatality_rate)s)
        ON CONFLICT (fips, year) DO UPDATE SET
            fatalities    = EXCLUDED.fatalities,
            fatality_rate = EXCLUDED.fatality_rate,
            fetched_at    = NOW()
    """
    count = 0
    with conn.cursor() as cur:
        for rec in records:
            cur.execute(sql, rec)
            count += cur.rowcount
    conn.commit()
    return count


def get_already_ingested(conn, years: list[int]) -> set[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT fips, year FROM nhtsa_traffic WHERE year = ANY(%s)",
            (years,),
        )
        return {(r[0], r[1]) for r in cur.fetchall()}


def ingest(conn, years: list[int] | None = None) -> int:
    if years is None:
        years = DEFAULT_YEARS

    with conn.cursor() as cur:
        cur.execute("SELECT fips FROM geo_entities WHERE geo_type = 'county'")
        known_fips = {r[0] for r in cur.fetchall()}

    already_done = get_already_ingested(conn, years)
    log.info("Already ingested: %d (fips, year) pairs", len(already_done))

    population = load_population(conn, years)
    total = 0

    for year in years:
        already_this_year = {fips for (fips, y) in already_done if y == year}
        try:
            zip_bytes = download_zip(year)
        except requests.RequestException as exc:
            log.error("Failed to download FARS %s: %s", year, exc)
            continue

        fatals_by_fips = parse_accident_csv(zip_bytes, year)
        log.info("Year %s: %d counties with fatality data", year, len(fatals_by_fips))

        records = []
        for fips, fatalities in fatals_by_fips.items():
            if fips not in known_fips:
                continue
            if fips in already_this_year:
                continue
            pop = population.get((fips, year))
            rate = round(fatalities / pop * 100_000, 1) if pop else None
            records.append({
                "fips": fips,
                "year": year,
                "fatalities": fatalities,
                "fatality_rate": rate,
            })

        # Also upsert counties in our DB that had 0 fatalities (absent from FARS)
        for fips in known_fips - fatals_by_fips.keys() - already_this_year:
            pop = population.get((fips, year))
            records.append({
                "fips": fips,
                "year": year,
                "fatalities": 0,
                "fatality_rate": 0.0 if pop else None,
            })

        n = upsert(conn, records)
        already_done.update((r["fips"], year) for r in records)
        log.info("Year %s: upserted %d rows", year, n)
        total += n

    log.info("Total upserted: %d rows", total)
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--years", nargs="+", type=int, default=DEFAULT_YEARS,
        help="FARS years to ingest (default: 2018–2023)",
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
