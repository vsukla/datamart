"""
Common base class for county-level data ingestion scripts.

New sources should subclass BaseIngestion and implement:
  - source_key  (str) — matches datasets.source_key
  - flat_file_url(year) -> str — URL to download
  - parse(content) -> dict[tuple[str,int], dict] — {(fips, year): metrics}
  - upsert(conn, records) -> int

The base provides:
  - run(conn, start, end) — download → parse → upsert loop with audit logging
  - mark_ingested(conn) — stamps datasets.last_ingested_at after a successful run
  - CLI via build_parser() / main()
"""

import argparse
import hashlib
import io
import logging
import os
import zipfile
from datetime import datetime, timezone

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../config/.env"))

log = logging.getLogger(__name__)


class BaseIngestion:
    source_key: str = ""

    # Override to True if the download is a zip containing a single CSV/TXT
    download_is_zip: bool = False

    def flat_file_url(self, year: int) -> str:
        raise NotImplementedError

    def parse(self, content: bytes) -> dict[tuple[str, int], dict]:
        """Parse raw bytes into {(fips, year): metrics}."""
        raise NotImplementedError

    def upsert(self, conn, records: dict[tuple[str, int], dict]) -> int:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Helpers available to subclasses

    def fetch(self, year: int) -> bytes:
        url = self.flat_file_url(year)
        log.info("[%s] Downloading %d: %s", self.source_key, year, url)
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        if self.download_is_zip:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                name = next(n for n in zf.namelist()
                            if n.endswith(".csv") or n.endswith(".txt"))
                return zf.read(name)
        return resp.content

    def mark_ingested(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE datasets SET last_ingested_at = %s WHERE source_key = %s",
                (datetime.now(timezone.utc), self.source_key),
            )
        conn.commit()

    # ------------------------------------------------------------------
    # Governance: run tracking and schema snapshotting

    def _compute_file_hash(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _begin_run(self, conn) -> int:
        """Insert a new ingestion_runs row and return its id."""
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ingestion_runs (source_key, started_at, fetched_at, status)
                VALUES (%s, %s, %s, 'running')
                RETURNING id
                """,
                (self.source_key, datetime.now(timezone.utc), datetime.now(timezone.utc)),
            )
            run_id = cur.fetchone()[0]
        conn.commit()
        log.info("[%s] Started ingestion run #%d", self.source_key, run_id)
        return run_id

    def _complete_run(
        self,
        conn,
        run_id: int,
        status: str,
        rows_loaded: int,
        file_hash: str | None = None,
        raw_file_url: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingestion_runs
                SET finished_at = %s, status = %s, rows_loaded = %s,
                    file_hash = %s, raw_file_url = %s, error_message = %s
                WHERE id = %s
                """,
                (
                    datetime.now(timezone.utc),
                    status,
                    rows_loaded,
                    file_hash,
                    raw_file_url,
                    error_message,
                    run_id,
                ),
            )
        conn.commit()
        log.info("[%s] Run #%d completed: %s (%d rows)", self.source_key, run_id, status, rows_loaded)

    def _take_schema_snapshot(self, conn, run_id: int, column_names: list[str]) -> None:
        """Record the column schema of parsed records; detect drift between runs."""
        sorted_cols = sorted(column_names)
        schema_hash = hashlib.sha256("|".join(sorted_cols).encode()).hexdigest()

        # Check if schema changed since last snapshot
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT schema_hash FROM schema_snapshots
                WHERE source_key = %s
                ORDER BY captured_at DESC LIMIT 1
                """,
                (self.source_key,),
            )
            row = cur.fetchone()
            if row and row[0] == schema_hash:
                return  # unchanged — skip

            if row:
                log.warning("[%s] Schema changed since last run!", self.source_key)

            cur.execute(
                """
                INSERT INTO schema_snapshots (source_key, ingestion_run_id, column_names, schema_hash)
                VALUES (%s, %s, %s, %s)
                """,
                (self.source_key, run_id, sorted_cols, schema_hash),
            )
        conn.commit()

    # ------------------------------------------------------------------
    # Main loop

    def run(self, conn, start: int, end: int) -> int:
        run_id = self._begin_run(conn)
        total = 0
        file_hash = None
        last_url = None
        schema_captured = False

        try:
            for year in range(start, end + 1):
                last_url = self.flat_file_url(year)
                content = self.fetch(year)
                file_hash = self._compute_file_hash(content)
                records = self.parse(content)
                log.info("[%s] Parsed %d records for %d", self.source_key, len(records), year)

                if not schema_captured and records:
                    sample = next(iter(records.values()))
                    self._take_schema_snapshot(conn, run_id, list(sample.keys()))
                    schema_captured = True

                count = self.upsert(conn, records)
                log.info("[%s] Upserted %d rows for %d", self.source_key, count, year)
                total += count

            self._complete_run(conn, run_id, "success", total,
                               file_hash=file_hash, raw_file_url=last_url)
            self.mark_ingested(conn)
        except Exception as exc:
            self._complete_run(conn, run_id, "error", total, error_message=str(exc))
            raise

        return total

    # ------------------------------------------------------------------
    # CLI

    def build_parser(self) -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(
            description=f"Ingest {self.source_key} data into datamart."
        )
        p.add_argument("--start", type=int, default=2018)
        p.add_argument("--end",   type=int, default=2023)
        p.add_argument("--file",  help="Path to a local file (skips download)")
        p.add_argument("--year",  type=int, help="Year for --file mode")
        return p

    def main(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        args = self.build_parser().parse_args()
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
                    self.build_parser().error("--year is required with --file")
                with open(args.file, "rb") as fh:
                    content = fh.read()
                records = self.parse(content)
                count = self.upsert(conn, records)
                self.mark_ingested(conn)
                log.info("[%s] Upserted %d rows. Done.", self.source_key, count)
            else:
                self.run(conn, args.start, args.end)
                log.info("[%s] Done.", self.source_key)
        finally:
            conn.close()
