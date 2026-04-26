from rest_framework import serializers
from .models import GeoEntity, CensusAcs5, AggNationalSummary, AggStateSummary, AggRanking, AggYoY


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


class AggNationalSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = AggNationalSummary
        fields = [
            "year", "total_population",
            "avg_median_income", "avg_pct_bachelors", "avg_median_home_value",
            "avg_pct_owner_occupied", "avg_pct_poverty", "avg_unemployment_rate",
            "computed_at",
        ]


class AggStateSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = AggStateSummary
        fields = [
            "state_fips", "year", "total_population",
            "avg_median_income", "avg_pct_bachelors", "avg_median_home_value",
            "avg_pct_owner_occupied", "avg_pct_poverty", "avg_unemployment_rate",
            "computed_at",
        ]


class AggRankingSerializer(serializers.ModelSerializer):
    class Meta:
        model = AggRanking
        fields = [
            "fips", "state_fips", "geo_type", "year", "metric",
            "value", "rank", "percentile", "peer_count", "computed_at",
        ]


class AggYoYSerializer(serializers.ModelSerializer):
    class Meta:
        model = AggYoY
        fields = [
            "fips", "state_fips", "geo_type", "year", "metric",
            "value", "prev_value", "change_abs", "change_pct", "computed_at",
        ]


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
