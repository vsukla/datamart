import json
from django.core.serializers.json import DjangoJSONEncoder
from django.views.generic import TemplateView
from census.models import GeoEntity, AggNationalSummary, AggStateSummary, AggYoY

METRIC_LABELS = {
    "median_income":      "Median Income",
    "pct_bachelors":      "Bachelor's Degree (%)",
    "median_home_value":  "Median Home Value",
    "pct_owner_occupied": "Owner-Occupied (%)",
    "pct_poverty":        "Poverty Rate (%)",
    "unemployment_rate":  "Unemployment Rate (%)",
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

        ctx.update({
            "national_json":      json.dumps(national, cls=DjangoJSONEncoder),
            "state_summary_json": json.dumps(state_summary, cls=DjangoJSONEncoder),
            "yoy_json":           json.dumps(yoy, cls=DjangoJSONEncoder),
            "state_names_json":   json.dumps(state_names),
            "metric_labels_json": json.dumps(METRIC_LABELS),
            "metric_labels":      METRIC_LABELS,
            "years":              list(range(2018, 2023)),
        })
        return ctx
