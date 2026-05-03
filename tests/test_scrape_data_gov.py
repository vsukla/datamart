"""Tests for scrape_data_gov.py scoring and parsing logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../ingestion"))

from scrape_data_gov import score_record, _parse_record


class TestScoreRecord:
    def _base(self, **overrides):
        row = {
            "formats": ["CSV", "JSON"],
            "org_name": "hhs-gov",
            "publisher": "",
            "tag_names": ["county", "health"],
            "group_names": [],
            "title": "County Health Statistics",
            "periodicity": "R/P1Y",
            "modified_date": "2023-01-01",
            "access_level": "public",
        }
        row.update(overrides)
        return row

    def test_max_score_federal_geo_maintained(self):
        assert score_record(self._base()) == 100

    def test_non_public_penalized(self):
        score = score_record(self._base(access_level="restricted public"))
        assert score < score_record(self._base())

    def test_bad_formats_only_penalizes(self):
        score_bad = score_record(self._base(formats=["PDF", "DOCX"]))
        score_good = score_record(self._base(formats=["CSV"]))
        assert score_bad < score_good

    def test_no_periodicity_reduces_score(self):
        score_with = score_record(self._base())
        score_without = score_record(self._base(periodicity=None))
        assert score_with > score_without

    def test_old_modified_date_no_bonus(self):
        score_recent = score_record(self._base(modified_date="2022-06-01"))
        score_old = score_record(self._base(modified_date="2015-01-01"))
        assert score_recent > score_old

    def test_score_clamped_0_to_100(self):
        score = score_record(self._base(
            access_level="non-public",
            formats=["PDF"],
            org_name="unknown",
            publisher="",
            tag_names=[],
            periodicity=None,
            modified_date=None,
        ))
        assert 0 <= score <= 100

    def test_federal_publisher_keyword_scores(self):
        row = self._base(org_name="not-gov", publisher="Department of Labor")
        score = score_record(row)
        assert score > 50


class TestParseRecord:
    def _ckan(self, **overrides):
        r = {
            "id": "abc-123",
            "name": "test-dataset",
            "title": "Test Dataset",
            "organization": {"name": "hhs-gov"},
            "extras": [
                {"key": "publisher", "value": "HHS"},
                {"key": "accessLevel", "value": "public"},
                {"key": "accrualPeriodicity", "value": "R/P1Y"},
                {"key": "modified", "value": "2023-06-15"},
            ],
            "resources": [
                {"format": "CSV"},
                {"format": "JSON"},
                {"format": "CSV"},  # duplicate
            ],
            "groups": [{"name": "health"}],
            "tags": [{"name": "county"}, {"name": "statistics"}],
            "num_resources": 3,
            "metadata_modified": "2024-01-01T00:00:00Z",
        }
        r.update(overrides)
        return r

    def test_deduplicates_formats(self):
        rec = _parse_record(self._ckan())
        assert rec["formats"].count("CSV") == 1

    def test_modified_date_parsed(self):
        from datetime import date
        rec = _parse_record(self._ckan())
        assert rec["modified_date"] == date(2023, 6, 15)

    def test_has_spatial_false_without_extras(self):
        rec = _parse_record(self._ckan())
        assert rec["has_spatial"] is False

    def test_has_spatial_true_with_extras(self):
        r = self._ckan()
        r["extras"].append({"key": "spatial", "value": '{"type":"Polygon"}'})
        rec = _parse_record(r)
        assert rec["has_spatial"] is True

    def test_access_level_extracted(self):
        rec = _parse_record(self._ckan())
        assert rec["access_level"] == "public"

    def test_missing_org_graceful(self):
        r = self._ckan()
        r["organization"] = None
        rec = _parse_record(r)
        assert rec["org_name"] == ""
