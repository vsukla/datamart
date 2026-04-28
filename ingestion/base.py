"""
Common base class for county-level data ingestion scripts.

New sources should subclass BaseIngestion and implement:
  - source_key  (str) — matches datasets.source_key
  - flat_file_url(year) -> str — URL to download
  - parse(content) -> dict[tuple[str,int], dict] — {(fips, year): metrics}
  - upsert(conn, records) -> int

The base provides:
  - run(conn, start, end) — download → parse → upsert loop with logging
  - mark_ingested(conn) — stamps datasets.last_ingested_at after a successful run
  - CLI via build_parser() / main()
"""

import argparse
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
    # Main loop

    def run(self, conn, start: int, end: int) -> int:
        total = 0
        for year in range(start, end + 1):
            content = self.fetch(year)
            records = self.parse(content)
            log.info("[%s] Parsed %d records for %d", self.source_key, len(records), year)
            count = self.upsert(conn, records)
            log.info("[%s] Upserted %d rows for %d", self.source_key, count, year)
            total += count
        self.mark_ingested(conn)
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
