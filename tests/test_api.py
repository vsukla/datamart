from django.test import TestCase
from django.db import connection
from census.models import GeoEntity, CensusAcs5, AggNationalSummary, AggStateSummary, AggRanking, AggYoY


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

    # --- validation ---

    def test_geo_list_invalid_geo_type_returns_400(self):
        resp = self.client.get("/api/geo/?geo_type=invalid")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("geo_type", resp.json())

    def test_estimates_invalid_geo_type_returns_400(self):
        resp = self.client.get("/api/estimates/?geo_type=staet")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("geo_type", resp.json())

    def test_estimates_invalid_year_returns_400(self):
        resp = self.client.get("/api/estimates/?year=abc")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("year", resp.json())


class AggregateAPITest(TestCase):
    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(AggNationalSummary)
            editor.create_model(AggStateSummary)
            editor.create_model(AggRanking)
            editor.create_model(AggYoY)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(AggYoY)
            editor.delete_model(AggRanking)
            editor.delete_model(AggStateSummary)
            editor.delete_model(AggNationalSummary)

    @classmethod
    def setUpTestData(cls):
        AggNationalSummary.objects.create(year=2021, total_population=330000000, avg_median_income=65000)
        AggNationalSummary.objects.create(year=2022, total_population=332000000, avg_median_income=67000)

        AggStateSummary.objects.create(state_fips="06", year=2021, avg_median_income=76000)
        AggStateSummary.objects.create(state_fips="06", year=2022, avg_median_income=80000)
        AggStateSummary.objects.create(state_fips="48", year=2022, avg_median_income=63000)

        AggRanking.objects.create(fips="06", state_fips="06", geo_type="state", year=2022,
                                  metric="median_income", value=80000, rank=1, percentile="100.00", peer_count=2)
        AggRanking.objects.create(fips="48", state_fips="48", geo_type="state", year=2022,
                                  metric="median_income", value=63000, rank=2, percentile="50.00", peer_count=2)
        AggRanking.objects.create(fips="06037", state_fips="06", geo_type="county", year=2022,
                                  metric="median_income", value=75000, rank=1, percentile="100.00", peer_count=1)

        AggYoY.objects.create(fips="06", state_fips="06", geo_type="state", year=2022,
                              metric="median_income", value=80000, prev_value=76000, change_abs=4000, change_pct="5.26")
        AggYoY.objects.create(fips="48", state_fips="48", geo_type="state", year=2022,
                              metric="pct_poverty", value="13.50", prev_value="14.00", change_abs="-0.50", change_pct="-3.57")

    # --- /api/aggregates/national/ ---

    def test_national_returns_all(self):
        resp = self.client.get("/api/aggregates/national/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 2)

    def test_national_filter_year(self):
        resp = self.client.get("/api/aggregates/national/?year=2022")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["year"], 2022)

    def test_national_fields(self):
        resp = self.client.get("/api/aggregates/national/?year=2022")
        r = resp.json()["results"][0]
        self.assertIn("total_population", r)
        self.assertIn("avg_median_income", r)
        self.assertIn("avg_pct_poverty", r)

    def test_national_invalid_year_returns_400(self):
        resp = self.client.get("/api/aggregates/national/?year=abc")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("year", resp.json())

    # --- /api/aggregates/state-summary/ ---

    def test_state_summary_returns_all(self):
        resp = self.client.get("/api/aggregates/state-summary/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 3)

    def test_state_summary_filter_state_fips(self):
        resp = self.client.get("/api/aggregates/state-summary/?state_fips=06")
        data = resp.json()
        self.assertEqual(data["count"], 2)
        for r in data["results"]:
            self.assertEqual(r["state_fips"], "06")

    def test_state_summary_filter_year(self):
        resp = self.client.get("/api/aggregates/state-summary/?year=2022")
        self.assertEqual(resp.json()["count"], 2)

    def test_state_summary_filter_state_and_year(self):
        resp = self.client.get("/api/aggregates/state-summary/?state_fips=06&year=2022")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["avg_median_income"], "80000")

    def test_state_summary_invalid_year_returns_400(self):
        resp = self.client.get("/api/aggregates/state-summary/?year=bad")
        self.assertEqual(resp.status_code, 400)

    # --- /api/aggregates/rankings/ ---

    def test_rankings_returns_all(self):
        resp = self.client.get("/api/aggregates/rankings/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 3)

    def test_rankings_filter_geo_type(self):
        resp = self.client.get("/api/aggregates/rankings/?geo_type=state")
        self.assertEqual(resp.json()["count"], 2)

    def test_rankings_filter_state_fips(self):
        resp = self.client.get("/api/aggregates/rankings/?state_fips=06")
        data = resp.json()
        for r in data["results"]:
            self.assertEqual(r["state_fips"], "06")

    def test_rankings_filter_metric(self):
        resp = self.client.get("/api/aggregates/rankings/?metric=median_income")
        self.assertEqual(resp.json()["count"], 3)

    def test_rankings_filter_year(self):
        resp = self.client.get("/api/aggregates/rankings/?year=2022")
        self.assertEqual(resp.json()["count"], 3)

    def test_rankings_fields(self):
        resp = self.client.get("/api/aggregates/rankings/?state_fips=06&geo_type=state")
        r = resp.json()["results"][0]
        self.assertIn("rank", r)
        self.assertIn("percentile", r)
        self.assertIn("peer_count", r)

    def test_rankings_invalid_metric_returns_400(self):
        resp = self.client.get("/api/aggregates/rankings/?metric=bogus")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("metric", resp.json())

    def test_rankings_invalid_geo_type_returns_400(self):
        resp = self.client.get("/api/aggregates/rankings/?geo_type=nation")
        self.assertEqual(resp.status_code, 400)

    # --- /api/aggregates/yoy/ ---

    def test_yoy_returns_all(self):
        resp = self.client.get("/api/aggregates/yoy/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 2)

    def test_yoy_filter_metric(self):
        resp = self.client.get("/api/aggregates/yoy/?metric=median_income")
        self.assertEqual(resp.json()["count"], 1)

    def test_yoy_filter_state_fips(self):
        resp = self.client.get("/api/aggregates/yoy/?state_fips=06")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "06")

    def test_yoy_filter_geo_type(self):
        resp = self.client.get("/api/aggregates/yoy/?geo_type=state")
        self.assertEqual(resp.json()["count"], 2)

    def test_yoy_fields(self):
        resp = self.client.get("/api/aggregates/yoy/?state_fips=06")
        r = resp.json()["results"][0]
        self.assertIn("change_abs", r)
        self.assertIn("change_pct", r)
        self.assertIn("prev_value", r)
        self.assertIn("value", r)

    def test_yoy_invalid_metric_returns_400(self):
        resp = self.client.get("/api/aggregates/yoy/?metric=invalid")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("metric", resp.json())

    def test_yoy_invalid_geo_type_returns_400(self):
        resp = self.client.get("/api/aggregates/yoy/?geo_type=bad")
        self.assertEqual(resp.status_code, 400)


class DashboardTest(TestCase):
    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(GeoEntity)
            editor.create_model(AggNationalSummary)
            editor.create_model(AggStateSummary)
            editor.create_model(AggYoY)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(AggYoY)
            editor.delete_model(AggStateSummary)
            editor.delete_model(AggNationalSummary)
            editor.delete_model(GeoEntity)

    @classmethod
    def setUpTestData(cls):
        GeoEntity.objects.create(fips="06", geo_type="state", name="California", state_fips="06")
        AggNationalSummary.objects.create(year=2022, total_population=332000000, avg_median_income=67000)
        AggStateSummary.objects.create(state_fips="06", year=2022, avg_median_income=80000)
        AggYoY.objects.create(fips="06", state_fips="06", geo_type="state", year=2022,
                              metric="median_income", value=80000, prev_value=76000,
                              change_abs=4000, change_pct="5.26")

    def test_dashboard_returns_200(self):
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_embeds_national_json(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b'"year": 2022', resp.content)

    def test_dashboard_embeds_state_names(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"California", resp.content)

    def test_dashboard_embeds_metric_labels(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"median_income", resp.content)

    def test_dashboard_has_chart_canvases(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"nationalChart", resp.content)
        self.assertIn(b"rankingChart", resp.content)
        self.assertIn(b"yoyChart", resp.content)

    def test_dashboard_has_metric_select(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"metricSelect", resp.content)

    def test_dashboard_has_year_select(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"yearSelect", resp.content)
