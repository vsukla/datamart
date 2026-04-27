from django.db.models import Prefetch
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from .models import (
    GeoEntity, CensusAcs5, AggNationalSummary, AggStateSummary, AggRanking, AggYoY,
    CdcPlaces, BlsLaus, UsdaFoodEnv, CountyProfile,
)
from .serializers import (
    GeoListSerializer, GeoDetailSerializer, EstimateWithGeoSerializer,
    AggNationalSummarySerializer, AggStateSummarySerializer,
    AggRankingSerializer, AggYoYSerializer,
    CdcPlacesSerializer, BlsLausSerializer, UsdaFoodEnvSerializer, CountyProfileSerializer,
)

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


class CdcPlacesView(generics.ListAPIView):
    """GET /api/health/  — optional ?fips, ?state_fips, ?year"""
    serializer_class = CdcPlacesSerializer

    def get_queryset(self):
        qs = CdcPlaces.objects.all()
        fips = self.request.query_params.get("fips")
        state_fips = self.request.query_params.get("state_fips")
        year = _validate_year(self.request.query_params.get("year"))
        if fips:
            qs = qs.filter(fips=fips)
        if state_fips:
            qs = qs.filter(fips__startswith=state_fips)
        if year is not None:
            qs = qs.filter(year=year)
        return qs


class BlsLausView(generics.ListAPIView):
    """GET /api/labor/  — optional ?fips, ?state_fips, ?year"""
    serializer_class = BlsLausSerializer

    def get_queryset(self):
        qs = BlsLaus.objects.all()
        fips = self.request.query_params.get("fips")
        state_fips = self.request.query_params.get("state_fips")
        year = _validate_year(self.request.query_params.get("year"))
        if fips:
            qs = qs.filter(fips=fips)
        if state_fips:
            qs = qs.filter(fips__startswith=state_fips)
        if year is not None:
            qs = qs.filter(year=year)
        return qs


class UsdaFoodEnvView(generics.ListAPIView):
    """GET /api/food/  — optional ?fips, ?state_fips, ?data_year"""
    serializer_class = UsdaFoodEnvSerializer

    def get_queryset(self):
        qs = UsdaFoodEnv.objects.all()
        fips = self.request.query_params.get("fips")
        state_fips = self.request.query_params.get("state_fips")
        data_year = _validate_year(self.request.query_params.get("data_year"))
        if fips:
            qs = qs.filter(fips=fips)
        if state_fips:
            qs = qs.filter(fips__startswith=state_fips)
        if data_year is not None:
            qs = qs.filter(data_year=data_year)
        return qs


class CountyProfileView(generics.ListAPIView):
    """GET /api/profile/  — optional ?fips, ?state_fips"""
    serializer_class = CountyProfileSerializer

    def get_queryset(self):
        qs = CountyProfile.objects.all()
        fips = self.request.query_params.get("fips")
        state_fips = self.request.query_params.get("state_fips")
        if fips:
            qs = qs.filter(fips=fips)
        if state_fips:
            qs = qs.filter(state_fips=state_fips)
        return qs
