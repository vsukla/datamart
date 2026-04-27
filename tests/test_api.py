from django.test import TestCase
from django.db import connection
from census.models import (
    GeoEntity, CensusAcs5, AggNationalSummary, AggStateSummary, AggRanking, AggYoY,
    CdcPlaces, BlsLaus, UsdaFoodEnv, CountyProfile,
)


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

    def test_dashboard_has_health_and_food_canvases(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"healthChart", resp.content)
        self.assertIn(b"foodChart", resp.content)

    def test_dashboard_has_external_section(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"externalSection", resp.content)

    def test_dashboard_embeds_health_metric_labels(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"pct_obesity", resp.content)
        self.assertIn(b"healthMetricLabels", resp.content)

    def test_dashboard_embeds_food_metric_labels(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"pct_low_food_access", resp.content)
        self.assertIn(b"foodMetricLabels", resp.content)


class ExternalSourceAPITest(TestCase):
    """Tests for /api/health/, /api/labor/, /api/food/."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(GeoEntity)
            editor.create_model(CdcPlaces)
            editor.create_model(BlsLaus)
            editor.create_model(UsdaFoodEnv)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(UsdaFoodEnv)
            editor.delete_model(BlsLaus)
            editor.delete_model(CdcPlaces)
            editor.delete_model(GeoEntity)

    @classmethod
    def setUpTestData(cls):
        GeoEntity.objects.create(fips="06037", geo_type="county", name="Los Angeles County, California", state_fips="06")
        GeoEntity.objects.create(fips="48201", geo_type="county", name="Harris County, Texas", state_fips="48")

        CdcPlaces.objects.create(fips="06037", year=2022,
                                 pct_obesity="36.5", pct_diabetes="10.2", pct_smoking="12.0",
                                 pct_hypertension="38.1", pct_depression="22.4",
                                 pct_no_lpa="30.1", pct_poor_mental_health="15.6")
        CdcPlaces.objects.create(fips="48201", year=2022,
                                 pct_obesity="38.0", pct_diabetes="11.5", pct_smoking="14.0",
                                 pct_hypertension="40.0", pct_depression="24.0",
                                 pct_no_lpa="32.0", pct_poor_mental_health="16.0")

        BlsLaus.objects.create(fips="06037", year=2022,
                               labor_force=5000000, employed=4750000, unemployed=250000, unemployment_rate="5.0")
        BlsLaus.objects.create(fips="48201", year=2021,
                               labor_force=2500000, employed=2375000, unemployed=125000, unemployment_rate="5.0")

        UsdaFoodEnv.objects.create(fips="06037", data_year=2018,
                                   pct_low_food_access="12.5", groceries_per_1000="0.42",
                                   fast_food_per_1000="2.10", pct_snap="14.2", farmers_markets=45)
        UsdaFoodEnv.objects.create(fips="48201", data_year=2018,
                                   pct_low_food_access="8.3", groceries_per_1000="0.31",
                                   fast_food_per_1000="2.50", pct_snap="12.0", farmers_markets=20)

    # --- /api/health/ ---

    def test_health_returns_all(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 2)

    def test_health_filter_fips(self):
        resp = self.client.get("/api/health/?fips=06037")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "06037")

    def test_health_filter_state_fips(self):
        resp = self.client.get("/api/health/?state_fips=48")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "48201")

    def test_health_filter_year(self):
        resp = self.client.get("/api/health/?year=2022")
        self.assertEqual(resp.json()["count"], 2)

    def test_health_fields(self):
        resp = self.client.get("/api/health/?fips=06037")
        r = resp.json()["results"][0]
        for field in ["pct_obesity", "pct_diabetes", "pct_smoking",
                      "pct_hypertension", "pct_depression", "pct_no_lpa", "pct_poor_mental_health"]:
            self.assertIn(field, r)

    def test_health_invalid_year_returns_400(self):
        resp = self.client.get("/api/health/?year=notanumber")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("year", resp.json())

    # --- /api/labor/ ---

    def test_labor_returns_all(self):
        resp = self.client.get("/api/labor/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 2)

    def test_labor_filter_fips(self):
        resp = self.client.get("/api/labor/?fips=48201")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "48201")

    def test_labor_filter_state_fips(self):
        resp = self.client.get("/api/labor/?state_fips=06")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "06037")

    def test_labor_filter_year(self):
        resp = self.client.get("/api/labor/?year=2022")
        self.assertEqual(resp.json()["count"], 1)

    def test_labor_fields(self):
        resp = self.client.get("/api/labor/?fips=06037")
        r = resp.json()["results"][0]
        for field in ["labor_force", "employed", "unemployed", "unemployment_rate"]:
            self.assertIn(field, r)

    def test_labor_invalid_year_returns_400(self):
        resp = self.client.get("/api/labor/?year=abc")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("year", resp.json())

    # --- /api/food/ ---

    def test_food_returns_all(self):
        resp = self.client.get("/api/food/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 2)

    def test_food_filter_fips(self):
        resp = self.client.get("/api/food/?fips=06037")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "06037")

    def test_food_filter_state_fips(self):
        resp = self.client.get("/api/food/?state_fips=48")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "48201")

    def test_food_filter_data_year(self):
        resp = self.client.get("/api/food/?data_year=2018")
        self.assertEqual(resp.json()["count"], 2)

    def test_food_fields(self):
        resp = self.client.get("/api/food/?fips=06037")
        r = resp.json()["results"][0]
        for field in ["pct_low_food_access", "groceries_per_1000",
                      "fast_food_per_1000", "pct_snap", "farmers_markets"]:
            self.assertIn(field, r)

    def test_food_invalid_data_year_returns_400(self):
        resp = self.client.get("/api/food/?data_year=abc")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("year", resp.json())


class CountyProfileAPITest(TestCase):
    """Tests for /api/profile/ (county_profile view, treated as a table in tests)."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(CountyProfile)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(CountyProfile)

    @classmethod
    def setUpTestData(cls):
        CountyProfile.objects.create(
            fips="06037", county_name="Los Angeles County, California", state_fips="06",
            census_year=2022, population=10000000, median_income=75000,
            pct_bachelors="35.5", median_home_value=750000, pct_owner_occupied="48.0",
            pct_poverty="14.2", census_unemployment_rate="5.5",
            places_year=2022, pct_obesity="36.5", pct_diabetes="10.2",
            pct_smoking="12.0", pct_hypertension="38.1", pct_depression="22.4",
            pct_no_lpa="30.1", pct_poor_mental_health="15.6",
            bls_year=2022, labor_force=5000000, employed=4750000,
            unemployed=250000, bls_unemployment_rate="5.0",
            usda_year=2018, pct_low_food_access="12.5", groceries_per_1000="0.42",
            fast_food_per_1000="2.10", pct_snap="14.2", farmers_markets=45,
        )
        CountyProfile.objects.create(
            fips="48201", county_name="Harris County, Texas", state_fips="48",
            census_year=2022, population=4700000, median_income=62000,
            pct_bachelors="32.0", median_home_value=280000, pct_owner_occupied="55.0",
            pct_poverty="15.0", census_unemployment_rate="4.8",
            places_year=2022, pct_obesity="38.0", pct_diabetes="11.5",
            pct_smoking="14.0", pct_hypertension="40.0", pct_depression="24.0",
            pct_no_lpa="32.0", pct_poor_mental_health="16.0",
            bls_year=2022, labor_force=2500000, employed=2375000,
            unemployed=125000, bls_unemployment_rate="5.0",
            usda_year=2018, pct_low_food_access="8.3", groceries_per_1000="0.31",
            fast_food_per_1000="2.50", pct_snap="12.0", farmers_markets=20,
        )

    def test_profile_returns_all(self):
        resp = self.client.get("/api/profile/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 2)

    def test_profile_filter_fips(self):
        resp = self.client.get("/api/profile/?fips=06037")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        r = data["results"][0]
        self.assertEqual(r["fips"], "06037")
        self.assertEqual(r["county_name"], "Los Angeles County, California")

    def test_profile_filter_state_fips(self):
        resp = self.client.get("/api/profile/?state_fips=48")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "48201")

    def test_profile_has_all_source_fields(self):
        resp = self.client.get("/api/profile/?fips=06037")
        r = resp.json()["results"][0]
        # Census
        for f in ["census_year", "population", "median_income", "pct_poverty"]:
            self.assertIn(f, r)
        # CDC PLACES
        for f in ["places_year", "pct_obesity", "pct_diabetes"]:
            self.assertIn(f, r)
        # BLS
        for f in ["bls_year", "labor_force", "bls_unemployment_rate"]:
            self.assertIn(f, r)
        # USDA
        for f in ["usda_year", "pct_low_food_access", "pct_snap", "farmers_markets"]:
            self.assertIn(f, r)

    def test_profile_census_and_health_values(self):
        resp = self.client.get("/api/profile/?fips=06037")
        r = resp.json()["results"][0]
        self.assertEqual(int(r["median_income"]), 75000)
        self.assertEqual(r["pct_obesity"], "36.5")

    def test_profile_pagination(self):
        resp = self.client.get("/api/profile/")
        data = resp.json()
        self.assertIn("count", data)
        self.assertIn("results", data)
