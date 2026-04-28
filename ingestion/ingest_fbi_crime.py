"""
Ingests FBI UCR/NIBRS crime data at county level via the FBI Crime Data Explorer API.

The legacy flat-file URL (cde.ucr.cjis.gov/LATEST/webapp/assets/data/county_YEAR.zip)
no longer exists.  Data is now served through the CDE API.

API key: register free at https://api.data.gov/signup/
Set FBI_API_KEY in config/.env (or environment) before running.

Approach:
  1. Fetch all reporting agencies per state with county attribution.
  2. Fetch state-level annual offense totals, parsed per agency.
  3. Aggregate agency-level counts to county using the geo_entities lookup.

Usage:
  python ingest_fbi_crime.py [--start 2018] [--end 2022]
  python ingest_fbi_crime.py --file /path/to/county_crime.csv --year 2022
"""

import argparse
import csv
import io
import logging
import os
import time
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

CDE_BASE = "https://api.usa.gov/crime/fbi/cde"
RATE_LIMIT_DELAY = 0.15  # ~6-7 req/sec, well within 1000/hr default

STATE_ABBRS = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
]


def _get(url: str, params: dict, retries: int = 3) -> dict:
    delay = 1.0
    for attempt in range(1, retries + 1):
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", delay * 2))
            log.warning("Rate limited; sleeping %ds", wait)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "error" in data:
            code = data["error"].get("code", "")
            if code == "OVER_RATE_LIMIT":
                log.warning("Rate limit exceeded; sleeping 60s")
                time.sleep(60)
                continue
            raise RuntimeError(f"CDE API error: {data['error']}")
        return data
    raise RuntimeError(f"Failed after {retries} attempts: {url}")


def fetch_agency_county_map(state_abbr: str, api_key: str) -> dict[str, str]:
    """Returns {agency_name: county_name} for all agencies in a state."""
    url = f"{CDE_BASE}/agency/byStateAbbr/{state_abbr}"
    data = _get(url, {"API_KEY": api_key})
    # Response: {county_name: [{agency_name, ori, ...}, ...]}
    mapping: dict[str, str] = {}
    for county_name, agencies in data.items():
        for agency in agencies:
            name = agency.get("agency_name", "")
            if name:
                mapping[name] = county_name
    time.sleep(RATE_LIMIT_DELAY)
    return mapping


def fetch_state_offense_totals(
    state_abbr: str, offense_type: str, year: int, api_key: str
) -> dict[str, int]:
    """Returns {agency_name: annual_count} from the state summarized endpoint."""
    url = f"{CDE_BASE}/summarized/state/{state_abbr}/{offense_type}"
    data = _get(url, {
        "from": f"01-{year}",
        "to": f"12-{year}",
        "API_KEY": api_key,
    })
    actuals = data.get("offenses", {}).get("actuals", {})
    result: dict[str, int] = {}
    for key, monthly in actuals.items():
        if not key.endswith(" Offenses"):
            continue
        agency_name = key[: -len(" Offenses")]
        total = sum(v for v in monthly.values() if isinstance(v, (int, float)))
        result[agency_name] = int(total)
    time.sleep(RATE_LIMIT_DELAY)
    return result


def build_county_totals(
    agency_county_map: dict[str, str],
    violent_by_agency: dict[str, int],
    property_by_agency: dict[str, int],
    state_abbr: str,
) -> dict[tuple[str, str], dict]:
    """Returns {(state_abbr, county_name): {violent, property}}."""
    totals: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"violent": 0, "property": 0}
    )
    for agency_name, count in violent_by_agency.items():
        county = agency_county_map.get(agency_name)
        if county:
            totals[(state_abbr, county)]["violent"] += count
    for agency_name, count in property_by_agency.items():
        county = agency_county_map.get(agency_name)
        if county:
            totals[(state_abbr, county)]["property"] += count
    return dict(totals)


def _int_or_none(value: str) -> int | None:
    v = value.strip().replace(",", "")
    if not v:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def parse_crime_csv(content: bytes | str) -> dict[tuple[str, int], dict]:
    """Parse legacy FBI county crime CSV (used with --file option)."""
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
    else:
        text = content

    accum: dict[tuple[str, int], dict] = defaultdict(
        lambda: {"population": 0, "violent": 0, "property": 0}
    )
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        state_code = row.get("State Code", "").strip().zfill(2)
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
    for (fips, year), t in accum.items():
        pop, viol, prop = t["population"], t["violent"], t["property"]
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


def _build_county_fips_map(conn) -> tuple[set[str], dict[tuple[str, str], str]]:
    """
    Returns:
      known_fips: all county FIPS codes
      lookup: {(state_abbr_upper, county_name_upper): fips}
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT g.fips, g.name, s.name AS state_name "
            "FROM geo_entities g "
            "JOIN geo_entities s ON s.fips = g.state_fips AND s.geo_type = 'state' "
            "WHERE g.geo_type = 'county'"
        )
        rows = cur.fetchall()

    known_fips: set[str] = set()
    lookup: dict[tuple[str, str], str] = {}
    for fips, county_name, state_name in rows:
        known_fips.add(fips)
        state_abbr = _state_name_to_abbr(state_name)
        # county_name in geo_entities is e.g. "Los Angeles County, California"
        base = county_name.split(",")[0].strip().upper()
        lookup[(state_abbr, base)] = fips
        # Also store without "County"/"Parish"/etc. suffix for looser matching
        stripped = base.replace(" COUNTY", "").replace(" PARISH", "").replace(" BOROUGH", "").strip()
        lookup.setdefault((state_abbr, stripped), fips)
    return known_fips, lookup


def ingest_api(conn, start: int, end: int, api_key: str) -> int:
    """Ingest FBI crime data via the CDE API for all counties."""
    known_fips, county_fips_map = _build_county_fips_map(conn)

    total = 0
    for state_abbr in STATE_ABBRS:
        log.info("Fetching agencies for %s", state_abbr)
        try:
            agency_county_map = fetch_agency_county_map(state_abbr, api_key)
        except Exception as exc:
            log.warning("Skipping %s agency fetch: %s", state_abbr, exc)
            continue

        for year in range(start, end + 1):
            log.info("Fetching %s crime data for %d", state_abbr, year)
            try:
                violent = fetch_state_offense_totals(state_abbr, "violent-crime", year, api_key)
                property_c = fetch_state_offense_totals(state_abbr, "property-crime", year, api_key)
            except Exception as exc:
                log.warning("Skipping %s/%d: %s", state_abbr, year, exc)
                continue

            if not violent and not property_c:
                log.info("  No per-agency data for %s/%d (state aggregate only)", state_abbr, year)
                continue

            # Aggregate agency-level counts to county
            county_totals: dict[str, dict] = defaultdict(lambda: {"violent": 0, "property": 0})
            for agency_name, count in violent.items():
                county = agency_county_map.get(agency_name, "")
                fips = _resolve_county_fips(state_abbr, county, county_fips_map)
                if fips:
                    county_totals[fips]["violent"] += count
            for agency_name, count in property_c.items():
                county = agency_county_map.get(agency_name, "")
                fips = _resolve_county_fips(state_abbr, county, county_fips_map)
                if fips:
                    county_totals[fips]["property"] += count

            records: dict[tuple[str, int], dict] = {}
            for fips, t in county_totals.items():
                records[(fips, year)] = {
                    "population_covered": None,
                    "violent_crimes":     t["violent"] or None,
                    "violent_crime_rate": None,
                    "property_crimes":    t["property"] or None,
                    "property_crime_rate": None,
                }

            count = upsert(conn, records, known_fips)
            log.info("  Upserted %d rows for %s/%d", count, state_abbr, year)
            total += count

    return total


def _resolve_county_fips(state_abbr: str, county_name: str, lookup: dict) -> str | None:
    key = (state_abbr, county_name.upper())
    fips = lookup.get(key)
    if fips:
        return fips
    stripped = county_name.upper().replace(" COUNTY", "").replace(" PARISH", "").replace(" BOROUGH", "").strip()
    return lookup.get((state_abbr, stripped))


_STATE_ABBR_TO_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


_STATE_NAME_TO_ABBR = {v.upper(): k for k, v in _STATE_ABBR_TO_NAME.items()}


def _state_name_to_abbr(name: str) -> str:
    return _STATE_NAME_TO_ABBR.get(name.upper(), name[:2].upper())


def ingest(conn, start: int, end: int, api_key: str | None = None) -> int:
    if api_key:
        return ingest_api(conn, start, end, api_key)
    raise RuntimeError(
        "FBI_API_KEY not set. Register free at https://api.data.gov/signup/ "
        "and add FBI_API_KEY to config/.env"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2018)
    parser.add_argument("--end",   type=int, default=2022)
    parser.add_argument("--file",  help="Path to a local county crime CSV (legacy format)")
    parser.add_argument("--year",  type=int, help="Year for --file mode (required with --file)")
    args = parser.parse_args()

    api_key = os.environ.get("FBI_API_KEY")

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
            if not api_key:
                raise SystemExit(
                    "ERROR: FBI_API_KEY not set.\n"
                    "Register free at https://api.data.gov/signup/ "
                    "and add FBI_API_KEY=your_key to config/.env"
                )
            ingest(conn, args.start, args.end, api_key)
            log.info("Done.")
    finally:
        conn.close()
