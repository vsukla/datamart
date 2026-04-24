from django.db.models import Prefetch
from rest_framework import generics
from .models import GeoEntity, CensusAcs5
from .serializers import GeoListSerializer, GeoDetailSerializer, EstimateWithGeoSerializer


class GeoListView(generics.ListAPIView):
    """
    GET /api/geo/
    Query params: geo_type (state|county), state_fips
    """
    serializer_class = GeoListSerializer

    def get_queryset(self):
        qs = GeoEntity.objects.order_by("fips")
        geo_type = self.request.query_params.get("geo_type")
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
        geo_type = self.request.query_params.get("geo_type")
        state_fips = self.request.query_params.get("state_fips")
        year = self.request.query_params.get("year")
        if geo_type:
            qs = qs.filter(geo__geo_type=geo_type)
        if state_fips:
            qs = qs.filter(geo__state_fips=state_fips)
        if year:
            qs = qs.filter(year=year)
        return qs
