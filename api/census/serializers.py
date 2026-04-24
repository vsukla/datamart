from rest_framework import serializers
from .models import GeoEntity, CensusAcs5


class EstimateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CensusAcs5
        fields = [
            "year",
            "population",
            "median_income",
            "pct_bachelors",
            "median_home_value",
            "pct_owner_occupied",
            "pct_poverty",
            "unemployment_rate",
            "fetched_at",
        ]


class GeoListSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeoEntity
        fields = ["fips", "geo_type", "name", "state_fips"]


class GeoDetailSerializer(serializers.ModelSerializer):
    estimates = EstimateSerializer(many=True, read_only=True)

    class Meta:
        model = GeoEntity
        fields = ["fips", "geo_type", "name", "state_fips", "estimates"]


class EstimateWithGeoSerializer(serializers.ModelSerializer):
    fips = serializers.CharField(source="geo_id")
    geo_name = serializers.CharField(source="geo.name")
    geo_type = serializers.CharField(source="geo.geo_type")
    state_fips = serializers.CharField(source="geo.state_fips")

    class Meta:
        model = CensusAcs5
        fields = [
            "fips",
            "geo_name",
            "geo_type",
            "state_fips",
            "year",
            "population",
            "median_income",
            "pct_bachelors",
            "median_home_value",
            "pct_owner_occupied",
            "pct_poverty",
            "unemployment_rate",
            "fetched_at",
        ]
