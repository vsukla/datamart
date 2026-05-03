"""Tests for datamart-mcp/server.py tool logic."""
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../datamart-mcp"))

from unittest.mock import patch, MagicMock
import pytest

import server as mcp_server


def _mock_get(return_value):
    return patch.object(mcp_server, "_get", return_value=return_value)


class TestGetCountyProfile:
    def test_valid_fips_returns_json(self):
        profile = {"fips": "06037", "county_name": "Los Angeles County", "population": 10000000}
        with _mock_get([profile]):
            result = json.loads(mcp_server.get_county_profile("06037"))
        assert result["fips"] == "06037"

    def test_zero_pads_4digit_fips(self):
        profile = {"fips": "06037", "county_name": "Los Angeles County"}
        with _mock_get([profile]) as m:
            mcp_server.get_county_profile("6037")
        _, kwargs = m.call_args
        assert m.call_args[0][1]["fips"] == "06037"

    def test_invalid_fips_returns_error(self):
        result = json.loads(mcp_server.get_county_profile("XXXXX"))
        assert "error" in result

    def test_empty_response_returns_error(self):
        with _mock_get([]):
            result = json.loads(mcp_server.get_county_profile("06037"))
        assert "error" in result

    def test_http_error_returns_error(self):
        import httpx
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch.object(mcp_server, "_get", side_effect=httpx.HTTPStatusError("err", request=MagicMock(), response=mock_resp)):
            result = json.loads(mcp_server.get_county_profile("06037"))
        assert "error" in result


class TestSearchCounties:
    def test_returns_count_and_counties(self):
        counties = [{"fips": "06037", "name": "Los Angeles County", "state_fips": "06"}]
        with _mock_get(counties):
            result = json.loads(mcp_server.search_counties(state_fips="06"))
        assert result["count"] == 1
        assert result["counties"][0]["fips"] == "06037"

    def test_name_filter_case_insensitive(self):
        counties = [
            {"fips": "17031", "name": "Cook County", "state_fips": "17"},
            {"fips": "17043", "name": "DuPage County", "state_fips": "17"},
        ]
        with _mock_get(counties):
            result = json.loads(mcp_server.search_counties(name_contains="cook"))
        assert result["count"] == 1
        assert result["counties"][0]["fips"] == "17031"

    def test_empty_result_graceful(self):
        with _mock_get([]):
            result = json.loads(mcp_server.search_counties(state_fips="99"))
        assert result["count"] == 0


class TestGetStateSummary:
    def test_valid_state_returns_data(self):
        summary = {"state_fips": "06", "county_count": 58, "median_income": 75000}
        with _mock_get([summary]):
            result = json.loads(mcp_server.get_state_summary("06"))
        assert result["state_fips"] == "06"

    def test_invalid_state_fips_returns_error(self):
        result = json.loads(mcp_server.get_state_summary("XX"))
        assert "error" in result

    def test_zero_pads_1digit_fips(self):
        with _mock_get([{"state_fips": "01"}]) as m:
            mcp_server.get_state_summary("1")
        assert m.call_args[0][1]["state_fips"] == "01"

    def test_empty_response_returns_error(self):
        with _mock_get([]):
            result = json.loads(mcp_server.get_state_summary("06"))
        assert "error" in result


class TestCompareCounties:
    def test_compares_two_counties(self):
        profiles = [
            {"fips": "06037", "county_name": "Los Angeles"},
            {"fips": "17031", "county_name": "Cook"},
        ]
        with patch.object(mcp_server, "_get", side_effect=[[p] for p in profiles]):
            result = json.loads(mcp_server.compare_counties(["06037", "17031"]))
        assert result["count"] == 2

    def test_missing_county_listed(self):
        import httpx
        mock_resp = MagicMock(); mock_resp.status_code = 404
        with patch.object(mcp_server, "_get", side_effect=httpx.HTTPStatusError("", request=MagicMock(), response=mock_resp)):
            result = json.loads(mcp_server.compare_counties(["99999"]))
        assert "99999" in result["missing"]

    def test_empty_list_returns_error(self):
        result = json.loads(mcp_server.compare_counties([]))
        assert "error" in result

    def test_too_many_fips_returns_error(self):
        result = json.loads(mcp_server.compare_counties([str(i).zfill(5) for i in range(21)]))
        assert "error" in result


class TestListDatasets:
    def test_returns_datasets(self):
        datasets = [{"source_key": "census_acs5", "label": "Census ACS5"}]
        with _mock_get(datasets):
            result = json.loads(mcp_server.list_datasets())
        assert result[0]["source_key"] == "census_acs5"
