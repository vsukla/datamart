from rest_framework import serializers
from .models import (
    Dataset,
    GeoEntity, CensusAcs5, AggNationalSummary, AggStateSummary, AggRanking, AggYoY,
    CdcPlaces, BlsLaus, UsdaFoodEnv, EpaAqi, FbiCrime, HudFmr, EiaEnergy,
    NhtsaTraffic, EdGraduation, CountyProfile,
)


class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = [
            "source_key", "name", "description", "source_url",
            "entity_type", "update_cadence",
            "row_count", "null_rates", "last_ingested_at", "quality_computed_at",
        ]


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
            "pct_health_insured",
            "mean_commute_minutes",
            "pct_white",
            "pct_black",
            "pct_hispanic",
            "pct_asian",
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
            "pct_health_insured",
            "mean_commute_minutes",
            "pct_white",
            "pct_black",
            "pct_hispanic",
            "pct_asian",
            "fetched_at",
        ]


class CdcPlacesSerializer(serializers.ModelSerializer):
    class Meta:
        model = CdcPlaces
        fields = [
            "fips", "year",
            "pct_obesity", "pct_diabetes", "pct_smoking", "pct_hypertension",
            "pct_depression", "pct_no_lpa", "pct_poor_mental_health",
            "fetched_at",
        ]


class BlsLausSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlsLaus
        fields = [
            "fips", "year",
            "labor_force", "employed", "unemployed", "unemployment_rate",
            "fetched_at",
        ]


class UsdaFoodEnvSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsdaFoodEnv
        fields = [
            "fips", "data_year",
            "pct_low_food_access", "groceries_per_1000", "fast_food_per_1000",
            "pct_snap", "farmers_markets",
            "fetched_at",
        ]


class EpaAqiSerializer(serializers.ModelSerializer):
    class Meta:
        model = EpaAqi
        fields = [
            "fips", "year",
            "days_with_aqi", "good_days", "moderate_days",
            "unhealthy_sensitive_days", "unhealthy_days", "very_unhealthy_days",
            "hazardous_days", "max_aqi", "median_aqi", "pm25_days", "ozone_days",
            "fetched_at",
        ]


class FbiCrimeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FbiCrime
        fields = [
            "fips", "year",
            "population_covered",
            "violent_crimes", "violent_crime_rate",
            "property_crimes", "property_crime_rate",
            "fetched_at",
        ]


class HudFmrSerializer(serializers.ModelSerializer):
    class Meta:
        model = HudFmr
        fields = [
            "fips", "year",
            "fmr_0br", "fmr_1br", "fmr_2br", "fmr_3br", "fmr_4br",
            "fetched_at",
        ]


class NhtsaTrafficSerializer(serializers.ModelSerializer):
    class Meta:
        model = NhtsaTraffic
        fields = ["fips", "year", "fatalities", "fatality_rate", "fetched_at"]


class EiaEnergySerializer(serializers.ModelSerializer):
    class Meta:
        model = EiaEnergy
        fields = [
            "state_fips", "year",
            "elec_res_bbtu", "elec_com_bbtu", "elec_ind_bbtu", "elec_total_bbtu",
            "gas_res_bbtu", "gas_com_bbtu", "gas_ind_bbtu", "gas_total_bbtu",
            "fetched_at",
        ]


class EdGraduationSerializer(serializers.ModelSerializer):
    class Meta:
        model = EdGraduation
        fields = [
            "fips", "school_year",
            "grad_rate_all", "grad_rate_ecd",
            "cohort_all", "num_districts",
            "fetched_at",
        ]


class CountyProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CountyProfile
        fields = [
            "fips", "county_name", "state_fips",
            "census_year", "population", "median_income", "pct_bachelors",
            "median_home_value", "pct_owner_occupied", "pct_poverty",
            "census_unemployment_rate",
            "pct_health_insured", "mean_commute_minutes",
            "pct_white", "pct_black", "pct_hispanic", "pct_asian",
            "places_year", "pct_obesity", "pct_diabetes", "pct_smoking",
            "pct_hypertension", "pct_depression", "pct_no_lpa", "pct_poor_mental_health",
            "bls_year", "labor_force", "employed", "unemployed", "bls_unemployment_rate",
            "usda_year", "pct_low_food_access", "groceries_per_1000", "fast_food_per_1000",
            "pct_snap", "farmers_markets",
            "aqi_year", "median_aqi", "max_aqi", "good_days", "moderate_days",
            "unhealthy_sensitive_days", "unhealthy_days", "very_unhealthy_days",
            "hazardous_days", "pm25_days", "ozone_days",
            "crime_year", "violent_crimes", "violent_crime_rate",
            "property_crimes", "property_crime_rate",
            "traffic_year", "fatalities", "fatality_rate",
            "hud_year", "fmr_0br", "fmr_1br", "fmr_2br", "fmr_3br", "fmr_4br",
            "grad_year", "grad_rate_all", "grad_rate_ecd", "cohort_all", "num_districts",
        ]
