"""
Computes data quality statistics for all ingested source tables and updates
the datasets catalog.

For each registered source, this script:
  1. Counts total rows
  2. Computes null rate (0.0–1.0) for each metric column
  3. Writes the results back to datasets.row_count, datasets.null_rates,
     and datasets.quality_computed_at

Run after any ingestion job, or on a schedule (e.g. nightly GitHub Action).

Usage:
  python compute_data_quality.py
"""

import logging
import os
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../config/.env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# Per-source: (table_name, [metric_columns_to_check_for_nulls])
SOURCE_CONFIG: dict[str, tuple[str, list[str]]] = {
    "census_acs5": (
        "census_acs5",
        ["population", "median_income", "pct_bachelors",
         "median_home_value", "pct_owner_occupied", "pct_poverty", "unemployment_rate",
         "pct_health_insured", "mean_commute_minutes",
         "pct_white", "pct_black", "pct_hispanic", "pct_asian"],
    ),
    "cdc_places": (
        "cdc_places",
        ["pct_obesity", "pct_diabetes", "pct_smoking", "pct_hypertension",
         "pct_depression", "pct_no_lpa", "pct_poor_mental_health"],
    ),
    "bls_laus": (
        "bls_laus",
        ["labor_force", "employed", "unemployed", "unemployment_rate"],
    ),
    "usda_food_env": (
        "usda_food_env",
        ["pct_low_food_access", "groceries_per_1000", "fast_food_per_1000",
         "pct_snap", "farmers_markets"],
    ),
    "epa_aqi": (
        "epa_aqi",
        ["days_with_aqi", "good_days", "moderate_days", "unhealthy_sensitive_days",
         "unhealthy_days", "very_unhealthy_days", "hazardous_days",
         "max_aqi", "median_aqi", "pm25_days", "ozone_days"],
    ),
    "fbi_crime": (
        "fbi_crime",
        ["population_covered", "violent_crimes", "violent_crime_rate",
         "property_crimes", "property_crime_rate"],
    ),
    "hud_fmr": (
        "hud_fmr",
        ["fmr_0br", "fmr_1br", "fmr_2br", "fmr_3br", "fmr_4br"],
    ),
    "eia_energy": (
        "eia_energy",
        ["elec_res_bbtu", "elec_com_bbtu", "elec_ind_bbtu", "elec_total_bbtu",
         "gas_res_bbtu", "gas_com_bbtu", "gas_ind_bbtu", "gas_total_bbtu"],
    ),
    "nhtsa_traffic": (
        "nhtsa_traffic",
        ["fatalities", "fatality_rate"],
    ),
    "ed_graduation": (
        "ed_graduation",
        ["grad_rate_all", "grad_rate_ecd", "cohort_all"],
    ),
}


def compute_quality(conn, table: str, metric_cols: list[str]) -> tuple[int, dict]:
    """Return (row_count, {col: null_rate}) for the given table."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        row_count = cur.fetchone()[0]

    if row_count == 0:
        return 0, {col: None for col in metric_cols}

    # Build a single query: COUNT(col IS NULL) / total for each column
    null_exprs = ", ".join(
        f"ROUND(SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END)::numeric / COUNT(*), 4) AS {col}"
        for col in metric_cols
    )
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"SELECT {null_exprs} FROM {table}")  # noqa: S608
        row = cur.fetchone()

    null_rates = {col: float(row[col]) if row[col] is not None else None
                  for col in metric_cols}
    return row_count, null_rates


def get_last_fetched(conn, table: str) -> datetime | None:
    """Return MAX(fetched_at) from the source table, or None if table is empty."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT MAX(fetched_at) FROM {table}")  # noqa: S608
        val = cur.fetchone()[0]
    return val


def update_catalog(conn, source_key: str, table: str, row_count: int, null_rates: dict) -> None:
    import json
    last_ingested = get_last_fetched(conn, table)
    sql = """
        UPDATE datasets
        SET row_count           = %(row_count)s,
            null_rates          = %(null_rates)s::jsonb,
            quality_computed_at = %(now)s,
            last_ingested_at    = COALESCE(%(last_ingested)s, last_ingested_at)
        WHERE source_key = %(source_key)s
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "source_key":    source_key,
            "row_count":     row_count,
            "null_rates":    json.dumps(null_rates),
            "now":           datetime.now(timezone.utc),
            "last_ingested": last_ingested,
        })
    conn.commit()


def run(conn) -> None:
    for source_key, (table, metric_cols) in SOURCE_CONFIG.items():
        log.info("Computing quality for %s (%s)...", source_key, table)
        try:
            row_count, null_rates = compute_quality(conn, table, metric_cols)
            update_catalog(conn, source_key, table, row_count, null_rates)
            log.info("  %s: %d rows, null rates: %s", source_key, row_count,
                     {k: f"{v:.1%}" if v is not None else "n/a"
                      for k, v in null_rates.items()})
        except Exception as exc:
            log.error("  %s: failed — %s", source_key, exc)


if __name__ == "__main__":
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
    )
    try:
        run(conn)
        log.info("Done.")
    finally:
        conn.close()
