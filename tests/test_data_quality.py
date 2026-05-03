"""Tests for compute_data_quality.py."""
import json
from unittest.mock import MagicMock, call, patch

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../ingestion"))

from compute_data_quality import compute_quality, update_catalog, run, SOURCE_CONFIG


def _make_conn(row_count=100, null_row=None):
    """Return a mock connection. null_row is a dict {col: null_rate}."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchone.return_value = (row_count,)
    if null_row is not None:
        mock_cur.fetchone.side_effect = [(row_count,), null_row]
    return mock_conn, mock_cur


class TestComputeQuality:
    def test_returns_row_count(self):
        conn, cur = _make_conn(
            row_count=500,
            null_row={"median_income": 0.02, "population": 0.0},
        )
        count, _ = compute_quality(conn, "census_acs5", ["median_income", "population"])
        assert count == 500

    def test_returns_null_rates_dict(self):
        conn, cur = _make_conn(
            row_count=500,
            null_row={"median_income": 0.02, "population": 0.0},
        )
        _, rates = compute_quality(conn, "census_acs5", ["median_income", "population"])
        assert rates["median_income"] == pytest.approx(0.02)
        assert rates["population"] == pytest.approx(0.0)

    def test_empty_table_returns_zero_count(self):
        conn, cur = _make_conn(row_count=0)
        count, rates = compute_quality(conn, "census_acs5", ["median_income"])
        assert count == 0
        assert rates["median_income"] is None

    def test_null_rate_cast_to_float(self):
        from decimal import Decimal
        conn, cur = _make_conn(
            row_count=100,
            null_row={"pct_obesity": Decimal("0.0500")},
        )
        _, rates = compute_quality(conn, "cdc_places", ["pct_obesity"])
        assert isinstance(rates["pct_obesity"], float)
        assert rates["pct_obesity"] == pytest.approx(0.05)


class TestUpdateCatalog:
    def test_executes_update(self):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        update_catalog(conn, "census_acs5", 16400, {"median_income": 0.02})
        assert cur.execute.called

    def test_commits(self):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        update_catalog(conn, "census_acs5", 16400, {})
        conn.commit.assert_called_once()


class TestRun:
    def test_processes_all_sources(self):
        with patch("compute_data_quality.compute_quality", return_value=(100, {})) as mock_q, \
             patch("compute_data_quality.update_catalog") as mock_u:
            run(MagicMock())
        assert mock_q.call_count == len(SOURCE_CONFIG)
        assert mock_u.call_count == len(SOURCE_CONFIG)

    def test_source_config_covers_all_tables(self):
        expected = {"census_acs5", "cdc_places", "bls_laus", "usda_food_env",
                    "epa_aqi", "fbi_crime", "hud_fmr", "eia_energy",
                    "nhtsa_traffic", "ed_graduation"}
        assert set(SOURCE_CONFIG.keys()) == expected

    def test_run_continues_after_error(self):
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("simulated failure")
            return (100, {})

        with patch("compute_data_quality.compute_quality", side_effect=side_effect), \
             patch("compute_data_quality.update_catalog"):
            run(MagicMock())
        # All sources attempted; first one failed, rest succeeded
        assert call_count == len(SOURCE_CONFIG)
