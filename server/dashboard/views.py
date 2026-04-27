import json
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Avg, Q
from django.db.models.functions import Substr
from django.views.generic import TemplateView
from census.models import GeoEntity, AggNationalSummary, AggStateSummary, AggYoY, CdcPlaces, UsdaFoodEnv

METRIC_LABELS = {
    "median_income":      "Median Income",
    "pct_bachelors":      "Bachelor's Degree (%)",
    "median_home_value":  "Median Home Value",
    "pct_owner_occupied": "Owner-Occupied (%)",
    "pct_poverty":        "Poverty Rate (%)",
    "unemployment_rate":  "Unemployment Rate (%)",
}

HEALTH_METRIC_LABELS = {
    "pct_obesity":            "Obesity (%)",
    "pct_diabetes":           "Diabetes (%)",
    "pct_smoking":            "Current Smoking (%)",
    "pct_hypertension":       "High Blood Pressure (%)",
    "pct_depression":         "Depression (%)",
    "pct_no_lpa":             "No Physical Activity (%)",
    "pct_poor_mental_health": "Poor Mental Health (%)",
}

FOOD_METRIC_LABELS = {
    "pct_low_food_access": "Low Food Access (%)",
    "groceries_per_1000":  "Grocery Stores per 1,000",
    "fast_food_per_1000":  "Fast Food per 1,000",
    "pct_snap":            "SNAP Participation (%)",
    "farmers_markets":     "Farmers Markets (count)",
}


class DashboardView(TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        national = list(AggNationalSummary.objects.order_by("year").values(
            "year", "avg_median_income", "avg_pct_bachelors", "avg_median_home_value",
            "avg_pct_owner_occupied", "avg_pct_poverty", "avg_unemployment_rate",
        ))

        state_summary = list(AggStateSummary.objects.order_by("state_fips", "year").values(
            "state_fips", "year", "avg_median_income", "avg_pct_bachelors",
            "avg_median_home_value", "avg_pct_owner_occupied", "avg_pct_poverty",
            "avg_unemployment_rate",
        ))

        yoy = list(AggYoY.objects.filter(geo_type="state").values(
            "fips", "state_fips", "year", "metric", "value", "change_abs", "change_pct",
        ))

        state_names = {
            g.fips: g.name
            for g in GeoEntity.objects.filter(geo_type="state").order_by("name")
        }

        state_health = list(
            CdcPlaces.objects
            .values(state_fips=Substr("fips", 1, 2))
            .annotate(
                avg_pct_obesity=Avg("pct_obesity"),
                avg_pct_diabetes=Avg("pct_diabetes"),
                avg_pct_smoking=Avg("pct_smoking"),
                avg_pct_hypertension=Avg("pct_hypertension"),
                avg_pct_depression=Avg("pct_depression"),
                avg_pct_no_lpa=Avg("pct_no_lpa"),
                avg_pct_poor_mental_health=Avg("pct_poor_mental_health"),
            )
            .order_by("state_fips")
        )

        state_food = list(
            UsdaFoodEnv.objects
            .values(state_fips=Substr("fips", 1, 2))
            .annotate(
                avg_pct_low_food_access=Avg("pct_low_food_access", filter=Q(pct_low_food_access__gte=0)),
                avg_groceries_per_1000=Avg("groceries_per_1000",   filter=Q(groceries_per_1000__gte=0)),
                avg_fast_food_per_1000=Avg("fast_food_per_1000",   filter=Q(fast_food_per_1000__gte=0)),
                avg_pct_snap=Avg("pct_snap",                       filter=Q(pct_snap__gte=0)),
                avg_farmers_markets=Avg("farmers_markets",         filter=Q(farmers_markets__gte=0)),
            )
            .order_by("state_fips")
        )

        ctx.update({
            "national_json":             json.dumps(national, cls=DjangoJSONEncoder),
            "state_summary_json":        json.dumps(state_summary, cls=DjangoJSONEncoder),
            "yoy_json":                  json.dumps(yoy, cls=DjangoJSONEncoder),
            "state_names_json":          json.dumps(state_names),
            "state_health_json":         json.dumps(state_health, cls=DjangoJSONEncoder),
            "state_food_json":           json.dumps(state_food, cls=DjangoJSONEncoder),
            "metric_labels_json":        json.dumps(METRIC_LABELS),
            "health_metric_labels_json": json.dumps(HEALTH_METRIC_LABELS),
            "food_metric_labels_json":   json.dumps(FOOD_METRIC_LABELS),
            "metric_groups": [
                {"label": "Census ACS5",        "metrics": METRIC_LABELS},
                {"label": "Health — CDC PLACES", "metrics": HEALTH_METRIC_LABELS},
                {"label": "Food — USDA Atlas",   "metrics": FOOD_METRIC_LABELS},
            ],
            "years": list(range(2018, 2023)),
        })
        return ctx
