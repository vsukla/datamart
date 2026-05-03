import json

from django.test import TestCase
from django.db import connection
from census.models import (
    Dataset,
    GeoEntity, CensusAcs5, AggNationalSummary, AggStateSummary, AggRanking, AggYoY,
    CdcPlaces, BlsLaus, UsdaFoodEnv, EpaAqi, FbiCrime, HudFmr, EiaEnergy, NhtsaTraffic, EdGraduation, CountyProfile,
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

    # --- range filters ---

    def test_estimates_range_filter_gte(self):
        # Only CA 2022 has median_income >= 85000
        resp = self.client.get("/api/estimates/?median_income__gte=85000")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(int(data["results"][0]["median_income"]), 91905)

    def test_estimates_range_filter_lte(self):
        # Only TX 2022 has median_income <= 65000
        resp = self.client.get("/api/estimates/?median_income__lte=65000")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "48")

    def test_estimates_range_filter_combined(self):
        # CA 2021 (80000) and LA county 2022 (75000) are in [75000, 80000]
        resp = self.client.get("/api/estimates/?median_income__gte=75000&median_income__lte=80000")
        data = resp.json()
        self.assertEqual(data["count"], 2)
        fips_set = {r["fips"] for r in data["results"]}
        self.assertEqual(fips_set, {"06", "06037"})

    def test_estimates_range_filter_combines_with_year(self):
        # median_income__gte=70000 AND year=2022 → CA 2022 (91905) + LA 2022 (75000)
        resp = self.client.get("/api/estimates/?year=2022&median_income__gte=70000")
        data = resp.json()
        self.assertEqual(data["count"], 2)

    def test_estimates_range_filter_invalid_value_returns_400(self):
        resp = self.client.get("/api/estimates/?median_income__gte=notanumber")
        self.assertEqual(resp.status_code, 400)

    def test_estimates_range_filter_unknown_field_ignored(self):
        # Unrecognized field names are silently ignored (not a security issue — only
        # whitelisted metrics are ever applied)
        resp = self.client.get("/api/estimates/?bogus_field__gte=100")
        self.assertEqual(resp.status_code, 200)

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
            editor.create_model(Dataset)
            editor.create_model(GeoEntity)
            editor.create_model(AggNationalSummary)
            editor.create_model(AggStateSummary)
            editor.create_model(AggYoY)
            editor.create_model(CdcPlaces)
            editor.create_model(UsdaFoodEnv)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(AggYoY)
            editor.delete_model(AggStateSummary)
            editor.delete_model(AggNationalSummary)
            editor.delete_model(UsdaFoodEnv)
            editor.delete_model(CdcPlaces)
            editor.delete_model(GeoEntity)
            editor.delete_model(Dataset)

    @classmethod
    def setUpTestData(cls):
        Dataset.objects.create(
            source_key="census_acs5", name="Census ACS5",
            row_count=16400, null_rates={"median_income": 0.02, "population": 0.0},
            last_ingested_at="2026-04-01T00:00:00Z",
        )
        Dataset.objects.create(
            source_key="cdc_places", name="CDC PLACES",
            row_count=3200, null_rates=None, last_ingested_at=None,
        )
        GeoEntity.objects.create(fips="06", geo_type="state", name="California", state_fips="06")
        AggNationalSummary.objects.create(year=2022, total_population=332000000, avg_median_income=67000)
        AggStateSummary.objects.create(state_fips="06", year=2022, avg_median_income=80000)
        AggYoY.objects.create(fips="06", state_fips="06", geo_type="state", year=2022,
                              metric="median_income", value=80000, prev_value=76000,
                              change_abs=4000, change_pct="5.26")
        CdcPlaces.objects.create(fips="06037", year=2022,
                                 pct_obesity="36.5", pct_diabetes="10.2", pct_smoking="12.0",
                                 pct_hypertension="38.1", pct_depression="22.4",
                                 pct_no_lpa="30.1", pct_poor_mental_health="15.6")
        UsdaFoodEnv.objects.create(fips="06037", data_year=2018,
                                   pct_low_food_access="12.5", groceries_per_1000="0.42",
                                   fast_food_per_1000="2.10", pct_snap="14.2", farmers_markets=45)

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

    def test_dashboard_has_scatter_chart(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"scatterChart", resp.content)
        self.assertIn(b"scatterXSelect", resp.content)
        self.assertIn(b"scatterYSelect", resp.content)

    def test_dashboard_has_county_table(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"countyTableHead", resp.content)
        self.assertIn(b"countyTableBody", resp.content)

    def test_dashboard_embeds_state_health_json(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"stateHealth", resp.content)
        self.assertIn(b"avg_pct_obesity", resp.content)

    def test_dashboard_embeds_state_food_json(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"stateFood", resp.content)
        self.assertIn(b"avg_pct_low_food_access", resp.content)

    def test_dashboard_metric_select_has_optgroups(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"Census ACS5", resp.content)
        self.assertIn(b"CDC PLACES", resp.content)

    def test_metric_select_has_usda_optgroup(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"USDA Atlas", resp.content)

    # --- state_health aggregate (health-food-ranking feature) ---

    def test_state_health_aggregates_by_state(self):
        resp = self.client.get("/dashboard/")
        health = json.loads(resp.context["state_health_json"])
        self.assertEqual(len(health), 1)
        self.assertEqual(health[0]["state_fips"], "06")

    def test_state_health_aggregate_values(self):
        resp = self.client.get("/dashboard/")
        r = json.loads(resp.context["state_health_json"])[0]
        self.assertAlmostEqual(float(r["avg_pct_obesity"]), 36.5)
        self.assertAlmostEqual(float(r["avg_pct_diabetes"]), 10.2)

    def test_state_health_has_all_metric_fields(self):
        resp = self.client.get("/dashboard/")
        r = json.loads(resp.context["state_health_json"])[0]
        for field in [
            "avg_pct_obesity", "avg_pct_diabetes", "avg_pct_smoking",
            "avg_pct_hypertension", "avg_pct_depression",
            "avg_pct_no_lpa", "avg_pct_poor_mental_health",
        ]:
            self.assertIn(field, r)

    # --- state_food aggregate (health-food-ranking feature) ---

    def test_state_food_aggregates_by_state(self):
        resp = self.client.get("/dashboard/")
        food = json.loads(resp.context["state_food_json"])
        self.assertEqual(len(food), 1)
        self.assertEqual(food[0]["state_fips"], "06")

    def test_state_food_aggregate_values(self):
        resp = self.client.get("/dashboard/")
        r = json.loads(resp.context["state_food_json"])[0]
        self.assertAlmostEqual(float(r["avg_pct_low_food_access"]), 12.5)
        self.assertAlmostEqual(float(r["avg_fast_food_per_1000"]), 2.1)

    def test_state_food_has_all_metric_fields(self):
        resp = self.client.get("/dashboard/")
        r = json.loads(resp.context["state_food_json"])[0]
        for field in [
            "avg_pct_low_food_access", "avg_groceries_per_1000",
            "avg_fast_food_per_1000", "avg_pct_snap", "avg_farmers_markets",
        ]:
            self.assertIn(field, r)

    def test_state_food_sentinel_excludes_null(self):
        # A county with null pct_low_food_access should not affect the state average
        UsdaFoodEnv.objects.create(
            fips="06001", data_year=2018,
            pct_low_food_access=None, groceries_per_1000="0.50",
            fast_food_per_1000="1.0", pct_snap="10.0", farmers_markets=5,
        )
        resp = self.client.get("/dashboard/")
        r = json.loads(resp.context["state_food_json"])[0]
        self.assertAlmostEqual(float(r["avg_pct_low_food_access"]), 12.5)

    # --- Dataset catalog panel ---

    def test_dashboard_embeds_datasets_json(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"catalogDatasets", resp.content)
        self.assertIn(b"census_acs5", resp.content)

    def test_dashboard_has_catalog_table(self):
        resp = self.client.get("/dashboard/")
        self.assertIn(b"catalogTable", resp.content)
        self.assertIn(b"catalogBody", resp.content)

    def test_dashboard_datasets_json_has_two_rows(self):
        resp = self.client.get("/dashboard/")
        datasets = json.loads(resp.context["datasets_json"])
        self.assertEqual(len(datasets), 2)

    def test_dashboard_datasets_json_includes_row_count(self):
        resp = self.client.get("/dashboard/")
        datasets = json.loads(resp.context["datasets_json"])
        acs5 = next(d for d in datasets if d["source_key"] == "census_acs5")
        self.assertEqual(acs5["row_count"], 16400)

    def test_dashboard_datasets_json_includes_null_rates(self):
        resp = self.client.get("/dashboard/")
        datasets = json.loads(resp.context["datasets_json"])
        acs5 = next(d for d in datasets if d["source_key"] == "census_acs5")
        self.assertAlmostEqual(acs5["null_rates"]["median_income"], 0.02)

    def test_dashboard_datasets_json_handles_no_ingestion(self):
        resp = self.client.get("/dashboard/")
        datasets = json.loads(resp.context["datasets_json"])
        places = next(d for d in datasets if d["source_key"] == "cdc_places")
        self.assertIsNone(places["last_ingested_at"])
        self.assertIsNone(places["null_rates"])


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
            pct_health_insured="91.2", mean_commute_minutes="28.5",
            pct_white="28.0", pct_black="9.0", pct_hispanic="49.0", pct_asian="12.0",
            places_year=2022, pct_obesity="36.5", pct_diabetes="10.2",
            pct_smoking="12.0", pct_hypertension="38.1", pct_depression="22.4",
            pct_no_lpa="30.1", pct_poor_mental_health="15.6",
            bls_year=2022, labor_force=5000000, employed=4750000,
            unemployed=250000, bls_unemployment_rate="5.0",
            usda_year=2018, pct_low_food_access="12.5", groceries_per_1000="0.42",
            fast_food_per_1000="2.10", pct_snap="14.2", farmers_markets=45,
            aqi_year=2022, median_aqi="42.0", max_aqi=112, good_days=180,
            moderate_days=120, unhealthy_sensitive_days=50, unhealthy_days=10,
            very_unhealthy_days=3, hazardous_days=0, pm25_days=85, ozone_days=95,
            crime_year=2022, violent_crimes=15234, violent_crime_rate="450.1",
            property_crimes=89023, property_crime_rate="2630.5",
        )
        CountyProfile.objects.create(
            fips="48201", county_name="Harris County, Texas", state_fips="48",
            census_year=2022, population=4700000, median_income=62000,
            pct_bachelors="32.0", median_home_value=280000, pct_owner_occupied="55.0",
            pct_poverty="15.0", census_unemployment_rate="4.8",
            pct_health_insured="82.5", mean_commute_minutes="30.2",
            pct_white="33.0", pct_black="19.0", pct_hispanic="41.0", pct_asian="7.0",
            places_year=2022, pct_obesity="38.0", pct_diabetes="11.5",
            pct_smoking="14.0", pct_hypertension="40.0", pct_depression="24.0",
            pct_no_lpa="32.0", pct_poor_mental_health="16.0",
            bls_year=2022, labor_force=2500000, employed=2375000,
            unemployed=125000, bls_unemployment_rate="5.0",
            usda_year=2018, pct_low_food_access="8.3", groceries_per_1000="0.31",
            fast_food_per_1000="2.50", pct_snap="12.0", farmers_markets=20,
            aqi_year=2022, median_aqi="55.0", max_aqi=145, good_days=150,
            moderate_days=140, unhealthy_sensitive_days=55, unhealthy_days=15,
            very_unhealthy_days=5, hazardous_days=1, pm25_days=100, ozone_days=80,
            crime_year=2022, violent_crimes=23456, violent_crime_rate="620.8",
            property_crimes=145678, property_crime_rate="3860.2",
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
        for f in ["census_year", "population", "median_income", "pct_poverty",
                   "pct_health_insured", "mean_commute_minutes",
                   "pct_white", "pct_black", "pct_hispanic", "pct_asian"]:
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
        # EPA AQI
        for f in ["aqi_year", "median_aqi", "max_aqi", "good_days", "pm25_days", "ozone_days"]:
            self.assertIn(f, r)
        # FBI Crime
        for f in ["crime_year", "violent_crime_rate", "property_crime_rate"]:
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

    # --- /api/profile/<fips>/ ---

    def test_profile_detail_returns_single(self):
        resp = self.client.get("/api/profile/06037/")
        self.assertEqual(resp.status_code, 200)
        r = resp.json()
        self.assertEqual(r["fips"], "06037")
        self.assertEqual(r["county_name"], "Los Angeles County, California")

    def test_profile_detail_404_on_unknown_fips(self):
        resp = self.client.get("/api/profile/99999/")
        self.assertEqual(resp.status_code, 404)

    def test_profile_detail_not_paginated(self):
        resp = self.client.get("/api/profile/06037/")
        data = resp.json()
        self.assertNotIn("count", data)
        self.assertIn("fips", data)

    # --- /api/compare/ ---

    def test_compare_two_counties(self):
        resp = self.client.get("/api/compare/?fips=06037,48201")
        data = resp.json()
        self.assertEqual(data["count"], 2)
        fips_returned = {r["fips"] for r in data["results"]}
        self.assertEqual(fips_returned, {"06037", "48201"})

    def test_compare_single_county(self):
        resp = self.client.get("/api/compare/?fips=06037")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 1)

    def test_compare_empty_returns_empty(self):
        resp = self.client.get("/api/compare/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)

    def test_compare_caps_at_six(self):
        # 7 fips supplied; only 2 exist in test data so count <= 2, but no error
        resp = self.client.get("/api/compare/?fips=06037,48201,11001,12001,13001,17001,36001")
        self.assertEqual(resp.status_code, 200)


class CountyRankingsAPITest(TestCase):
    """Tests for /api/rankings/<fips>/."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(AggRanking)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(AggRanking)

    @classmethod
    def setUpTestData(cls):
        AggRanking.objects.create(
            fips="06037", state_fips="06", geo_type="county",
            year=2022, metric="median_income",
            value="75000.00", rank=250, percentile="90.50", peer_count=3000,
        )
        AggRanking.objects.create(
            fips="06037", state_fips="06", geo_type="county",
            year=2021, metric="median_income",
            value="72000.00", rank=280, percentile="88.00", peer_count=3000,
        )
        AggRanking.objects.create(
            fips="06037", state_fips="06", geo_type="county",
            year=2022, metric="pct_poverty",
            value="14.20", rank=800, percentile="40.00", peer_count=3000,
        )
        AggRanking.objects.create(
            fips="48201", state_fips="48", geo_type="county",
            year=2022, metric="median_income",
            value="62000.00", rank=1200, percentile="60.00", peer_count=3000,
        )

    def test_rankings_returns_all_for_fips(self):
        resp = self.client.get("/api/rankings/06037/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # 3 rows for 06037 (2 years of median_income + 1 pct_poverty)
        self.assertEqual(data["count"], 3)

    def test_rankings_excludes_other_fips(self):
        resp = self.client.get("/api/rankings/06037/")
        fips_set = {r["fips"] for r in resp.json()["results"]}
        self.assertEqual(fips_set, {"06037"})

    def test_rankings_filter_year(self):
        resp = self.client.get("/api/rankings/06037/?year=2022")
        data = resp.json()
        self.assertEqual(data["count"], 2)
        for r in data["results"]:
            self.assertEqual(r["year"], 2022)

    def test_rankings_fields(self):
        resp = self.client.get("/api/rankings/06037/")
        r = resp.json()["results"][0]
        for f in ["fips", "metric", "year", "value", "rank", "percentile", "peer_count"]:
            self.assertIn(f, r)

    def test_rankings_unknown_fips_returns_empty(self):
        resp = self.client.get("/api/rankings/99999/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)


class EpaAqiAPITest(TestCase):
    """Tests for /api/aqi/."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(GeoEntity)
            editor.create_model(EpaAqi)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(EpaAqi)
            editor.delete_model(GeoEntity)

    @classmethod
    def setUpTestData(cls):
        GeoEntity.objects.create(fips="06037", geo_type="county",
                                 name="Los Angeles County, California", state_fips="06")
        GeoEntity.objects.create(fips="48201", geo_type="county",
                                 name="Harris County, Texas", state_fips="48")
        EpaAqi.objects.create(
            fips="06037", year=2022, days_with_aqi=363, good_days=180,
            moderate_days=120, unhealthy_sensitive_days=50, unhealthy_days=10,
            very_unhealthy_days=3, hazardous_days=0, max_aqi=112, median_aqi="42.0",
            pm25_days=85, ozone_days=95,
        )
        EpaAqi.objects.create(
            fips="48201", year=2022, days_with_aqi=355, good_days=150,
            moderate_days=140, unhealthy_sensitive_days=55, unhealthy_days=15,
            very_unhealthy_days=5, hazardous_days=1, max_aqi=145, median_aqi="55.0",
            pm25_days=100, ozone_days=80,
        )

    def test_aqi_returns_all(self):
        resp = self.client.get("/api/aqi/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 2)

    def test_aqi_filter_fips(self):
        resp = self.client.get("/api/aqi/?fips=06037")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "06037")

    def test_aqi_filter_state_fips(self):
        resp = self.client.get("/api/aqi/?state_fips=48")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "48201")

    def test_aqi_filter_year(self):
        resp = self.client.get("/api/aqi/?year=2022")
        self.assertEqual(resp.json()["count"], 2)

    def test_aqi_fields(self):
        resp = self.client.get("/api/aqi/?fips=06037")
        r = resp.json()["results"][0]
        for field in ["median_aqi", "max_aqi", "good_days", "moderate_days",
                      "unhealthy_sensitive_days", "unhealthy_days", "very_unhealthy_days",
                      "hazardous_days", "pm25_days", "ozone_days"]:
            self.assertIn(field, r)

    def test_aqi_values(self):
        resp = self.client.get("/api/aqi/?fips=06037")
        r = resp.json()["results"][0]
        self.assertEqual(r["median_aqi"], "42.0")
        self.assertEqual(r["max_aqi"], 112)
        self.assertEqual(r["good_days"], 180)

    def test_aqi_invalid_year_returns_400(self):
        resp = self.client.get("/api/aqi/?year=abc")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("year", resp.json())


class FbiCrimeAPITest(TestCase):
    """Tests for /api/crime/."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(GeoEntity)
            editor.create_model(FbiCrime)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(FbiCrime)
            editor.delete_model(GeoEntity)

    @classmethod
    def setUpTestData(cls):
        GeoEntity.objects.create(fips="06037", geo_type="county",
                                 name="Los Angeles County, California", state_fips="06")
        GeoEntity.objects.create(fips="48201", geo_type="county",
                                 name="Harris County, Texas", state_fips="48")
        FbiCrime.objects.create(
            fips="06037", year=2022, population_covered=10014009,
            violent_crimes=15234, violent_crime_rate="450.1",
            property_crimes=89023, property_crime_rate="2630.5",
        )
        FbiCrime.objects.create(
            fips="48201", year=2022, population_covered=4731145,
            violent_crimes=23456, violent_crime_rate="620.8",
            property_crimes=145678, property_crime_rate="3860.2",
        )

    def test_crime_returns_all(self):
        resp = self.client.get("/api/crime/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 2)

    def test_crime_filter_fips(self):
        resp = self.client.get("/api/crime/?fips=06037")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "06037")

    def test_crime_filter_state_fips(self):
        resp = self.client.get("/api/crime/?state_fips=48")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "48201")

    def test_crime_filter_year(self):
        resp = self.client.get("/api/crime/?year=2022")
        self.assertEqual(resp.json()["count"], 2)

    def test_crime_fields(self):
        resp = self.client.get("/api/crime/?fips=06037")
        r = resp.json()["results"][0]
        for field in ["violent_crimes", "violent_crime_rate",
                      "property_crimes", "property_crime_rate", "population_covered"]:
            self.assertIn(field, r)

    def test_crime_values(self):
        resp = self.client.get("/api/crime/?fips=06037")
        r = resp.json()["results"][0]
        self.assertEqual(r["violent_crimes"], 15234)
        self.assertEqual(r["violent_crime_rate"], "450.1")

    def test_crime_invalid_year_returns_400(self):
        resp = self.client.get("/api/crime/?year=notanumber")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("year", resp.json())


class HudFmrAPITest(TestCase):
    """Tests for /api/housing/."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(GeoEntity)
            editor.create_model(HudFmr)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(HudFmr)
            editor.delete_model(GeoEntity)

    @classmethod
    def setUpTestData(cls):
        GeoEntity.objects.create(fips="06037", geo_type="county",
                                 name="Los Angeles County, California", state_fips="06")
        GeoEntity.objects.create(fips="48201", geo_type="county",
                                 name="Harris County, Texas", state_fips="48")
        HudFmr.objects.create(fips="06037", year=2023,
                              fmr_0br=2079, fmr_1br=2328, fmr_2br=2903, fmr_3br=3681, fmr_4br=4098)
        HudFmr.objects.create(fips="06037", year=2022,
                              fmr_0br=1900, fmr_1br=2100, fmr_2br=2600, fmr_3br=3400, fmr_4br=3900)
        HudFmr.objects.create(fips="48201", year=2023,
                              fmr_0br=990, fmr_1br=1080, fmr_2br=1320, fmr_3br=1720, fmr_4br=2050)

    def test_housing_returns_all(self):
        resp = self.client.get("/api/housing/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 3)

    def test_housing_filter_fips(self):
        resp = self.client.get("/api/housing/?fips=06037")
        data = resp.json()
        self.assertEqual(data["count"], 2)
        for r in data["results"]:
            self.assertEqual(r["fips"], "06037")

    def test_housing_filter_state_fips(self):
        resp = self.client.get("/api/housing/?state_fips=48")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "48201")

    def test_housing_filter_year(self):
        resp = self.client.get("/api/housing/?year=2023")
        self.assertEqual(resp.json()["count"], 2)

    def test_housing_fields(self):
        resp = self.client.get("/api/housing/?fips=06037&year=2023")
        r = resp.json()["results"][0]
        for field in ["fips", "year", "fmr_0br", "fmr_1br", "fmr_2br", "fmr_3br", "fmr_4br"]:
            self.assertIn(field, r)

    def test_housing_values(self):
        resp = self.client.get("/api/housing/?fips=06037&year=2023")
        r = resp.json()["results"][0]
        self.assertEqual(r["fmr_0br"], 2079)
        self.assertEqual(r["fmr_2br"], 2903)

    def test_housing_invalid_year_returns_400(self):
        resp = self.client.get("/api/housing/?year=notanumber")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("year", resp.json())


class DatasetCatalogAPITest(TestCase):
    """Tests for /api/datasets/."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Dataset)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(Dataset)

    @classmethod
    def setUpTestData(cls):
        Dataset.objects.create(
            source_key="census_acs5",
            name="Census ACS 5-Year Estimates",
            description="Population, income, education.",
            source_url="https://api.census.gov/",
            entity_type="county",
            update_cadence="annual",
            row_count=16400,
            null_rates={"median_income": 0.02},
        )
        Dataset.objects.create(
            source_key="cdc_places",
            name="CDC PLACES",
            description="County health outcomes.",
            source_url="https://data.cdc.gov/",
            entity_type="county",
            update_cadence="annual",
            row_count=2956,
            null_rates=None,
        )

    def test_catalog_returns_200(self):
        resp = self.client.get("/api/datasets/")
        self.assertEqual(resp.status_code, 200)

    def test_catalog_returns_all_sources(self):
        resp = self.client.get("/api/datasets/")
        self.assertEqual(resp.json()["count"], 2)

    def test_catalog_fields(self):
        resp = self.client.get("/api/datasets/")
        r = resp.json()["results"][0]
        for field in ["source_key", "name", "description", "source_url",
                      "entity_type", "update_cadence", "row_count", "null_rates"]:
            self.assertIn(field, r)

    def test_catalog_has_row_count(self):
        resp = self.client.get("/api/datasets/")
        results = {r["source_key"]: r for r in resp.json()["results"]}
        self.assertEqual(results["census_acs5"]["row_count"], 16400)

    def test_catalog_has_null_rates(self):
        resp = self.client.get("/api/datasets/")
        results = {r["source_key"]: r for r in resp.json()["results"]}
        self.assertEqual(results["census_acs5"]["null_rates"], {"median_income": 0.02})

    def test_null_rates_null_when_uncomputed(self):
        resp = self.client.get("/api/datasets/")
        results = {r["source_key"]: r for r in resp.json()["results"]}
        self.assertIsNone(results["cdc_places"]["null_rates"])


class EiaEnergyAPITest(TestCase):
    """Tests for /api/energy/."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(GeoEntity)
            editor.create_model(EiaEnergy)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(EiaEnergy)
            editor.delete_model(GeoEntity)

    @classmethod
    def setUpTestData(cls):
        GeoEntity.objects.create(fips="06", geo_type="state", name="California", state_fips="06")
        GeoEntity.objects.create(fips="48", geo_type="state", name="Texas", state_fips="48")
        EiaEnergy.objects.create(
            state_fips="06", year=2022,
            elec_res_bbtu=305518, elec_com_bbtu=371095, elec_ind_bbtu=162354, elec_total_bbtu=843617,
            gas_res_bbtu=464763, gas_com_bbtu=248273, gas_ind_bbtu=743728, gas_total_bbtu=2172757,
        )
        EiaEnergy.objects.create(
            state_fips="48", year=2022,
            elec_res_bbtu=600000, elec_com_bbtu=400000, elec_ind_bbtu=500000, elec_total_bbtu=1500000,
            gas_res_bbtu=300000, gas_com_bbtu=200000, gas_ind_bbtu=800000, gas_total_bbtu=1300000,
        )
        EiaEnergy.objects.create(
            state_fips="06", year=2021,
            elec_res_bbtu=290000, elec_com_bbtu=360000, elec_ind_bbtu=155000, elec_total_bbtu=810000,
            gas_res_bbtu=450000, gas_com_bbtu=240000, gas_ind_bbtu=720000, gas_total_bbtu=2100000,
        )

    def test_energy_returns_all(self):
        resp = self.client.get("/api/energy/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 3)

    def test_energy_filter_state_fips(self):
        resp = self.client.get("/api/energy/?state_fips=06")
        data = resp.json()
        self.assertEqual(data["count"], 2)
        for r in data["results"]:
            self.assertEqual(r["state_fips"], "06")

    def test_energy_filter_year(self):
        resp = self.client.get("/api/energy/?year=2022")
        self.assertEqual(resp.json()["count"], 2)

    def test_energy_fields(self):
        resp = self.client.get("/api/energy/?state_fips=06&year=2022")
        r = resp.json()["results"][0]
        for field in ["state_fips", "year",
                      "elec_res_bbtu", "elec_com_bbtu", "elec_ind_bbtu", "elec_total_bbtu",
                      "gas_res_bbtu", "gas_com_bbtu", "gas_ind_bbtu", "gas_total_bbtu"]:
            self.assertIn(field, r)

    def test_energy_values(self):
        resp = self.client.get("/api/energy/?state_fips=06&year=2022")
        r = resp.json()["results"][0]
        self.assertEqual(r["elec_total_bbtu"], 843617)
        self.assertEqual(r["gas_res_bbtu"], 464763)

    def test_energy_invalid_year_returns_400(self):
        resp = self.client.get("/api/energy/?year=notanumber")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("year", resp.json())


class NhtsaTrafficAPITest(TestCase):
    """Tests for /api/traffic/."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(GeoEntity)
            editor.create_model(NhtsaTraffic)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(NhtsaTraffic)
            editor.delete_model(GeoEntity)

    @classmethod
    def setUpTestData(cls):
        GeoEntity.objects.create(fips="06037", geo_type="county",
                                 name="Los Angeles County, California", state_fips="06")
        GeoEntity.objects.create(fips="48201", geo_type="county",
                                 name="Harris County, Texas", state_fips="48")
        NhtsaTraffic.objects.create(fips="06037", year=2022, fatalities=866, fatality_rate="8.6")
        NhtsaTraffic.objects.create(fips="06037", year=2021, fatalities=820, fatality_rate="8.2")
        NhtsaTraffic.objects.create(fips="48201", year=2022, fatalities=558, fatality_rate="11.8")

    def test_traffic_returns_all(self):
        resp = self.client.get("/api/traffic/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 3)

    def test_traffic_filter_fips(self):
        resp = self.client.get("/api/traffic/?fips=06037")
        data = resp.json()
        self.assertEqual(data["count"], 2)
        for r in data["results"]:
            self.assertEqual(r["fips"], "06037")

    def test_traffic_filter_state_fips(self):
        resp = self.client.get("/api/traffic/?state_fips=48")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "48201")

    def test_traffic_filter_year(self):
        resp = self.client.get("/api/traffic/?year=2022")
        self.assertEqual(resp.json()["count"], 2)

    def test_traffic_fields(self):
        resp = self.client.get("/api/traffic/?fips=06037&year=2022")
        r = resp.json()["results"][0]
        for field in ["fips", "year", "fatalities", "fatality_rate"]:
            self.assertIn(field, r)

    def test_traffic_values(self):
        resp = self.client.get("/api/traffic/?fips=06037&year=2022")
        r = resp.json()["results"][0]
        self.assertEqual(r["fatalities"], 866)
        self.assertEqual(r["fatality_rate"], "8.6")

    def test_traffic_invalid_year_returns_400(self):
        resp = self.client.get("/api/traffic/?year=notanumber")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("year", resp.json())


class EdGraduationAPITest(TestCase):
    """Tests for /api/graduation/."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(GeoEntity)
            editor.create_model(EdGraduation)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(EdGraduation)
            editor.delete_model(GeoEntity)

    @classmethod
    def setUpTestData(cls):
        GeoEntity.objects.create(fips="06037", geo_type="county",
                                 name="Los Angeles County, California", state_fips="06")
        GeoEntity.objects.create(fips="48201", geo_type="county",
                                 name="Harris County, Texas", state_fips="48")
        EdGraduation.objects.create(fips="06037", school_year=2021,
                                    grad_rate_all="82.5", grad_rate_ecd="75.0",
                                    cohort_all=45000, num_districts=28)
        EdGraduation.objects.create(fips="06037", school_year=2020,
                                    grad_rate_all="81.0", grad_rate_ecd="74.0",
                                    cohort_all=44000, num_districts=28)
        EdGraduation.objects.create(fips="48201", school_year=2021,
                                    grad_rate_all="79.3", grad_rate_ecd="71.2",
                                    cohort_all=30000, num_districts=15)

    def test_graduation_returns_all(self):
        resp = self.client.get("/api/graduation/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 3)

    def test_graduation_filter_fips(self):
        resp = self.client.get("/api/graduation/?fips=06037")
        data = resp.json()
        self.assertEqual(data["count"], 2)
        for r in data["results"]:
            self.assertEqual(r["fips"], "06037")

    def test_graduation_filter_state_fips(self):
        resp = self.client.get("/api/graduation/?state_fips=48")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["fips"], "48201")

    def test_graduation_filter_school_year(self):
        resp = self.client.get("/api/graduation/?school_year=2021")
        self.assertEqual(resp.json()["count"], 2)

    def test_graduation_fields(self):
        resp = self.client.get("/api/graduation/?fips=06037&school_year=2021")
        r = resp.json()["results"][0]
        for field in ["fips", "school_year", "grad_rate_all", "grad_rate_ecd",
                      "cohort_all", "num_districts"]:
            self.assertIn(field, r)

    def test_graduation_values(self):
        resp = self.client.get("/api/graduation/?fips=06037&school_year=2021")
        r = resp.json()["results"][0]
        self.assertEqual(r["grad_rate_all"], "82.5")
        self.assertEqual(r["grad_rate_ecd"], "75.0")
        self.assertEqual(r["cohort_all"], 45000)
        self.assertEqual(r["num_districts"], 28)

    def test_graduation_invalid_year_returns_400(self):
        resp = self.client.get("/api/graduation/?school_year=notanumber")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("year", resp.json())
