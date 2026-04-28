"""
Ingests EPA Air Quality Index (AQI) data at county level.

Source: EPA AQS Annual AQI by County flat files
URL pattern: https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_county_{year}.zip

CSV columns inside each zip:
  State, County, Year, Days with AQI, Good Days, Moderate Days,
  Unhealthy for Sensitive Groups Days, Unhealthy Days, Very Unhealthy Days,
  Hazardous Days, Max AQI, 90th Percentile AQI, Median AQI,
  Days CO, Days NO2, Days Ozone, Days PM2.5, Days PM10

County rows are matched to geo_entities FIPS codes by (state_name, county_name).

Usage:
  python ingest_epa_aqi.py [--start 2018] [--end 2023]
  python ingest_epa_aqi.py --file /path/to/annual_aqi_by_county_2023.csv --year 2023
"""

import argparse
import csv
import io
import logging
import os
import zipfile

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
    "https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_county_{year}.zip"
)

# State name → 2-digit FIPS code
US_STATE_FIPS: dict[str, str] = {
    "Alabama": "01", "Alaska": "02", "Arizona": "04", "Arkansas": "05",
    "California": "06", "Colorado": "08", "Connecticut": "09", "Delaware": "10",
    "District Of Columbia": "11", "District of Columbia": "11",
    "Florida": "12", "Georgia": "13", "Hawaii": "15", "Idaho": "16",
    "Illinois": "17", "Indiana": "18", "Iowa": "19", "Kansas": "20",
    "Kentucky": "21", "Louisiana": "22", "Maine": "23", "Maryland": "24",
    "Massachusetts": "25", "Michigan": "26", "Minnesota": "27", "Mississippi": "28",
    "Missouri": "29", "Montana": "30", "Nebraska": "31", "Nevada": "32",
    "New Hampshire": "33", "New Jersey": "34", "New Mexico": "35", "New York": "36",
    "North Carolina": "37", "North Dakota": "38", "Ohio": "39", "Oklahoma": "40",
    "Oregon": "41", "Pennsylvania": "42", "Rhode Island": "44", "South Carolina": "45",
    "South Dakota": "46", "Tennessee": "47", "Texas": "48", "Utah": "49",
    "Vermont": "50", "Virginia": "51", "Washington": "53", "West Virginia": "54",
    "Wisconsin": "55", "Wyoming": "56",
    "Puerto Rico": "72", "Virgin Islands": "78",
}

_COUNTY_SUFFIXES = (
    " city and borough", " census area", " borough", " municipality",
    " parish", " county", " city",
)


def normalize_county(name: str) -> str:
    n = name.lower().strip()
    for suffix in _COUNTY_SUFFIXES:
        if n.endswith(suffix):
            return n[: -len(suffix)].strip()
    return n


def build_geo_lookup(conn) -> dict[tuple[str, str], str]:
    """Return {(state_fips, normalized_county_name): fips} from geo_entities."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT fips, state_fips, name FROM geo_entities WHERE geo_type = 'county'"
        )
        rows = cur.fetchall()
    lookup: dict[tuple[str, str], str] = {}
    for fips, state_fips, name in rows:
        county_part = name.split(",")[0].strip()
        normalized = normalize_county(county_part)
        lookup[(state_fips, normalized)] = fips
    return lookup


def _int_or_none(value: str) -> int | None:
    v = value.strip()
    if not v:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _float_or_none(value: str) -> float | None:
    v = value.strip()
    if not v:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def parse_aqi_csv(content: bytes | str) -> list[dict]:
    """Parse the EPA annual_aqi_by_county CSV and return a list of row dicts."""
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
    else:
        text = content

    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        try:
            year = int(row["Year"].strip())
        except (KeyError, ValueError):
            continue
        rows.append({
            "state":                   row.get("State", "").strip(),
            "county":                  row.get("County", "").strip(),
            "year":                    year,
            "days_with_aqi":           _int_or_none(row.get("Days with AQI", "")),
            "good_days":               _int_or_none(row.get("Good Days", "")),
            "moderate_days":           _int_or_none(row.get("Moderate Days", "")),
            "unhealthy_sensitive_days": _int_or_none(
                row.get("Unhealthy for Sensitive Groups Days", "")
            ),
            "unhealthy_days":          _int_or_none(row.get("Unhealthy Days", "")),
            "very_unhealthy_days":     _int_or_none(row.get("Very Unhealthy Days", "")),
            "hazardous_days":          _int_or_none(row.get("Hazardous Days", "")),
            "max_aqi":                 _int_or_none(row.get("Max AQI", "")),
            "median_aqi":              _float_or_none(row.get("Median AQI", "")),
            "pm25_days":               _int_or_none(row.get("Days PM2.5", "")),
            "ozone_days":              _int_or_none(row.get("Days Ozone", "")),
        })
    return rows


def match_to_fips(
    rows: list[dict],
    geo_lookup: dict[tuple[str, str], str],
) -> dict[tuple[str, int], dict]:
    """Map parsed CSV rows to {(fips, year): metrics} using geo lookup."""
    records: dict[tuple[str, int], dict] = {}
    unmatched = 0
    for row in rows:
        state_fips = US_STATE_FIPS.get(row["state"])
        if not state_fips:
            unmatched += 1
            continue
        normalized = normalize_county(row["county"])
        fips = geo_lookup.get((state_fips, normalized))
        if not fips:
            unmatched += 1
            continue
        metrics = {k: v for k, v in row.items() if k not in ("state", "county", "year")}
        records[(fips, row["year"])] = metrics
    if unmatched:
        log.warning("Could not match %d rows to a known county FIPS", unmatched)
    return records


def upsert(conn, records: dict[tuple[str, int], dict]) -> int:
    sql = """
        INSERT INTO epa_aqi
            (fips, year, days_with_aqi, good_days, moderate_days,
             unhealthy_sensitive_days, unhealthy_days, very_unhealthy_days,
             hazardous_days, max_aqi, median_aqi, pm25_days, ozone_days)
        VALUES
            (%(fips)s, %(year)s, %(days_with_aqi)s, %(good_days)s, %(moderate_days)s,
             %(unhealthy_sensitive_days)s, %(unhealthy_days)s, %(very_unhealthy_days)s,
             %(hazardous_days)s, %(max_aqi)s, %(median_aqi)s, %(pm25_days)s, %(ozone_days)s)
        ON CONFLICT (fips, year) DO UPDATE SET
            days_with_aqi            = EXCLUDED.days_with_aqi,
            good_days                = EXCLUDED.good_days,
            moderate_days            = EXCLUDED.moderate_days,
            unhealthy_sensitive_days = EXCLUDED.unhealthy_sensitive_days,
            unhealthy_days           = EXCLUDED.unhealthy_days,
            very_unhealthy_days      = EXCLUDED.very_unhealthy_days,
            hazardous_days           = EXCLUDED.hazardous_days,
            max_aqi                  = EXCLUDED.max_aqi,
            median_aqi               = EXCLUDED.median_aqi,
            pm25_days                = EXCLUDED.pm25_days,
            ozone_days               = EXCLUDED.ozone_days,
            fetched_at               = NOW()
    """
    count = 0
    with conn.cursor() as cur:
        for (fips, year), data in records.items():
            row = {"fips": fips, "year": year, **data}
            cur.execute(sql, row)
            count += cur.rowcount
    conn.commit()
    return count


def ingest(conn, start: int, end: int) -> int:
    geo_lookup = build_geo_lookup(conn)
    log.info("Loaded geo lookup with %d county entries", len(geo_lookup))
    total = 0
    for year in range(start, end + 1):
        url = FLAT_FILE_URL_TPL.format(year=year)
        log.info("Downloading EPA AQI flat file for %d: %s", year, url)
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
            csv_bytes = zf.read(csv_name)
        rows = parse_aqi_csv(csv_bytes)
        log.info("Parsed %d rows from %s", len(rows), csv_name)
        records = match_to_fips(rows, geo_lookup)
        log.info("Matched %d county-year records for %d", len(records), year)
        count = upsert(conn, records)
        log.info("Upserted %d rows for %d", count, year)
        total += count
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2018)
    parser.add_argument("--end",   type=int, default=2023)
    parser.add_argument("--file",  help="Path to a local annual_aqi_by_county CSV")
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
            geo_lookup = build_geo_lookup(conn)
            with open(args.file, "rb") as fh:
                rows = parse_aqi_csv(fh.read())
            records = match_to_fips(rows, geo_lookup)
            log.info("Matched %d county-year records", len(records))
            count = upsert(conn, records)
            log.info("Upserted %d rows. Done.", count)
        else:
            ingest(conn, args.start, args.end)
            log.info("Done.")
    finally:
        conn.close()
