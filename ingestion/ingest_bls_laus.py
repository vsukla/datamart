"""
Ingests BLS Local Area Unemployment Statistics (LAUS) at county level.

Source: BLS Public Data API v2
  https://api.bls.gov/publicAPI/v2/timeseries/data/

Series ID format:  LAUCN{2-digit-state}{3-digit-county}0000000{measure}
Measure codes:
  03 = unemployment rate (%)
  04 = unemployed (count)
  05 = employed (count)
  06 = labor force (count)

Free registration for an API key (higher rate limits) at:
  https://data.bls.gov/registrationEngine/registerUser.action

Set BLS_API_KEY in config/.env for 500 series/request (vs 25 without a key).

Usage:
  python ingest_bls_laus.py [--start 2018] [--end 2022]
  python ingest_bls_laus.py --file /path/to/laucnty23.txt --year 2023
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

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
MEASURES = {
    "06": "labor_force",
    "05": "employed",
    "04": "unemployed",
    "03": "unemployment_rate",
}
BATCH_SIZE_KEYED   = 50   # BLS API returns at most 50 series per request in practice
BATCH_SIZE_NOKEY   = 25
RETRY_DELAY        = 5   # seconds on HTTP error


def _series_id(fips: str, measure: str) -> str:
    """Build a LAUS series ID from a 5-digit county FIPS and 2-digit measure code."""
    return f"LAUCN{fips}00000000{measure}"


def _fetch_series_batch(
    series_ids: list[str],
    start_year: int,
    end_year: int,
    api_key: str | None,
) -> dict[str, list[dict]]:
    """
    POST to BLS API v2 for a batch of series IDs.
    Returns {series_id: [{year: ..., value: ...}, ...]} for annual averages.
    """
    payload: dict = {
        "seriesid":     series_ids,
        "startyear":    str(start_year),
        "endyear":      str(end_year),
        "annualaverage": True,
    }
    if api_key:
        payload["registrationkey"] = api_key

    for attempt in range(1, 4):
        resp = requests.post(BLS_API_URL, json=payload, timeout=60)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            log.warning("Rate limited; sleeping %ds", wait)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") == "REQUEST_SUCCEEDED":
            # Prefer official M13 annual average; fall back to mean of M01–M12.
            # Not all county series publish M13 even with annualaverage=True.
            out: dict[str, list[dict]] = {}
            for series in result.get("Results", {}).get("series", []):
                sid = series["seriesID"]
                data = series.get("data", [])

                # Group monthly values by year
                by_year: dict[int, list[float]] = {}
                m13_by_year: dict[int, float] = {}
                for d in data:
                    val_str = d.get("value", "-")
                    if val_str in ("-", ""):
                        continue
                    yr = int(d["year"])
                    period = d.get("period", "")
                    try:
                        val = float(val_str)
                    except (ValueError, TypeError):
                        continue
                    if period == "M13":
                        m13_by_year[yr] = val
                    elif period.startswith("M") and period[1:].isdigit():
                        by_year.setdefault(yr, []).append(val)

                annual: list[dict] = []
                all_years = set(m13_by_year) | set(by_year)
                for yr in sorted(all_years):
                    if yr in m13_by_year:
                        annual.append({"year": yr, "value": m13_by_year[yr]})
                    elif by_year.get(yr):
                        avg = round(sum(by_year[yr]) / len(by_year[yr]), 1)
                        annual.append({"year": yr, "value": avg})
                out[sid] = annual
            return out
        msg = " ".join(result.get("message", []))
        if "threshold" in msg.lower() or "limit" in msg.lower():
            raise RuntimeError(
                "BLS API daily request limit reached. Register a free key at "
                "https://data.bls.gov/registrationEngine/registerUser.action "
                "and add BLS_API_KEY to config/.env"
            )
        raise RuntimeError(f"BLS API error: {msg}")
    raise RuntimeError("BLS API failed after 3 attempts")


def fetch_all_county_laus(
    county_fips_list: list[str],
    start_year: int,
    end_year: int,
    api_key: str | None,
) -> dict[tuple[str, int], dict]:
    """
    Fetch LAUS data for all counties across all years.
    Returns {(fips, year): {labor_force, employed, unemployed, unemployment_rate}}.
    """
    batch_size = BATCH_SIZE_KEYED if api_key else BATCH_SIZE_NOKEY

    # Build all series IDs
    all_series: list[str] = [
        _series_id(fips, measure)
        for fips in county_fips_list
        for measure in MEASURES
    ]

    # Group by county so all 4 measures for a county stay together
    county_series: dict[str, list[str]] = {
        fips: [_series_id(fips, m) for m in MEASURES]
        for fips in county_fips_list
    }

    # Process in batches of series IDs
    series_data: dict[str, list[dict]] = {}
    batches = [all_series[i: i + batch_size] for i in range(0, len(all_series), batch_size)]
    for i, batch in enumerate(batches):
        log.info("Fetching batch %d/%d (%d series)", i + 1, len(batches), len(batch))
        series_data.update(_fetch_series_batch(batch, start_year, end_year, api_key))
        if i < len(batches) - 1:
            time.sleep(0.5)  # small delay between batches

    # Pivot: {(fips, year): {measure: value}}
    records: dict[tuple[str, int], dict] = {}
    for fips, sid_list in county_series.items():
        year_data: dict[int, dict] = {}
        for sid in sid_list:
            measure_code = sid[-2:]
            col = MEASURES[measure_code]
            for entry in series_data.get(sid, []):
                yr = entry["year"]
                if yr not in year_data:
                    year_data[yr] = {}
                year_data[yr][col] = entry["value"]
        for yr, values in year_data.items():
            records[(fips, yr)] = {
                "labor_force":       int(values["labor_force"])  if "labor_force"  in values else None,
                "employed":          int(values["employed"])     if "employed"     in values else None,
                "unemployed":        int(values["unemployed"])   if "unemployed"   in values else None,
                "unemployment_rate": values.get("unemployment_rate"),
            }
    return records


def parse_flat_file(content: bytes | str) -> dict[tuple[str, int], dict]:
    """Parse a legacy BLS LAUS county txt flat file into {(fips, year): {col: value}}."""
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
    else:
        text = content

    _COL_STATE  = 1
    _COL_COUNTY = 2
    _COL_YEAR   = 4
    _COL_LF     = 6
    _COL_EMP    = 7
    _COL_UNEMP  = 8
    _COL_RATE   = 9

    def _num(s: str) -> str:
        return s.strip().replace(",", "")

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


def ingest(conn, start: int, end: int, api_key: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT fips FROM geo_entities WHERE geo_type = 'county'")
        county_fips = [r[0] for r in cur.fetchall()]

    log.info("Fetching BLS LAUS for %d counties, years %d–%d", len(county_fips), start, end)
    records = fetch_all_county_laus(county_fips, start, end, api_key)
    log.info("Parsed %d county-year records", len(records))
    count = upsert(conn, records)
    log.info("Upserted %d rows", count)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2018)
    parser.add_argument("--end",   type=int, default=2022)
    parser.add_argument("--file",  help="Path to a local laucnty{YY}.txt file (legacy)")
    parser.add_argument("--year",  type=int, help="Year for --file mode (required with --file)")
    args = parser.parse_args()

    api_key = os.environ.get("BLS_API_KEY")

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
            if not api_key:
                log.warning(
                    "No BLS_API_KEY set — using unauthenticated API (25 series/request, "
                    "daily limit). Register a free key at "
                    "https://data.bls.gov/registrationEngine/registerUser.action "
                    "and add BLS_API_KEY=your_key to config/.env"
                )
            ingest(conn, args.start, args.end, api_key)
            log.info("Done.")
    finally:
        conn.close()
