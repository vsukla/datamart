import pytest
from unittest.mock import patch, MagicMock, call
from census_acs5 import _int, _pct, normalize_state, normalize_county, _fetch, load

SAMPLE_STATE = {
    "NAME": "California",
    "B01003_001E": "39356104",
    "B19013_001E": "91905",
    "B15003_022E": "5873000",
    "B15003_001E": "26561000",
    "B25077_001E": "659300",
    "B25003_001E": "13500000",
    "B25003_002E": "7500000",
    "B17001_002E": "4782000",
    "B17001_001E": "39500000",
    "B23025_005E": "1200000",
    "B23025_002E": "18900000",
    "state": "6",  # unpadded, as the API returns it
}

SAMPLE_COUNTY = {
    **SAMPLE_STATE,
    "NAME": "Los Angeles County, California",
    "county": "37",  # unpadded
}


class TestInt:
    def test_valid(self):
        assert _int("12345") == 12345

    def test_sentinel(self):
        assert _int("-666666666") is None

    def test_none(self):
        assert _int(None) is None

    def test_negative(self):
        assert _int("-1") is None

    def test_invalid_string(self):
        assert _int("N/A") is None

    def test_zero(self):
        assert _int("0") == 0


class TestPct:
    def test_valid(self):
        assert _pct("30", "100") == 30.0

    def test_rounding(self):
        assert _pct("1", "3") == 33.33

    def test_zero_denominator(self):
        assert _pct("30", "0") is None

    def test_none_numerator(self):
        assert _pct(None, "100") is None

    def test_sentinel_denominator(self):
        assert _pct("30", "-666666666") is None

    def test_both_none(self):
        assert _pct(None, None) is None


class TestNormalizeState:
    def test_fips_padded_to_2(self):
        geo, _ = normalize_state(SAMPLE_STATE, 2022)
        assert geo["fips"] == "06"

    def test_geo_type_is_state(self):
        geo, _ = normalize_state(SAMPLE_STATE, 2022)
        assert geo["geo_type"] == "state"

    def test_state_fips_equals_fips(self):
        geo, _ = normalize_state(SAMPLE_STATE, 2022)
        assert geo["state_fips"] == geo["fips"]

    def test_estimate_year(self):
        _, est = normalize_state(SAMPLE_STATE, 2022)
        assert est["year"] == 2022

    def test_estimate_population(self):
        _, est = normalize_state(SAMPLE_STATE, 2022)
        assert est["population"] == 39356104

    def test_estimate_median_income(self):
        _, est = normalize_state(SAMPLE_STATE, 2022)
        assert est["median_income"] == 91905

    def test_estimate_pct_bachelors(self):
        _, est = normalize_state(SAMPLE_STATE, 2022)
        assert est["pct_bachelors"] == round(5873000 / 26561000 * 100, 2)

    def test_estimate_pct_poverty(self):
        _, est = normalize_state(SAMPLE_STATE, 2022)
        assert est["pct_poverty"] == round(4782000 / 39500000 * 100, 2)

    def test_estimate_unemployment_rate(self):
        _, est = normalize_state(SAMPLE_STATE, 2022)
        assert est["unemployment_rate"] == round(1200000 / 18900000 * 100, 2)

    def test_sentinel_income_returns_none(self):
        raw = {**SAMPLE_STATE, "B19013_001E": "-666666666"}
        _, est = normalize_state(raw, 2022)
        assert est["median_income"] is None


class TestNormalizeCounty:
    def test_fips_is_5_chars(self):
        geo, _ = normalize_county(SAMPLE_COUNTY, 2022)
        assert geo["fips"] == "06037"

    def test_geo_type_is_county(self):
        geo, _ = normalize_county(SAMPLE_COUNTY, 2022)
        assert geo["geo_type"] == "county"

    def test_state_fips_is_2_chars(self):
        geo, _ = normalize_county(SAMPLE_COUNTY, 2022)
        assert geo["state_fips"] == "06"

    def test_state_fips_differs_from_fips(self):
        geo, _ = normalize_county(SAMPLE_COUNTY, 2022)
        assert geo["state_fips"] != geo["fips"]


class TestFetch:
    def _mock_resp(self, status=200, headers=None, json_data=None):
        resp = MagicMock()
        resp.status_code = status
        resp.headers = headers or {}
        if json_data is not None:
            resp.json.return_value = json_data
        return resp

    def test_raises_on_301(self):
        with patch("census_acs5.requests.get", return_value=self._mock_resp(status=301)):
            with pytest.raises(RuntimeError, match="Census API key"):
                _fetch(2022, "state:*")

    def test_raises_on_key_error_header(self):
        resp = self._mock_resp(headers={"X-DataWebAPI-KeyError": "true"})
        with patch("census_acs5.requests.get", return_value=resp):
            with pytest.raises(RuntimeError, match="Census API key"):
                _fetch(2022, "state:*")

    def test_returns_list_of_dicts(self):
        json_data = [
            ["NAME", "B01003_001E", "state"],
            ["California", "39356104", "06"],
            ["Texas", "29000000", "48"],
        ]
        with patch("census_acs5.requests.get", return_value=self._mock_resp(json_data=json_data)):
            result = _fetch(2022, "state:*")
        assert len(result) == 2
        assert result[0]["NAME"] == "California"
        assert result[1]["state"] == "48"

    def test_strips_header_row(self):
        json_data = [["NAME", "state"], ["California", "06"]]
        with patch("census_acs5.requests.get", return_value=self._mock_resp(json_data=json_data)):
            result = _fetch(2022, "state:*")
        assert len(result) == 1

    def test_retries_on_transient_error(self):
        good_resp = self._mock_resp(json_data=[["NAME", "state"], ["California", "06"]])
        with patch("census_acs5.requests.get", side_effect=[Exception("timeout"), good_resp]):
            with patch("census_acs5.time.sleep"):
                result = _fetch(2022, "state:*")
        assert len(result) == 1

    def test_raises_after_max_retries(self):
        with patch("census_acs5.requests.get", side_effect=Exception("timeout")):
            with patch("census_acs5.time.sleep"):
                with pytest.raises(Exception, match="timeout"):
                    _fetch(2022, "state:*")


class TestLoad:
    GEOS = [{"fips": "06", "geo_type": "state", "name": "California", "state_fips": "06"}]
    ESTIMATES = [{"fips": "06", "year": 2022, "population": 39356104, "median_income": 91905,
                  "pct_bachelors": 22.11, "median_home_value": 659300,
                  "pct_owner_occupied": 55.63, "pct_poverty": 12.12, "unemployment_rate": 6.36}]

    def _run_load(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        with patch("census_acs5.psycopg2.connect", return_value=mock_conn):
            with patch("census_acs5.psycopg2.extras.execute_batch") as mock_batch:
                load(self.GEOS, self.ESTIMATES)
                return mock_batch

    def test_geo_entities_upserted_before_estimates(self):
        mock_batch = self._run_load()
        first_sql = mock_batch.call_args_list[0][0][1]
        assert "geo_entities" in first_sql

    def test_census_acs5_upserted_second(self):
        mock_batch = self._run_load()
        second_sql = mock_batch.call_args_list[1][0][1]
        assert "census_acs5" in second_sql

    def test_execute_batch_called_twice(self):
        mock_batch = self._run_load()
        assert mock_batch.call_count == 2

    def test_page_size_500(self):
        mock_batch = self._run_load()
        for c in mock_batch.call_args_list:
            assert c[1]["page_size"] == 500
