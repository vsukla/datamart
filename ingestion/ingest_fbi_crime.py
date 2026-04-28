"""
Ingests FBI Uniform Crime Reporting (UCR) / NIBRS data at county level.

Source: FBI Crime Data Explorer county flat files
URL pattern: https://cde.ucr.cjis.gov/LATEST/webapp/assets/data/county_{year}.zip

CSV columns inside each zip (agency-level rows, aggregated here to county):
  State Code, County Code, Year, Population, Violent Crime, Property Crime
  (where State Code = 2-digit FIPS, County Code = 3-digit FIPS)

Multiple agencies per county are summed. Rates are computed as:
  rate = (count / population) * 100,000

Usage:
  python ingest_fbi_crime.py [--start 2018] [--end 2022]
  python ingest_fbi_crime.py --file /path/to/county_crime_2022.csv --year 2022
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

FLAT_FILE_URL_TPL = (
    "https://cde.ucr.cjis.gov/LATEST/webapp/assets/data/county_{year}.zip"
)


def _int_or_none(value: str) -> int | None:
    v = value.strip().replace(",", "")
    if not v:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def parse_crime_csv(content: bytes | str) -> dict[tuple[str, int], dict]:
    """
    Parse FBI county crime CSV into {(fips, year): {col: value}}.

    Aggregates agency-level rows to county by summing population and crime counts,
    then computes per-100k rates.
    """
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
    else:
        text = content

    # Accumulate: {(fips, year): {pop, violent, property}}
    accum: dict[tuple[str, int], dict] = defaultdict(
        lambda: {"population": 0, "violent": 0, "property": 0}
    )

    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        state_code  = row.get("State Code", "").strip().zfill(2)
        county_code = row.get("County Code", "").strip().zfill(3)
        if not state_code.isdigit() or not county_code.isdigit():
            continue
        fips = state_code + county_code
        try:
            year = int(row.get("Year", "").strip())
        except (ValueError, TypeError):
            continue

        pop  = _int_or_none(row.get("Population", "")) or 0
        viol = _int_or_none(row.get("Violent Crime", "")) or 0
        prop = _int_or_none(row.get("Property Crime", "")) or 0

        key = (fips, year)
        accum[key]["population"] += pop
        accum[key]["violent"]    += viol
        accum[key]["property"]   += prop

    records: dict[tuple[str, int], dict] = {}
    for (fips, year), totals in accum.items():
        pop  = totals["population"]
        viol = totals["violent"]
        prop = totals["property"]
        records[(fips, year)] = {
            "population_covered":  pop if pop else None,
            "violent_crimes":      viol if pop else None,
            "violent_crime_rate":  round(viol / pop * 100_000, 1) if pop else None,
            "property_crimes":     prop if pop else None,
            "property_crime_rate": round(prop / pop * 100_000, 1) if pop else None,
        }
    return records


def upsert(conn, records: dict[tuple[str, int], dict], known_fips: set[str]) -> int:
    sql = """
        INSERT INTO fbi_crime
            (fips, year, population_covered,
             violent_crimes, violent_crime_rate,
             property_crimes, property_crime_rate)
        VALUES
            (%(fips)s, %(year)s, %(population_covered)s,
             %(violent_crimes)s, %(violent_crime_rate)s,
             %(property_crimes)s, %(property_crime_rate)s)
        ON CONFLICT (fips, year) DO UPDATE SET
            population_covered  = EXCLUDED.population_covered,
            violent_crimes      = EXCLUDED.violent_crimes,
            violent_crime_rate  = EXCLUDED.violent_crime_rate,
            property_crimes     = EXCLUDED.property_crimes,
            property_crime_rate = EXCLUDED.property_crime_rate,
            fetched_at          = NOW()
    """
    count = 0
    with conn.cursor() as cur:
        for (fips, year), data in records.items():
            if fips not in known_fips:
                continue
            row = {"fips": fips, "year": year, **data}
            cur.execute(sql, row)
            count += cur.rowcount
    conn.commit()
    return count


def ingest(conn, start: int, end: int) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT fips FROM geo_entities WHERE geo_type = 'county'")
        known_fips = {r[0] for r in cur.fetchall()}

    total = 0
    for year in range(start, end + 1):
        url = FLAT_FILE_URL_TPL.format(year=year)
        log.info("Downloading FBI crime flat file for %d: %s", year, url)
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
            csv_bytes = zf.read(csv_name)
        records = parse_crime_csv(csv_bytes)
        log.info("Parsed %d county-year records for %d", len(records), year)
        count = upsert(conn, records, known_fips)
        log.info("Upserted %d rows for %d", count, year)
        total += count
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2018)
    parser.add_argument("--end",   type=int, default=2022)
    parser.add_argument("--file",  help="Path to a local county crime CSV")
    parser.add_argument("--year",  type=int, help="Year for --file mode (required with --file)")
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
    )
    try:
        if args.file:
            if not args.year:
                parser.error("--year is required with --file")
            with conn.cursor() as cur:
                cur.execute("SELECT fips FROM geo_entities WHERE geo_type = 'county'")
                known_fips = {r[0] for r in cur.fetchall()}
            with open(args.file, "rb") as fh:
                records = parse_crime_csv(fh.read())
            count = upsert(conn, records, known_fips)
            log.info("Upserted %d rows. Done.", count)
        else:
            ingest(conn, args.start, args.end)
            log.info("Done.")
    finally:
        conn.close()
