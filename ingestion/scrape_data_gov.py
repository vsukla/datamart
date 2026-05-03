"""
Scrape the data.gov CKAN catalog via the GSA API, score each dataset,
and export the top-N as a Markdown table for review.

Usage:
    python ingestion/scrape_data_gov.py              # scrape + score + export top 200
    python ingestion/scrape_data_gov.py --score-only # re-score without re-scraping
    python ingestion/scrape_data_gov.py --export-only --top 500
    python ingestion/scrape_data_gov.py --start-offset 50000  # resume from offset

Environment:
    DATA_GOV_API_KEY  — GSA api.data.gov key (DEMO_KEY works but is rate-limited)
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD  — standard datamart DB config

API endpoint (post-2025 migration):
    https://api.gsa.gov/technology/datagov/v3/action/package_search
"""

import argparse
import csv
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / "config" / ".env")

log = logging.getLogger(__name__)

CKAN_URL = "https://api.gsa.gov/technology/datagov/v3/action/package_search"
BATCH_SIZE = 1000       # CKAN max rows per request
REQUEST_DELAY = 1.0     # seconds between requests (polite crawl)

# Org name suffixes / publisher keywords that indicate federal datasets
_FEDERAL_ORG_SUFFIXES = ("-gov",)
_FEDERAL_PUBLISHER_KEYWORDS = (
    "department of", "bureau of", "centers for disease control",
    "environmental protection", "national highway", "national institute",
    "national center", "federal reserve", "federal housing", "federal aviation",
    "federal communications", "food and drug", "internal revenue",
    "social security", "u.s. census", "bureau of labor", "bureau of economic",
    "office of", "administration",
)

# Tags / title keywords that suggest geographic/demographic content
_GEO_KEYWORDS = {
    "county", "counties", "state", "states", "census", "demographic",
    "population", "income", "poverty", "unemployment", "labor", "health",
    "housing", "education", "crime", "mortality", "environment",
    "geographic", "geography", "fips", "tract", "zip",
}

# Machine-readable formats
_GOOD_FORMATS = {"csv", "json", "xls", "xlsx", "xml", "api", "geojson", "tsv", "rdf"}
# Non-machine-readable formats
_BAD_FORMATS = {"pdf", "shapefile", "shp", "kmz", "kml", "docx", "doc", "pptx"}


# ---------------------------------------------------------------------------
# Scoring

def score_record(row: dict) -> int:
    """Score a data_gov_catalog row (already parsed from CKAN). Returns 0-100."""
    s = 0

    # Formats
    formats = {(f or "").lower() for f in (row.get("formats") or [])}
    if formats & _GOOD_FORMATS:
        s += 30
    elif formats and not (formats - _BAD_FORMATS):
        s -= 20   # only bad formats present

    # Federal publisher
    org = (row.get("org_name") or "").lower()
    pub = (row.get("publisher") or "").lower()
    if any(org.endswith(sfx) for sfx in _FEDERAL_ORG_SUFFIXES):
        s += 20
    elif any(kw in pub for kw in _FEDERAL_PUBLISHER_KEYWORDS):
        s += 15

    # Geographic / demographic keywords in tags + title
    tags = {(t or "").lower() for t in (row.get("tag_names") or [])}
    groups = {(g or "").lower() for g in (row.get("group_names") or [])}
    title_words = set((row.get("title") or "").lower().split())
    all_words = tags | groups | title_words
    if all_words & _GEO_KEYWORDS:
        s += 20

    # Actively maintained (periodicity declared)
    if row.get("periodicity"):
        s += 15

    # Recently updated (modified >= 2018)
    modified = row.get("modified_date")
    if modified and str(modified) >= "2018-01-01":
        s += 15

    # Non-public — significantly penalize
    if row.get("access_level") and row["access_level"] != "public":
        s -= 30

    return max(0, min(100, s))


# ---------------------------------------------------------------------------
# CKAN parsing

def _parse_record(r: dict) -> dict:
    """Extract the fields we care about from a raw CKAN package dict."""
    extras = {e["key"]: e["value"] for e in r.get("extras", [])}

    formats = list({
        (res.get("format") or "").strip()
        for res in r.get("resources", [])
        if res.get("format")
    })
    groups = [g["name"] for g in r.get("groups", [])]
    tags   = [t["name"] for t in r.get("tags", [])]

    modified_raw = extras.get("modified")
    modified_date = None
    if modified_raw:
        try:
            modified_date = date.fromisoformat(modified_raw[:10])
        except ValueError:
            pass

    metadata_modified = None
    if r.get("metadata_modified"):
        try:
            metadata_modified = datetime.fromisoformat(
                r["metadata_modified"].replace("Z", "+00:00")
            )
        except ValueError:
            pass

    return {
        "ckan_id":           r.get("id", ""),
        "name":              r.get("name", "")[:300],
        "title":             r.get("title", ""),
        "org_name":          (r.get("organization") or {}).get("name", ""),
        "publisher":         extras.get("publisher", ""),
        "formats":           formats,
        "group_names":       groups,
        "tag_names":         tags,
        "access_level":      extras.get("accessLevel", ""),
        "periodicity":       extras.get("accrualPeriodicity", ""),
        "modified_date":     modified_date,
        "has_spatial":       bool(extras.get("spatial")),
        "num_resources":     r.get("num_resources", 0),
        "metadata_modified": metadata_modified,
    }


# ---------------------------------------------------------------------------
# Database

def upsert_batch(conn, records: list[dict]) -> int:
    sql = """
        INSERT INTO data_gov_catalog
            (ckan_id, name, title, org_name, publisher, formats, group_names,
             tag_names, access_level, periodicity, modified_date, has_spatial,
             num_resources, metadata_modified, scraped_at)
        VALUES
            (%(ckan_id)s, %(name)s, %(title)s, %(org_name)s, %(publisher)s,
             %(formats)s, %(group_names)s, %(tag_names)s, %(access_level)s,
             %(periodicity)s, %(modified_date)s, %(has_spatial)s,
             %(num_resources)s, %(metadata_modified)s, NOW())
        ON CONFLICT (ckan_id) DO UPDATE SET
            title             = EXCLUDED.title,
            org_name          = EXCLUDED.org_name,
            publisher         = EXCLUDED.publisher,
            formats           = EXCLUDED.formats,
            group_names       = EXCLUDED.group_names,
            tag_names         = EXCLUDED.tag_names,
            access_level      = EXCLUDED.access_level,
            periodicity       = EXCLUDED.periodicity,
            modified_date     = EXCLUDED.modified_date,
            has_spatial       = EXCLUDED.has_spatial,
            num_resources     = EXCLUDED.num_resources,
            metadata_modified = EXCLUDED.metadata_modified,
            scraped_at        = NOW()
    """
    with conn.cursor() as cur:
        for rec in records:
            cur.execute(sql, rec)
    conn.commit()
    return len(records)


def run_score_pass(conn) -> int:
    """Score all rows in data_gov_catalog and write scores back."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, org_name, publisher, formats, group_names,
                   tag_names, title, periodicity, modified_date, access_level
            FROM data_gov_catalog
        """)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]

    updates = []
    for row in rows:
        record = dict(zip(cols, row))
        updates.append((score_record(record), record["id"]))

    with conn.cursor() as cur:
        cur.executemany("UPDATE data_gov_catalog SET score = %s WHERE id = %s", updates)
    conn.commit()
    log.info("Scored %d records.", len(updates))
    return len(updates)


# ---------------------------------------------------------------------------
# Scrape

def _get_with_retry(session, url, params, timeout, max_retries=5) -> requests.Response:
    """GET with exponential backoff on 429 / 5xx."""
    delay = 10
    for attempt in range(max_retries):
        resp = session.get(url, params=params, timeout=timeout)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", delay))
            log.warning("Rate limited (429). Waiting %ds before retry %d/%d.",
                        retry_after, attempt + 1, max_retries)
            time.sleep(retry_after)
            delay = min(delay * 2, 300)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"Exceeded {max_retries} retries due to rate limiting.")


def scrape(conn, api_key: str, start_offset: int = 0) -> int:
    session = requests.Session()
    session.headers["X-Api-Key"] = api_key
    total_fetched = 0
    offset = start_offset

    # Get total count first
    resp = _get_with_retry(session, CKAN_URL, {"rows": 0, "start": 0}, timeout=30)
    total = resp.json()["result"]["count"]
    log.info("Total datasets in catalog: %d. Starting at offset %d.", total, offset)

    while offset < total:
        resp = _get_with_retry(
            session, CKAN_URL,
            {"rows": BATCH_SIZE, "start": offset},
            timeout=60,
        )
        results = resp.json()["result"]["results"]
        if not results:
            break

        parsed = [_parse_record(r) for r in results]
        upsert_batch(conn, parsed)
        total_fetched += len(parsed)
        offset += len(results)

        log.info("Scraped %d / %d (%.1f%%)", offset, total, 100 * offset / total)
        time.sleep(REQUEST_DELAY)

    return total_fetched


# ---------------------------------------------------------------------------
# Export

def export_top(conn, n: int, out_dir: Path) -> Path:
    """Write top-N scored datasets as Markdown + CSV to out_dir."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT score, title, org_name, publisher, formats,
                   periodicity, modified_date, has_spatial, ckan_id
            FROM data_gov_catalog
            WHERE score IS NOT NULL AND access_level = 'public'
            ORDER BY score DESC, modified_date DESC NULLS LAST
            LIMIT %s
        """, (n,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]

    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV
    csv_path = out_dir / f"top{n}_datasets.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            d = dict(zip(cols, row))
            d["formats"] = ", ".join(d["formats"] or [])
            writer.writerow(d)

    # Markdown
    md_path = out_dir / f"top{n}_datasets.md"
    with open(md_path, "w") as f:
        f.write(f"# Top {n} Scored Federal Datasets from data.gov\n\n")
        f.write(f"*Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')} — ")
        f.write(f"scored from {_get_total(conn):,} catalog records*\n\n")
        f.write("| Score | Title | Publisher | Formats | Updated | Spatial |\n")
        f.write("|---|---|---|---|---|---|\n")
        for row in rows:
            d = dict(zip(cols, row))
            title_link = f"[{d['title'][:60]}](https://catalog.data.gov/dataset/{d['ckan_id']})"
            pub = (d["publisher"] or d["org_name"] or "")[:40]
            fmts = ", ".join((d["formats"] or [])[:3])
            mod = str(d["modified_date"] or "—")
            spatial = "✓" if d["has_spatial"] else ""
            f.write(f"| {d['score']} | {title_link} | {pub} | {fmts} | {mod} | {spatial} |\n")

    log.info("Exported top %d to %s", n, out_dir)
    return md_path


def _get_total(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM data_gov_catalog")
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# CLI

def _connect():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    p = argparse.ArgumentParser(description="Scrape and score the data.gov catalog.")
    p.add_argument("--score-only",    action="store_true", help="Re-score without scraping")
    p.add_argument("--export-only",   action="store_true", help="Export without scraping or scoring")
    p.add_argument("--start-offset",  type=int, default=0, help="Resume scrape from offset")
    p.add_argument("--top",           type=int, default=200, help="Number of top datasets to export")
    p.add_argument("--out-dir",       default="scratch", help="Output directory for export files")
    args = p.parse_args()

    api_key = os.environ.get("DATA_GOV_API_KEY", "DEMO_KEY")
    conn = _connect()
    try:
        if not args.score_only and not args.export_only:
            n = scrape(conn, api_key, start_offset=args.start_offset)
            log.info("Scraped %d records total.", n)

        if not args.export_only:
            run_score_pass(conn)

        out_path = export_top(conn, args.top, Path(args.out_dir))
        log.info("Done. Top-%d list: %s", args.top, out_path)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
