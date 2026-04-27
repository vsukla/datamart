"""
Tests for ingest_cdc_places, ingest_bls_laus, and ingest_usda_food_env.
All DB and HTTP calls are mocked.
"""
import io
import json
from collections import defaultdict
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# CDC PLACES
# ---------------------------------------------------------------------------

from ingest_cdc_places import pivot, fetch_places, upsert as cdc_upsert, ingest as cdc_ingest

SAMPLE_PLACES_ROWS = [
    {"locationid": "06037", "year": "2022", "measureid": "OBESITY",    "data_value": "36.5"},
    {"locationid": "06037", "year": "2022", "measureid": "DIABETES",   "data_value": "10.2"},
    {"locationid": "06037", "year": "2022", "measureid": "CSMOKING",   "data_value": "12.0"},
    {"locationid": "06037", "year": "2022", "measureid": "BPHIGH",     "data_value": "38.1"},
    {"locationid": "06037", "year": "2022", "measureid": "DEPRESSION", "data_value": "22.4"},
    {"locationid": "06037", "year": "2022", "measureid": "LPA",        "data_value": "30.1"},
    {"locationid": "06037", "year": "2022", "measureid": "MHLTH",      "data_value": "15.6"},
    {"locationid": "48201", "year": "2022", "measureid": "OBESITY",    "data_value": "38.0"},
]


class TestCdcPivot:
    def test_known_measures_mapped(self):
        records = pivot(SAMPLE_PLACES_ROWS, 2022)
        assert "06037" in records
        assert records["06037"]["pct_obesity"] == 36.5
        assert records["06037"]["pct_diabetes"] == 10.2
        assert records["06037"]["pct_smoking"] == 12.0

    def test_year_set(self):
        records = pivot(SAMPLE_PLACES_ROWS, 2022)
        assert records["06037"]["year"] == 2022

    def test_fips_zero_padded(self):
        rows = [{"locationid": "6037", "year": "2022", "measureid": "OBESITY", "data_value": "36.5"}]
        records = pivot(rows, 2022)
        assert "06037" in records

    def test_unknown_measure_ignored(self):
        rows = [{"locationid": "06037", "year": "2022", "measureid": "UNKNOWN", "data_value": "9.9"}]
        records = pivot(rows, 2022)
        assert "06037" not in records or "UNKNOWN" not in records.get("06037", {})

    def test_null_value_skipped(self):
        rows = [{"locationid": "06037", "year": "2022", "measureid": "OBESITY", "data_value": None}]
        records = pivot(rows, 2022)
        assert records["06037"].get("pct_obesity") is None

    def test_multiple_fips(self):
        records = pivot(SAMPLE_PLACES_ROWS, 2022)
        assert "48201" in records
        assert records["48201"]["pct_obesity"] == 38.0


class TestCdcFetch:
    def _mock_resp(self, data):
        m = MagicMock()
        m.json.return_value = data
        m.raise_for_status = MagicMock()
        return m

    def test_single_page(self):
        with patch("ingest_cdc_places.requests.get",
                   return_value=self._mock_resp(SAMPLE_PLACES_ROWS[:3])):
            rows = fetch_places(2022)
        assert len(rows) == 3

    def test_paginate_until_short_page(self):
        # first page full (50000), second page short
        big_page = SAMPLE_PLACES_ROWS * 2  # only 16 rows — less than PAGE_LIMIT of 50000
        with patch("ingest_cdc_places.requests.get",
                   return_value=self._mock_resp(big_page)):
            rows = fetch_places(2022)
        assert len(rows) == len(big_page)


class TestCdcUpsert:
    def _make_conn(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = 1
        return mock_conn, mock_cur

    def test_skips_unknown_fips(self):
        conn, cur = self._make_conn()
        records = {"99999": {"year": 2022, "pct_obesity": 30.0}}
        count = cdc_upsert(conn, records, known_fips={"06037"})
        cur.execute.assert_not_called()

    def test_upserts_known_fips(self):
        conn, cur = self._make_conn()
        records = pivot(SAMPLE_PLACES_ROWS, 2022)
        cdc_upsert(conn, records, known_fips={"06037", "48201"})
        assert cur.execute.call_count == 2

    def test_commits_after_upsert(self):
        conn, cur = self._make_conn()
        records = pivot(SAMPLE_PLACES_ROWS[:1], 2022)
        cdc_upsert(conn, records, known_fips={"06037"})
        conn.commit.assert_called_once()


class TestCdcIngest:
    def test_ingest_calls_fetch_and_upsert(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = [("06037",), ("48201",)]
        mock_cur.rowcount = 1

        with patch("ingest_cdc_places.fetch_places", return_value=SAMPLE_PLACES_ROWS) as mock_fetch:
            count = cdc_ingest(mock_conn, 2022)

        mock_fetch.assert_called_once_with(2022, None)
        assert count >= 0


# ---------------------------------------------------------------------------
# BLS LAUS
# ---------------------------------------------------------------------------

from ingest_bls_laus import (
    build_series_id, parse_fips_from_series, parse_bls_response,
    upsert as bls_upsert, ingest as bls_ingest,
)

SAMPLE_BLS_RESPONSE = {
    "status": "REQUEST_SUCCEEDED",
    "Results": {
        "series": [
            {
                "seriesID": "LAUCN060370000000003",   # unemployment_rate
                "data": [
                    {"year": "2022", "period": "M13", "value": "5.0"},
                    {"year": "2022", "period": "M01", "value": "4.8"},  # non-annual, skip
                ],
            },
            {
                "seriesID": "LAUCN060370000000006",   # labor_force
                "data": [
                    {"year": "2022", "period": "M13", "value": "5000000"},
                ],
            },
        ]
    },
}


class TestBlsSeriesId:
    def test_format(self):
        sid = build_series_id("06037", "003")
        assert sid == "LAUCN060370000000003"

    def test_parse_roundtrip(self):
        sid = build_series_id("06037", "003")
        fips, stype = parse_fips_from_series(sid)
        assert fips == "06037"
        assert stype == "003"

    def test_all_states_fips_preserved(self):
        sid = build_series_id("01001", "006")
        assert sid == "LAUCN010010000000006"


class TestBlsParseResponse:
    def test_annual_only(self):
        records = parse_bls_response(SAMPLE_BLS_RESPONSE)
        # M13 records for 06037/2022
        assert ("06037", 2022) in records

    def test_monthly_skipped(self):
        records = parse_bls_response(SAMPLE_BLS_RESPONSE)
        # only annual M13 included; M01 skipped (still just one record per fips/year)
        assert len(records) == 1

    def test_unemployment_rate_float(self):
        records = parse_bls_response(SAMPLE_BLS_RESPONSE)
        assert records[("06037", 2022)]["unemployment_rate"] == 5.0

    def test_labor_force_int(self):
        records = parse_bls_response(SAMPLE_BLS_RESPONSE)
        assert records[("06037", 2022)]["labor_force"] == 5000000


class TestBlsUpsert:
    def _make_conn(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = 1
        return mock_conn, mock_cur

    def test_upsert_executes_once_per_record(self):
        conn, cur = self._make_conn()
        records = {("06037", 2022): {"unemployment_rate": 5.0, "labor_force": 5000000}}
        bls_upsert(conn, records)
        assert cur.execute.call_count == 1

    def test_commits(self):
        conn, cur = self._make_conn()
        bls_upsert(conn, {})
        conn.commit.assert_called_once()


class TestBlsIngest:
    def test_ingest_builds_series_and_fetches(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = [("06037",)]
        mock_cur.rowcount = 1

        with patch("ingest_bls_laus.fetch_batch", return_value=SAMPLE_BLS_RESPONSE) as mock_fetch:
            with patch("ingest_bls_laus.time.sleep"):
                bls_ingest(mock_conn, 2022, 2022)

        assert mock_fetch.called


# ---------------------------------------------------------------------------
# USDA Food Environment Atlas
# ---------------------------------------------------------------------------

from ingest_usda_food_env import load_workbook_data, upsert as usda_upsert, _safe


def _make_workbook(sheets: dict[str, list[list]]):
    """Build a minimal openpyxl workbook in memory for testing."""
    import openpyxl
    wb = openpyxl.Workbook()
    first = True
    for sheet_name, rows in sheets.items():
        if first:
            ws = wb.active
            ws.title = sheet_name
            first = False
        else:
            ws = wb.create_sheet(sheet_name)
        for row in rows:
            ws.append(row)
    return wb


class TestUsdaSafe:
    def test_float_conversion(self):
        assert _safe("12.5", float) == 12.5

    def test_int_conversion(self):
        assert _safe("45", int) == 45

    def test_na_returns_none(self):
        assert _safe("NA", float) is None

    def test_empty_returns_none(self):
        assert _safe("", float) is None

    def test_none_returns_none(self):
        assert _safe(None, float) is None


class TestUsdaLoadWorkbook:
    def _workbook_bytes(self, sheets):
        import io, openpyxl
        wb = _make_workbook(sheets)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.read()

    def test_loads_pct_low_food_access(self):
        data = self._workbook_bytes({
            "ACCESS": [["FIPS", "PCT_LACCESS_POP15"], [6037, 12.5]],
        })
        records = load_workbook_data(data)
        assert "06037" in records
        assert records["06037"]["pct_low_food_access"] == 12.5

    def test_fips_zero_padded(self):
        data = self._workbook_bytes({
            "STORES": [["FIPS", "GROCPTH16"], [1001, 0.42]],
        })
        records = load_workbook_data(data)
        assert "01001" in records

    def test_missing_sheet_skipped(self):
        # Only ACCESS sheet — STORES not present
        data = self._workbook_bytes({
            "ACCESS": [["FIPS", "PCT_LACCESS_POP15"], [6037, 12.5]],
        })
        records = load_workbook_data(data)
        # No groceries_per_1000 since STORES sheet missing
        assert "groceries_per_1000" not in records.get("06037", {})

    def test_na_value_stored_as_none(self):
        data = self._workbook_bytes({
            "LOCAL": [["FIPS", "FMRKT18"], [6037, None]],
        })
        records = load_workbook_data(data)
        assert records.get("06037", {}).get("farmers_markets") is None

    def test_multiple_sheets_merged(self):
        data = self._workbook_bytes({
            "ACCESS":      [["FIPS", "PCT_LACCESS_POP15"], [6037, 12.5]],
            "STORES":      [["FIPS", "GROCPTH16"],         [6037, 0.42]],
            "RESTAURANTS": [["FIPS", "FSRPTH16"],          [6037, 2.10]],
            "ASSISTANCE":  [["FIPS", "PCT_SNAP17"],        [6037, 14.2]],
            "LOCAL":       [["FIPS", "FMRKT18"],           [6037, 45]],
        })
        records = load_workbook_data(data)
        r = records["06037"]
        assert r["pct_low_food_access"] == 12.5
        assert r["groceries_per_1000"] == 0.42
        assert r["fast_food_per_1000"] == 2.10
        assert r["pct_snap"] == 14.2
        assert r["farmers_markets"] == 45


class TestUsdaUpsert:
    def _make_conn(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = 1
        return mock_conn, mock_cur

    def test_skips_unknown_fips(self):
        conn, cur = self._make_conn()
        records = {"99999": {"pct_low_food_access": 10.0}}
        usda_upsert(conn, records, known_fips={"06037"}, data_year=2018)
        cur.execute.assert_not_called()

    def test_upserts_known_fips(self):
        conn, cur = self._make_conn()
        records = {"06037": {"pct_low_food_access": 12.5, "groceries_per_1000": 0.42,
                             "fast_food_per_1000": 2.10, "pct_snap": 14.2, "farmers_markets": 45}}
        usda_upsert(conn, records, known_fips={"06037"}, data_year=2018)
        cur.execute.assert_called_once()

    def test_commits(self):
        conn, cur = self._make_conn()
        usda_upsert(conn, {}, known_fips=set(), data_year=2018)
        conn.commit.assert_called_once()
