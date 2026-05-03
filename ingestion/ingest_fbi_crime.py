"""
Ingests FBI UCR/NIBRS crime data at county level from the Kaplan Return A dataset.

Data source: Jacob Kaplan's "Offenses Known and Clearances by Arrest (Return A), 1960-2024"
  https://www.openicpsr.org/openicpsr/project/100707/version/V22/view
  Free openICPSR account required. Download the yearly summary CSV (not the monthly file).

Accepts .csv or .csv.gz. All years in the file are loaded unless --start/--end is given.

Usage:
  python ingest_fbi_crime.py --file /path/to/offenses_known_yearly_1960_2024.csv
  python ingest_fbi_crime.py --file /path/to/data.csv.gz --start 2019
"""

import argparse
import csv
import gzip
import logging
import os
from collections import defaultdict

import psycopg2
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../config/.env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# Column name variants across Kaplan dataset versions
_MURDER_COLS  = ("actual_murder_manslaughter", "actual_murder")
_RAPE_COLS    = ("actual_rape_total", "actual_rape_legacy", "actual_rape")
_ROBBERY_COLS = ("actual_robbery_total", "actual_robbery")
_ASSAULT_COLS = ("actual_assault_aggravated",)
_BURG_COLS    = ("actual_burg_total", "actual_burglary_total")
_THEFT_COLS   = ("actual_theft_total", "actual_larceny_total")
_MVT_COLS     = ("actual_mtr_veh_theft_total", "actual_motor_vehicle_theft_total")
_FIPS_COLS    = ("fips_state_county_code", "county_fips", "fips")
_POP_COLS     = ("population",)
_YEAR_COLS    = ("year",)

_REQUIRED_GROUPS = ("year", "fips", "murder", "rape", "robbery", "assault", "burg", "theft", "mvt")


def _first_col(header: list[str], candidates: tuple[str, ...]) -> str | None:
    lower = [c.lower() for c in header]
    for c in candidates:
        if c.lower() in lower:
            return header[lower.index(c.lower())]
    return None


def _int_val(val: str) -> int | None:
    """Parse int; treat empty or negative sentinel (-1) as None."""
    v = val.strip().replace(",", "")
    if not v:
        return None
    try:
        n = int(float(v))
        return None if n < 0 else n
    except (ValueError, TypeError):
        return None


def parse_return_a_csv(
    path: str,
    start_year: int | None = None,
    end_year: int | None = None,
) -> dict[tuple[str, int], dict]:
    """
    Parse Kaplan Return A yearly summary CSV.
    Returns {(fips5, year): {population_covered, violent_crimes, violent_crime_rate,
                              property_crimes, property_crime_rate}}.
    """
    opener = gzip.open if path.endswith(".gz") else open

    accum: dict[tuple[str, int], dict] = defaultdict(
        lambda: {"population": 0, "violent": 0, "property": 0}
    )

    with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])

        col = {
            "year":    _first_col(header, _YEAR_COLS),
            "fips":    _first_col(header, _FIPS_COLS),
            "pop":     _first_col(header, _POP_COLS),
            "murder":  _first_col(header, _MURDER_COLS),
            "rape":    _first_col(header, _RAPE_COLS),
            "robbery": _first_col(header, _ROBBERY_COLS),
            "assault": _first_col(header, _ASSAULT_COLS),
            "burg":    _first_col(header, _BURG_COLS),
            "theft":   _first_col(header, _THEFT_COLS),
            "mvt":     _first_col(header, _MVT_COLS),
        }

        missing = [k for k in _REQUIRED_GROUPS if col[k] is None]
        if missing:
            raise ValueError(
                f"Required columns not found in CSV: {missing}. "
                f"First 20 headers: {header[:20]}"
            )

        for row in reader:
            try:
                year = int(row[col["year"]])
            except (ValueError, TypeError):
                continue
            if start_year and year < start_year:
                continue
            if end_year and year > end_year:
                continue

            raw_fips = row.get(col["fips"], "").strip()
            if not raw_fips:
                continue
            fips = raw_fips.zfill(5)
            if not fips.isdigit() or len(fips) != 5:
                continue

            murder  = _int_val(row.get(col["murder"],  "")) or 0
            rape    = _int_val(row.get(col["rape"],    "")) or 0
            robbery = _int_val(row.get(col["robbery"], "")) or 0
            assault = _int_val(row.get(col["assault"], "")) or 0
            burg    = _int_val(row.get(col["burg"],    "")) or 0
            theft   = _int_val(row.get(col["theft"],   "")) or 0
            mvt     = _int_val(row.get(col["mvt"],     "")) or 0
            pop     = _int_val(row.get(col["pop"] or "", "")) or 0

            key = (fips, year)
            accum[key]["violent"]  += murder + rape + robbery + assault
            accum[key]["property"] += burg + theft + mvt
            accum[key]["population"] += pop

    records: dict[tuple[str, int], dict] = {}
    for (fips, year), t in accum.items():
        pop, viol, prop = t["population"], t["violent"], t["property"]
        records[(fips, year)] = {
            "population_covered":  pop or None,
            "violent_crimes":      viol or None,
            "violent_crime_rate":  round(viol / pop * 100_000, 1) if pop else None,
            "property_crimes":     prop or None,
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
            cur.execute(sql, {"fips": fips, "year": year, **data})
            count += cur.rowcount
    conn.commit()
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file", required=True,
        help="Path to Kaplan Return A yearly CSV (.csv or .csv.gz). "
             "Download from: https://www.openicpsr.org/openicpsr/project/100707/version/V22/view",
    )
    parser.add_argument("--start", type=int, help="First year to ingest (default: all years in file)")
    parser.add_argument("--end",   type=int, help="Last year to ingest (default: all years in file)")
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT fips FROM geo_entities WHERE geo_type = 'county'")
            known_fips = {r[0] for r in cur.fetchall()}

        log.info("Parsing %s ...", args.file)
        records = parse_return_a_csv(args.file, args.start, args.end)
        years = sorted({y for _, y in records})
        log.info(
            "Parsed %d county-year records spanning %d–%d",
            len(records), min(years), max(years),
        )

        count = upsert(conn, records, known_fips)
        log.info("Upserted %d rows. Done.", count)
    finally:
        conn.close()
