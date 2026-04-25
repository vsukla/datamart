import pytest
from django.test import TestCase
from django.db import connection
from census.models import GeoEntity, CensusAcs5


class GeoAPITest(TestCase):
    @classmethod
    def setUpClass(cls):
        # Tables must exist before super() enters its atomic block and calls setUpTestData
        with connection.schema_editor() as editor:
            editor.create_model(GeoEntity)
            editor.create_model(CensusAcs5)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()  # rolls back the atomic block (clears data)
        with connection.schema_editor() as editor:
            editor.delete_model(CensusAcs5)
            editor.delete_model(GeoEntity)

    @classmethod
    def setUpTestData(cls):
        cls.ca = GeoEntity.objects.create(fips="06", geo_type="state", name="California", state_fips="06")
        cls.tx = GeoEntity.objects.create(fips="48", geo_type="state", name="Texas", state_fips="48")
        cls.la = GeoEntity.objects.create(fips="06037", geo_type="county", name="Los Angeles County, California", state_fips="06")

        CensusAcs5.objects.create(geo=cls.ca, year=2021, population=39000000, median_income=80000)
        CensusAcs5.objects.create(geo=cls.ca, year=2022, population=39356104, median_income=91905)
        CensusAcs5.objects.create(geo=cls.tx, year=2022, population=29000000, median_income=63000)
        CensusAcs5.objects.create(geo=cls.la, year=2022, population=10000000, median_income=75000)

    # --- /api/geo/ ---

    def test_geo_list_returns_all(self):
        resp = self.client.get("/api/geo/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 3)

    def test_geo_list_filter_geo_type_state(self):
        resp = self.client.get("/api/geo/?geo_type=state")
        data = resp.json()
        self.assertEqual(data["count"], 2)
        for item in data["results"]:
            self.assertEqual(item["geo_type"], "state")

    def test_geo_list_filter_geo_type_county(self):
        resp = self.client.get("/api/geo/?geo_type=county")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "06037")

    def test_geo_list_filter_state_fips(self):
        resp = self.client.get("/api/geo/?state_fips=06")
        fips_returned = [r["fips"] for r in resp.json()["results"]]
        self.assertIn("06", fips_returned)
        self.assertIn("06037", fips_returned)
        self.assertNotIn("48", fips_returned)

    # --- /api/geo/<fips>/ ---

    def test_geo_detail_fields(self):
        resp = self.client.get("/api/geo/06/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["fips"], "06")
        self.assertEqual(data["name"], "California")
        self.assertEqual(data["geo_type"], "state")

    def test_geo_detail_estimates_ordered_by_year(self):
        resp = self.client.get("/api/geo/06/")
        years = [e["year"] for e in resp.json()["estimates"]]
        self.assertEqual(years, [2021, 2022])

    def test_geo_detail_estimate_count(self):
        resp = self.client.get("/api/geo/06/")
        self.assertEqual(len(resp.json()["estimates"]), 2)

    def test_geo_detail_404(self):
        resp = self.client.get("/api/geo/99/")
        self.assertEqual(resp.status_code, 404)

    # --- /api/estimates/ ---

    def test_estimates_list_total(self):
        resp = self.client.get("/api/estimates/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 4)

    def test_estimates_filter_year(self):
        resp = self.client.get("/api/estimates/?year=2022")
        data = resp.json()
        self.assertEqual(data["count"], 3)
        for r in data["results"]:
            self.assertEqual(r["year"], 2022)

    def test_estimates_filter_state_fips(self):
        resp = self.client.get("/api/estimates/?state_fips=06")
        data = resp.json()
        for r in data["results"]:
            self.assertEqual(r["state_fips"], "06")
        fips_list = [r["fips"] for r in data["results"]]
        self.assertNotIn("48", fips_list)

    def test_estimates_filter_geo_type_county(self):
        resp = self.client.get("/api/estimates/?geo_type=county")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "06037")
        self.assertEqual(data["results"][0]["geo_type"], "county")

    def test_estimates_include_geo_fields(self):
        resp = self.client.get("/api/estimates/?geo_type=state&year=2022")
        result = next(r for r in resp.json()["results"] if r["fips"] == "06")
        self.assertEqual(result["geo_name"], "California")
        self.assertEqual(result["state_fips"], "06")

    def test_estimates_pagination(self):
        resp = self.client.get("/api/estimates/")
        data = resp.json()
        self.assertIn("count", data)
        self.assertIn("results", data)
