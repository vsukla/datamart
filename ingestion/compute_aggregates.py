"""
Computes pre-aggregated views from census_acs5 data and stores them in
aggregate tables. Designed to run as a daily batch job.

Tables populated (truncated and fully recomputed each run):
  agg_national_summary — population-weighted national averages per year
  agg_state_summary    — population-weighted county rollups per state per year
  agg_rankings         — rank + percentile per geography x year x metric
  agg_yoy              — year-over-year absolute and % change

Usage:
  python compute_aggregates.py
"""

import logging
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../config/.env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

METRICS = [
    "median_income",
    "pct_bachelors",
    "median_home_value",
    "pct_owner_occupied",
    "pct_poverty",
    "unemployment_rate",
]

_SQL_NATIONAL_SUMMARY = """
INSERT INTO agg_national_summary (
    year, total_population,
    avg_median_income, avg_pct_bachelors, avg_median_home_value,
    avg_pct_owner_occupied, avg_pct_poverty, avg_unemployment_rate
)
SELECT
    c.year,
    SUM(c.population)::bigint,
    ROUND(SUM(c.median_income::numeric     * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.median_income     IS NOT NULL), 0))    AS avg_median_income,
    ROUND(SUM(c.pct_bachelors::numeric     * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.pct_bachelors     IS NOT NULL), 0), 2) AS avg_pct_bachelors,
    ROUND(SUM(c.median_home_value::numeric  * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.median_home_value  IS NOT NULL), 0))   AS avg_median_home_value,
    ROUND(SUM(c.pct_owner_occupied::numeric * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.pct_owner_occupied IS NOT NULL), 0), 2) AS avg_pct_owner_occupied,
    ROUND(SUM(c.pct_poverty::numeric        * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.pct_poverty        IS NOT NULL), 0), 2) AS avg_pct_poverty,
    ROUND(SUM(c.unemployment_rate::numeric  * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.unemployment_rate  IS NOT NULL), 0), 2) AS avg_unemployment_rate
FROM census_acs5 c
JOIN geo_entities g ON g.fips = c.fips
WHERE g.geo_type = 'state'
GROUP BY c.year
ORDER BY c.year
"""

_SQL_STATE_SUMMARY = """
INSERT INTO agg_state_summary (
    state_fips, year, total_population,
    avg_median_income, avg_pct_bachelors, avg_median_home_value,
    avg_pct_owner_occupied, avg_pct_poverty, avg_unemployment_rate
)
SELECT
    g.state_fips,
    c.year,
    SUM(c.population)::bigint,
    ROUND(SUM(c.median_income::numeric     * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.median_income     IS NOT NULL), 0)),
    ROUND(SUM(c.pct_bachelors::numeric     * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.pct_bachelors     IS NOT NULL), 0), 2),
    ROUND(SUM(c.median_home_value::numeric  * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.median_home_value  IS NOT NULL), 0)),
    ROUND(SUM(c.pct_owner_occupied::numeric * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.pct_owner_occupied IS NOT NULL), 0), 2),
    ROUND(SUM(c.pct_poverty::numeric        * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.pct_poverty        IS NOT NULL), 0), 2),
    ROUND(SUM(c.unemployment_rate::numeric  * c.population)
          / NULLIF(SUM(c.population) FILTER (WHERE c.unemployment_rate  IS NOT NULL), 0), 2)
FROM census_acs5 c
JOIN geo_entities g ON g.fips = c.fips
WHERE g.geo_type = 'county'
GROUP BY g.state_fips, c.year
ORDER BY g.state_fips, c.year
"""


def _metric_union(metrics: list[str]) -> str:
    parts = [
        f"""
    SELECT c.fips, g.state_fips, g.geo_type, c.year,
           '{m}' AS metric, {m}::numeric AS value
    FROM census_acs5 c
    JOIN geo_entities g ON g.fips = c.fips
    WHERE {m} IS NOT NULL"""
        for m in metrics
    ]
    return " UNION ALL".join(parts)


def _sql_rankings(metrics: list[str]) -> str:
    return f"""
INSERT INTO agg_rankings
    (fips, state_fips, geo_type, year, metric, value, rank, percentile, peer_count)
WITH pivoted AS ({_metric_union(metrics)}
)
SELECT
    fips, state_fips, geo_type, year, metric, value,
    RANK() OVER (PARTITION BY geo_type, year, metric ORDER BY value)         AS rank,
    ROUND((PERCENT_RANK() OVER (PARTITION BY geo_type, year, metric
                               ORDER BY value) * 100)::numeric, 2)           AS percentile,
    COUNT(*) OVER (PARTITION BY geo_type, year, metric)                      AS peer_count
FROM pivoted
"""


def _sql_yoy(metrics: list[str]) -> str:
    return f"""
INSERT INTO agg_yoy
    (fips, state_fips, geo_type, year, metric, value, prev_value, change_abs, change_pct)
WITH pivoted AS ({_metric_union(metrics)}
)
SELECT
    curr.fips, curr.state_fips, curr.geo_type, curr.year, curr.metric,
    curr.value,
    prev.value                                                          AS prev_value,
    curr.value - prev.value                                             AS change_abs,
    ROUND((curr.value - prev.value) / NULLIF(ABS(prev.value), 0) * 100, 2) AS change_pct
FROM pivoted curr
JOIN pivoted prev
    ON  prev.fips   = curr.fips
    AND prev.metric = curr.metric
    AND prev.year   = curr.year - 1
"""


def compute(conn) -> None:
    with conn:
        with conn.cursor() as cur:
            log.info("Truncating aggregate tables...")
            cur.execute("""
                TRUNCATE agg_national_summary, agg_state_summary,
                         agg_rankings, agg_yoy
                RESTART IDENTITY
            """)

            log.info("Computing national summary...")
            cur.execute(_SQL_NATIONAL_SUMMARY)
            log.info("  %d rows", cur.rowcount)

            log.info("Computing state summary (county rollups)...")
            cur.execute(_SQL_STATE_SUMMARY)
            log.info("  %d rows", cur.rowcount)

            log.info("Computing rankings...")
            cur.execute(_sql_rankings(METRICS))
            log.info("  %d rows", cur.rowcount)

            log.info("Computing year-over-year changes...")
            cur.execute(_sql_yoy(METRICS))
            log.info("  %d rows", cur.rowcount)


if __name__ == "__main__":
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
    )
    try:
        compute(conn)
        log.info("Done.")
    finally:
        conn.close()
