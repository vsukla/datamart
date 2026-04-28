"""
Ingests BLS Local Area Unemployment Statistics (LAUS) at county level.

Source: BLS LAUS county annual flat files
URL pattern: https://www.bls.gov/lau/laucnty{YY}.txt  (2-digit year)

File format (tab-delimited after header rows):
  LAUS Code | State FIPS | County FIPS | Area Title | Year | Period |
  Labor Force | Employed | Unemployed | Unemployment Rate

County data rows start with "CN" followed by digits. This covers all ~3,200
counties in one download per year with no API rate limits.

Usage:
  python ingest_bls_laus.py [--start 2018] [--end 2023]
  python ingest_bls_laus.py --file /path/to/laucnty23.txt --year 2023
"""

import argparse
import logging
import os

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

FLAT_FILE_URL_TPL = "https://www.bls.gov/lau/laucnty{yy:02d}.txt"

# 0-based column indices in tab-delimited data rows
_COL_STATE  = 1   # 2-digit state FIPS
_COL_COUNTY = 2   # 3-digit county FIPS
_COL_YEAR   = 4
_COL_LF     = 6   # civilian labor force
_COL_EMP    = 7   # employed
_COL_UNEMP  = 8   # unemployed level
_COL_RATE   = 9   # unemployment rate (%)


def _num(s: str) -> str:
    return s.strip().replace(",", "")


def parse_flat_file(content: bytes | str) -> dict[tuple[str, int], dict]:
    """Parse a BLS LAUS county txt flat file into {(fips, year): {col: value}}."""
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
    else:
        text = content

    records: dict[tuple[str, int], dict] = {}
    for line in text.splitlines():
        if not line.startswith("CN"):
            continue
        parts = line.split("\t")
        if len(parts) < 10:
            continue
        try:
            fips = parts[_COL_STATE].strip().zfill(2) + parts[_COL_COUNTY].strip().zfill(3)
            year = int(parts[_COL_YEAR].strip())
            lf   = int(float(_num(parts[_COL_LF])))   if _num(parts[_COL_LF])   else None
            emp  = int(float(_num(parts[_COL_EMP])))  if _num(parts[_COL_EMP])  else None
            une  = int(float(_num(parts[_COL_UNEMP]))) if _num(parts[_COL_UNEMP]) else None
            rate = float(_num(parts[_COL_RATE]))        if _num(parts[_COL_RATE])  else None
        except (ValueError, IndexError):
            continue
        records[(fips, year)] = {
            "labor_force":       lf,
            "employed":          emp,
            "unemployed":        une,
            "unemployment_rate": rate,
        }
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
                "fips":               fips,
                "year":               year,
                "labor_force":        data.get("labor_force"),
                "employed":           data.get("employed"),
                "unemployed":         data.get("unemployed"),
                "unemployment_rate":  data.get("unemployment_rate"),
            }
            cur.execute(sql, row)
            count += cur.rowcount
    conn.commit()
    return count


def ingest(conn, start: int, end: int) -> int:
    total = 0
    for year in range(start, end + 1):
        url = FLAT_FILE_URL_TPL.format(yy=year % 100)
        log.info("Downloading BLS LAUS flat file for %d: %s", year, url)
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        records = parse_flat_file(resp.content)
        log.info("Parsed %d county records for %d", len(records), year)
        count = upsert(conn, records)
        log.info("Upserted %d rows for %d", count, year)
        total += count
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2018)
    parser.add_argument("--end",   type=int, default=2023)
    parser.add_argument("--file",  help="Path to a local laucnty{YY}.txt file")
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
            with open(args.file, "rb") as fh:
                records = parse_flat_file(fh.read())
            log.info("Parsed %d county records from %s", len(records), args.file)
            count = upsert(conn, records)
            log.info("Upserted %d rows. Done.", count)
        else:
            ingest(conn, args.start, args.end)
            log.info("Done.")
    finally:
        conn.close()
