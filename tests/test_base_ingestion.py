"""Tests for ingestion/base.py — BaseIngestion."""
import io
import zipfile
from unittest.mock import MagicMock, patch, call

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../ingestion"))

from base import BaseIngestion


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing
# ---------------------------------------------------------------------------

class _StubIngestion(BaseIngestion):
    source_key = "stub_source"

    def flat_file_url(self, year: int) -> str:
        return f"https://example.com/data_{year}.csv"

    def parse(self, content: bytes) -> dict:
        return {("01001", 2022): {"value": 42}}

    def upsert(self, conn, records: dict) -> int:
        return len(records)


class _ZipIngestion(BaseIngestion):
    source_key = "zip_source"
    download_is_zip = True

    def flat_file_url(self, year: int) -> str:
        return f"https://example.com/data_{year}.zip"

    def parse(self, content: bytes) -> dict:
        return {}

    def upsert(self, conn, records: dict) -> int:
        return 0


def _make_zip(filename: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(filename, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# TestFetch
# ---------------------------------------------------------------------------

class TestFetch:
    def test_returns_response_content(self):
        stub = _StubIngestion()
        mock_resp = MagicMock()
        mock_resp.content = b"col1,col2\n1,2\n"
        with patch("requests.get", return_value=mock_resp) as mock_get:
            result = stub.fetch(2022)
        mock_get.assert_called_once_with("https://example.com/data_2022.csv", timeout=120)
        assert result == b"col1,col2\n1,2\n"

    def test_raises_on_http_error(self):
        stub = _StubIngestion()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404")
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(Exception, match="404"):
                stub.fetch(2022)

    def test_zip_extracts_csv(self):
        ingestion = _ZipIngestion()
        csv_bytes = b"a,b\n1,2\n"
        zip_bytes = _make_zip("data_2022.csv", csv_bytes)
        mock_resp = MagicMock()
        mock_resp.content = zip_bytes
        with patch("requests.get", return_value=mock_resp):
            result = ingestion.fetch(2022)
        assert result == csv_bytes

    def test_zip_extracts_txt(self):
        ingestion = _ZipIngestion()
        txt_bytes = b"line1\nline2\n"
        zip_bytes = _make_zip("data_2022.txt", txt_bytes)
        mock_resp = MagicMock()
        mock_resp.content = zip_bytes
        with patch("requests.get", return_value=mock_resp):
            result = ingestion.fetch(2022)
        assert result == txt_bytes

    def test_year_substituted_in_url(self):
        stub = _StubIngestion()
        mock_resp = MagicMock()
        mock_resp.content = b""
        with patch("requests.get", return_value=mock_resp) as mock_get:
            stub.fetch(2019)
        assert "2019" in mock_get.call_args[0][0]


# ---------------------------------------------------------------------------
# TestMarkIngested
# ---------------------------------------------------------------------------

class TestMarkIngested:
    def test_executes_update(self):
        stub = _StubIngestion()
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        stub.mark_ingested(conn)
        assert cur.execute.called
        sql = cur.execute.call_args[0][0]
        assert "datasets" in sql
        assert "last_ingested_at" in sql

    def test_uses_correct_source_key(self):
        stub = _StubIngestion()
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        stub.mark_ingested(conn)
        params = cur.execute.call_args[0][1]
        assert "stub_source" in params

    def test_commits(self):
        stub = _StubIngestion()
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        stub.mark_ingested(conn)
        conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# TestRun
# ---------------------------------------------------------------------------

class TestRun:
    def test_iterates_year_range(self):
        stub = _StubIngestion()
        conn = MagicMock()
        fetched_years = []

        def fake_fetch(year):
            fetched_years.append(year)
            return b""

        with patch.object(stub, "fetch", side_effect=fake_fetch), \
             patch.object(stub, "mark_ingested"):
            stub.run(conn, 2020, 2022)

        assert fetched_years == [2020, 2021, 2022]

    def test_returns_total_upserted(self):
        stub = _StubIngestion()
        conn = MagicMock()

        with patch.object(stub, "fetch", return_value=b""), \
             patch.object(stub, "parse", return_value={("01001", 2020): {}}), \
             patch.object(stub, "upsert", return_value=5), \
             patch.object(stub, "mark_ingested"):
            total = stub.run(conn, 2020, 2022)

        assert total == 15  # 5 rows × 3 years

    def test_calls_mark_ingested_once(self):
        stub = _StubIngestion()
        conn = MagicMock()

        with patch.object(stub, "fetch", return_value=b""), \
             patch.object(stub, "mark_ingested") as mock_mark:
            stub.run(conn, 2020, 2022)

        mock_mark.assert_called_once_with(conn)

    def test_passes_parsed_records_to_upsert(self):
        stub = _StubIngestion()
        conn = MagicMock()
        records = {("01001", 2021): {"val": 99}}

        with patch.object(stub, "fetch", return_value=b""), \
             patch.object(stub, "parse", return_value=records), \
             patch.object(stub, "upsert", return_value=1) as mock_upsert, \
             patch.object(stub, "mark_ingested"):
            stub.run(conn, 2021, 2021)

        mock_upsert.assert_called_once_with(conn, records)

    def test_single_year_range(self):
        stub = _StubIngestion()
        conn = MagicMock()
        with patch.object(stub, "fetch", return_value=b"") as mock_fetch, \
             patch.object(stub, "mark_ingested"):
            stub.run(conn, 2023, 2023)
        mock_fetch.assert_called_once_with(2023)


# ---------------------------------------------------------------------------
# TestBuildParser
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_defaults(self):
        stub = _StubIngestion()
        p = stub.build_parser()
        args = p.parse_args([])
        assert args.start == 2018
        assert args.end == 2023
        assert args.file is None
        assert args.year is None

    def test_override_start_end(self):
        stub = _StubIngestion()
        p = stub.build_parser()
        args = p.parse_args(["--start", "2020", "--end", "2021"])
        assert args.start == 2020
        assert args.end == 2021

    def test_file_mode_args(self):
        stub = _StubIngestion()
        p = stub.build_parser()
        args = p.parse_args(["--file", "/tmp/data.csv", "--year", "2022"])
        assert args.file == "/tmp/data.csv"
        assert args.year == 2022


# ---------------------------------------------------------------------------
# TestAbstractMethods
# ---------------------------------------------------------------------------

class TestAbstractMethods:
    def test_flat_file_url_raises(self):
        class _Bare(BaseIngestion):
            source_key = "bare"
            def parse(self, content): return {}
            def upsert(self, conn, records): return 0

        with pytest.raises(NotImplementedError):
            _Bare().flat_file_url(2022)

    def test_parse_raises(self):
        class _Bare(BaseIngestion):
            source_key = "bare"
            def flat_file_url(self, year): return ""
            def upsert(self, conn, records): return 0

        with pytest.raises(NotImplementedError):
            _Bare().parse(b"")

    def test_upsert_raises(self):
        class _Bare(BaseIngestion):
            source_key = "bare"
            def flat_file_url(self, year): return ""
            def parse(self, content): return {}

        with pytest.raises(NotImplementedError):
            _Bare().upsert(None, {})
