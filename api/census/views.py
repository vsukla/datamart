import json
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Prefetch
from django.views.generic import TemplateView
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from .models import GeoEntity, CensusAcs5, AggNationalSummary, AggStateSummary, AggRanking, AggYoY
from .serializers import (
    GeoListSerializer, GeoDetailSerializer, EstimateWithGeoSerializer,
    AggNationalSummarySerializer, AggStateSummarySerializer,
    AggRankingSerializer, AggYoYSerializer,
)

METRIC_LABELS = {
    "median_income":      "Median Income",
    "pct_bachelors":      "Bachelor's Degree (%)",
    "median_home_value":  "Median Home Value",
    "pct_owner_occupied": "Owner-Occupied (%)",
    "pct_poverty":        "Poverty Rate (%)",
    "unemployment_rate":  "Unemployment Rate (%)",
}


class DashboardView(TemplateView):
    template_name = "census/dashboard.html"

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

VALID_GEO_TYPES = {"state", "county"}


def _validate_geo_type(value):
    if value and value not in VALID_GEO_TYPES:
        raise ValidationError({"geo_type": f"Must be one of: {', '.join(sorted(VALID_GEO_TYPES))}."})
    return value


def _validate_year(value):
    if value is not None:
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ValidationError({"year": "Must be an integer."})
    return value


class GeoListView(generics.ListAPIView):
    """
    GET /api/geo/
    Query params: geo_type (state|county), state_fips
    """
    serializer_class = GeoListSerializer

    def get_queryset(self):
        qs = GeoEntity.objects.order_by("fips")
        geo_type = _validate_geo_type(self.request.query_params.get("geo_type"))
        state_fips = self.request.query_params.get("state_fips")
        if geo_type:
            qs = qs.filter(geo_type=geo_type)
        if state_fips:
            qs = qs.filter(state_fips=state_fips)
        return qs


class GeoDetailView(generics.RetrieveAPIView):
    """
    GET /api/geo/<fips>/
    Returns geo metadata plus all ACS5 estimates ordered by year.
    """
    serializer_class = GeoDetailSerializer
    lookup_field = "fips"

    def get_queryset(self):
        return GeoEntity.objects.prefetch_related(
            Prefetch("estimates", queryset=CensusAcs5.objects.order_by("year"))
        )


class EstimatesListView(generics.ListAPIView):
    """
    GET /api/estimates/
    Query params: geo_type (state|county), state_fips, year
    """
    serializer_class = EstimateWithGeoSerializer

    def get_queryset(self):
        qs = CensusAcs5.objects.select_related("geo").order_by("geo_id", "year")
        geo_type = _validate_geo_type(self.request.query_params.get("geo_type"))
        state_fips = self.request.query_params.get("state_fips")
        year = _validate_year(self.request.query_params.get("year"))
        if geo_type:
            qs = qs.filter(geo__geo_type=geo_type)
        if state_fips:
            qs = qs.filter(geo__state_fips=state_fips)
        if year is not None:
            qs = qs.filter(year=year)
        return qs


VALID_METRICS = {
    "median_income", "pct_bachelors", "median_home_value",
    "pct_owner_occupied", "pct_poverty", "unemployment_rate",
}


def _validate_metric(value):
    if value and value not in VALID_METRICS:
        raise ValidationError({"metric": f"Must be one of: {', '.join(sorted(VALID_METRICS))}."})
    return value


class AggNationalSummaryView(generics.ListAPIView):
    """GET /api/aggregates/national/  — optional ?year filter"""
    serializer_class = AggNationalSummarySerializer

    def get_queryset(self):
        qs = AggNationalSummary.objects.all()
        year = _validate_year(self.request.query_params.get("year"))
        if year is not None:
            qs = qs.filter(year=year)
        return qs


class AggStateSummaryView(generics.ListAPIView):
    """GET /api/aggregates/state-summary/  — optional ?state_fips, ?year"""
    serializer_class = AggStateSummarySerializer

    def get_queryset(self):
        qs = AggStateSummary.objects.all()
        state_fips = self.request.query_params.get("state_fips")
        year = _validate_year(self.request.query_params.get("year"))
        if state_fips:
            qs = qs.filter(state_fips=state_fips)
        if year is not None:
            qs = qs.filter(year=year)
        return qs


class AggRankingsView(generics.ListAPIView):
    """GET /api/aggregates/rankings/  — optional ?geo_type, ?state_fips, ?year, ?metric"""
    serializer_class = AggRankingSerializer

    def get_queryset(self):
        qs = AggRanking.objects.all()
        geo_type = _validate_geo_type(self.request.query_params.get("geo_type"))
        state_fips = self.request.query_params.get("state_fips")
        year = _validate_year(self.request.query_params.get("year"))
        metric = _validate_metric(self.request.query_params.get("metric"))
        if geo_type:
            qs = qs.filter(geo_type=geo_type)
        if state_fips:
            qs = qs.filter(state_fips=state_fips)
        if year is not None:
            qs = qs.filter(year=year)
        if metric:
            qs = qs.filter(metric=metric)
        return qs


class AggYoYView(generics.ListAPIView):
    """GET /api/aggregates/yoy/  — optional ?geo_type, ?state_fips, ?year, ?metric"""
    serializer_class = AggYoYSerializer

    def get_queryset(self):
        qs = AggYoY.objects.all()
        geo_type = _validate_geo_type(self.request.query_params.get("geo_type"))
        state_fips = self.request.query_params.get("state_fips")
        year = _validate_year(self.request.query_params.get("year"))
        metric = _validate_metric(self.request.query_params.get("metric"))
        if geo_type:
            qs = qs.filter(geo_type=geo_type)
        if state_fips:
            qs = qs.filter(state_fips=state_fips)
        if year is not None:
            qs = qs.filter(year=year)
        if metric:
            qs = qs.filter(metric=metric)
        return qs
