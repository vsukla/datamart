"""
Ingest Department of Education 4-year Adjusted Cohort Graduation Rates (ACGR)
at the county level.

Source: EDFacts ACGR LEA-level CSV files (U.S. Dept of Education)
Crosswalk: Urban Institute Education Data API (school directory → LEAID→county)

Process:
  1. Build LEAID→county_fips crosswalk from Urban Institute school directory API
  2. Download EDFacts ACGR long-format CSV for each school year
  3. Parse rows with CATEGORY=ALL and CATEGORY=ECD, skip suppressed/range rates
  4. Aggregate to county: cohort-weighted mean graduation rate per county per year
  5. Upsert into ed_graduation

Usage:
  python ingest_ed_graduation.py [--years 2019 2020 2021]
"""

import argparse
import csv
import io
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

# school_year (ending year) → URL of long-format EDFacts ACGR CSV
ACGR_URLS: dict[int, str] = {
    2019: "https://www.ed.gov/sites/ed/files/about/inits/ed/edfacts/data-files/acgr-lea-sy2018-19-long.csv",
    2020: "https://www.ed.gov/sites/ed/files/about/inits/ed/edfacts/data-files/acgr-lea-sy2019-20-long.csv",
    2021: "https://www.ed.gov/sites/ed/files/about/inits/ed/edfacts/data-files/acgr-lea-sy2020-21-long.csv",
}
DEFAULT_YEARS = list(ACGR_URLS.keys())

# Urban Institute Education Data API — school directory with leaid + county_code
URBAN_DIRECTORY_URL = "https://educationdata.urban.org/api/v1/schools/ccd/directory/{year}/"

# Crosswalk base year — use the most recent available CCD directory year
CROSSWALK_YEAR = 2021

# State FIPS codes (for fetching crosswalk by state to keep pages manageable)
_STATE_FIPS = [
    "01","02","04","05","06","08","09","10","11","12","13","15","16","17","18",
    "19","20","21","22","23","24","25","26","27","28","29","30","31","32","33",
    "34","35","36","37","38","39","40","41","42","44","45","46","47","48","49",
    "50","51","53","54","55","56",
]


def build_crosswalk(session: requests.Session) -> dict[str, str]:
    """Return {leaid: county_fips} from Urban Institute school directory.

    Fetches one state at a time to stay within per_page limits.
    Assigns each LEAID to its most common county across all schools.
    """
    crosswalk: dict[str, str] = {}
    county_votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for state_fips in _STATE_FIPS:
        url = URBAN_DIRECTORY_URL.format(year=CROSSWALK_YEAR)
        params = {"fips": int(state_fips), "per_page": 10000}
        page = 1
        total_schools = 0

        while url:
            try:
                resp = session.get(url, params=params, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as exc:
                log.warning("Crosswalk: state %s page %d failed — %s", state_fips, page, exc)
                break

            data = resp.json()
            for rec in data.get("results", []):
                leaid = str(rec.get("leaid") or "").strip()
                county_code = rec.get("county_code")
                if not leaid or county_code is None:
                    continue
                county_fips = str(int(county_code)).zfill(5)
                county_votes[leaid][county_fips] += 1
                total_schools += 1

            url = data.get("next")
            params = {}   # next URL already includes params
            page += 1
            if url:
                time.sleep(0.1)

        log.info("  Crosswalk state %s: %d schools fetched", state_fips, total_schools)
        time.sleep(0.2)

    # Resolve each LEAID to its majority county
    for leaid, votes in county_votes.items():
        crosswalk[leaid] = max(votes, key=votes.__getitem__)

    log.info("Crosswalk built: %d districts mapped to counties", len(crosswalk))
    return crosswalk


def _parse_rate(rate_str: str) -> float | None:
    """Parse EDFacts RATE value to float.

    Handles exact values ("82"), ranges ("80-85" → midpoint 82.5),
    and returns None for fully suppressed values ("PS", "GE50", etc.).
    """
    s = rate_str.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    if "-" in s:
        parts = s.split("-", 1)
        try:
            lo, hi = float(parts[0]), float(parts[1])
            return (lo + hi) / 2
        except ValueError:
            pass
    return None


def download_acgr(session: requests.Session, year: int) -> str:
    url = ACGR_URLS[year]
    log.info("Downloading EDFacts ACGR %d from %s ...", year, url)
    resp = session.get(url, timeout=120)
    resp.raise_for_status()
    return resp.text


def parse_acgr(
    csv_text: str,
    school_year: int,
    crosswalk: dict[str, str],
    known_fips: set[str],
) -> list[dict]:
    """Parse long-format ACGR CSV and aggregate to county level.

    Returns list of dicts ready for upsert into ed_graduation.
    Only ALL and ECD categories are used.
    Rates that are suppressed (non-numeric) are excluded from weighted mean
    but their cohorts still count toward num_districts.
    """
    # Accumulators per (county_fips, school_year):
    #   rate_sum_all, cohort_sum_all, cohort_all_total, count_districts
    #   rate_sum_ecd, cohort_sum_ecd
    acc: dict[str, dict] = {}

    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        leaid = str(row.get("LEAID", "")).strip()
        category = str(row.get("CATEGORY", "")).strip()
        if category not in ("ALL", "ECD"):
            continue

        county_fips = crosswalk.get(leaid)
        if not county_fips or county_fips not in known_fips:
            continue

        key = county_fips
        if key not in acc:
            acc[key] = {
                "rate_sum_all": 0.0, "cohort_rate_all": 0,
                "cohort_all": 0,
                "rate_sum_ecd": 0.0, "cohort_rate_ecd": 0,
                "leaids": set(),
            }

        try:
            cohort = int(str(row.get("COHORT", "0")).strip())
        except ValueError:
            cohort = 0

        rate = _parse_rate(str(row.get("RATE", "")))

        acc[key]["leaids"].add(leaid)

        if category == "ALL":
            acc[key]["cohort_all"] += cohort
            if rate is not None and cohort > 0:
                acc[key]["rate_sum_all"] += rate * cohort
                acc[key]["cohort_rate_all"] += cohort
        else:  # ECD
            if rate is not None and cohort > 0:
                acc[key]["rate_sum_ecd"] += rate * cohort
                acc[key]["cohort_rate_ecd"] += cohort

    records = []
    for county_fips, a in acc.items():
        grad_rate_all = (
            round(a["rate_sum_all"] / a["cohort_rate_all"], 1)
            if a["cohort_rate_all"] > 0 else None
        )
        grad_rate_ecd = (
            round(a["rate_sum_ecd"] / a["cohort_rate_ecd"], 1)
            if a["cohort_rate_ecd"] > 0 else None
        )
        records.append({
            "fips":         county_fips,
            "school_year":  school_year,
            "grad_rate_all": grad_rate_all,
            "grad_rate_ecd": grad_rate_ecd,
            "cohort_all":   a["cohort_all"] if a["cohort_all"] > 0 else None,
            "num_districts": len(a["leaids"]),
        })

    return records


def upsert(conn, records: list[dict]) -> int:
    sql = """
        INSERT INTO ed_graduation
            (fips, school_year, grad_rate_all, grad_rate_ecd, cohort_all, num_districts)
        VALUES
            (%(fips)s, %(school_year)s, %(grad_rate_all)s, %(grad_rate_ecd)s,
             %(cohort_all)s, %(num_districts)s)
        ON CONFLICT (fips, school_year) DO UPDATE SET
            grad_rate_all  = EXCLUDED.grad_rate_all,
            grad_rate_ecd  = EXCLUDED.grad_rate_ecd,
            cohort_all     = EXCLUDED.cohort_all,
            num_districts  = EXCLUDED.num_districts,
            fetched_at     = NOW()
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
            "SELECT fips, school_year FROM ed_graduation WHERE school_year = ANY(%s)",
            (years,),
        )
        return {(r[0], r[1]) for r in cur.fetchall()}


def _load_known_fips(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT fips FROM geo_entities WHERE geo_type = 'county'")
        return {r[0] for r in cur.fetchall()}


def ingest(conn, years: list[int] | None = None, force: bool = False) -> int:
    if years is None:
        years = DEFAULT_YEARS

    if force:
        years_todo = years
    else:
        already = get_already_ingested(conn, years)
        years_todo = [y for y in years if not any(y == pair[1] for pair in already)]
        if not years_todo:
            log.info("All requested years already ingested — skipping.")
            return 0

    known_fips = _load_known_fips(conn)
    log.info("Building LEAID→county crosswalk from Urban Institute API...")
    session = requests.Session()
    session.headers["User-Agent"] = "datamart-ingestion/1.0"
    crosswalk = build_crosswalk(session)

    total = 0
    for year in years_todo:
        log.info("Processing school year ending %d...", year)
        csv_text = download_acgr(session, year)
        records = parse_acgr(csv_text, year, crosswalk, known_fips)
        count = upsert(conn, records)
        log.info("  School year %d: %d counties upserted", year, count)
        total += count

    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, default=DEFAULT_YEARS)
    parser.add_argument("--force", action="store_true",
                        help="Re-ingest even if years already loaded")
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
    )
    try:
        total = ingest(conn, args.years, force=args.force)
        log.info("Total upserted: %d rows", total)
        log.info("Done.")
    finally:
        conn.close()
