from django.db import models


class Dataset(models.Model):
    source_key = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    source_url = models.TextField(blank=True, null=True)
    entity_type = models.CharField(max_length=20, default="county")
    update_cadence = models.CharField(max_length=20, blank=True, null=True)
    row_count = models.IntegerField(null=True)
    null_rates = models.JSONField(null=True)
    last_ingested_at = models.DateTimeField(null=True)
    quality_computed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "datasets"
        managed = False
        ordering = ["source_key"]


class GeoEntity(models.Model):
    GEO_TYPE_CHOICES = [("state", "State"), ("county", "County")]

    fips = models.CharField(max_length=5, primary_key=True)
    geo_type = models.CharField(max_length=10, choices=GEO_TYPE_CHOICES)
    name = models.CharField(max_length=200)
    state_fips = models.CharField(max_length=2)

    class Meta:
        db_table = "geo_entities"
        managed = False

    def __str__(self):
        return f"{self.name} ({self.fips})"


class CensusAcs5(models.Model):
    geo = models.ForeignKey(
        GeoEntity,
        on_delete=models.CASCADE,
        db_column="fips",
        related_name="estimates",
    )
    year = models.SmallIntegerField()
    population = models.IntegerField(null=True)
    median_income = models.IntegerField(null=True)
    pct_bachelors = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    median_home_value = models.IntegerField(null=True)
    pct_owner_occupied = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pct_poverty = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    unemployment_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pct_health_insured = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    mean_commute_minutes = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_white = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pct_black = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pct_hispanic = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pct_asian = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    fetched_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "census_acs5"
        managed = False
        ordering = ["year"]


class AggNationalSummary(models.Model):
    year = models.SmallIntegerField(unique=True)
    total_population = models.BigIntegerField(null=True)
    avg_median_income = models.DecimalField(max_digits=10, decimal_places=0, null=True)
    avg_pct_bachelors = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_median_home_value = models.DecimalField(max_digits=10, decimal_places=0, null=True)
    avg_pct_owner_occupied = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_pct_poverty = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_unemployment_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    computed_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "agg_national_summary"
        managed = False
        ordering = ["year"]


class AggStateSummary(models.Model):
    state_fips = models.CharField(max_length=2)
    year = models.SmallIntegerField()
    total_population = models.BigIntegerField(null=True)
    avg_median_income = models.DecimalField(max_digits=10, decimal_places=0, null=True)
    avg_pct_bachelors = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_median_home_value = models.DecimalField(max_digits=10, decimal_places=0, null=True)
    avg_pct_owner_occupied = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_pct_poverty = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_unemployment_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    computed_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "agg_state_summary"
        managed = False
        ordering = ["state_fips", "year"]


class AggRanking(models.Model):
    fips = models.CharField(max_length=5)
    state_fips = models.CharField(max_length=2)
    geo_type = models.CharField(max_length=10)
    year = models.SmallIntegerField()
    metric = models.CharField(max_length=30)
    value = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    rank = models.IntegerField(null=True)
    percentile = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    peer_count = models.IntegerField(null=True)
    computed_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "agg_rankings"
        managed = False
        ordering = ["geo_type", "year", "metric", "rank"]


class AggYoY(models.Model):
    fips = models.CharField(max_length=5)
    state_fips = models.CharField(max_length=2)
    geo_type = models.CharField(max_length=10)
    year = models.SmallIntegerField()
    metric = models.CharField(max_length=30)
    value = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    prev_value = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    change_abs = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    change_pct = models.DecimalField(max_digits=7, decimal_places=2, null=True)
    computed_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "agg_yoy"
        managed = False
        ordering = ["fips", "metric", "year"]


class CdcPlaces(models.Model):
    fips = models.CharField(max_length=5)
    year = models.SmallIntegerField()
    pct_obesity = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_diabetes = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_smoking = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_hypertension = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_depression = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_no_lpa = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_poor_mental_health = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    fetched_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "cdc_places"
        managed = False
        ordering = ["fips", "year"]


class BlsLaus(models.Model):
    fips = models.CharField(max_length=5)
    year = models.SmallIntegerField()
    labor_force = models.IntegerField(null=True)
    employed = models.IntegerField(null=True)
    unemployed = models.IntegerField(null=True)
    unemployment_rate = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    fetched_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "bls_laus"
        managed = False
        ordering = ["fips", "year"]


class UsdaFoodEnv(models.Model):
    fips = models.CharField(max_length=5)
    data_year = models.SmallIntegerField()
    pct_low_food_access = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    groceries_per_1000 = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    fast_food_per_1000 = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    pct_snap = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    farmers_markets = models.IntegerField(null=True)
    fetched_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "usda_food_env"
        managed = False
        ordering = ["fips", "data_year"]


class EpaAqi(models.Model):
    fips = models.CharField(max_length=5)
    year = models.SmallIntegerField()
    days_with_aqi = models.SmallIntegerField(null=True)
    good_days = models.SmallIntegerField(null=True)
    moderate_days = models.SmallIntegerField(null=True)
    unhealthy_sensitive_days = models.SmallIntegerField(null=True)
    unhealthy_days = models.SmallIntegerField(null=True)
    very_unhealthy_days = models.SmallIntegerField(null=True)
    hazardous_days = models.SmallIntegerField(null=True)
    max_aqi = models.SmallIntegerField(null=True)
    median_aqi = models.DecimalField(max_digits=6, decimal_places=1, null=True)
    pm25_days = models.SmallIntegerField(null=True)
    ozone_days = models.SmallIntegerField(null=True)
    fetched_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "epa_aqi"
        managed = False
        ordering = ["fips", "year"]


class FbiCrime(models.Model):
    fips = models.CharField(max_length=5)
    year = models.SmallIntegerField()
    population_covered = models.IntegerField(null=True)
    violent_crimes = models.IntegerField(null=True)
    violent_crime_rate = models.DecimalField(max_digits=8, decimal_places=1, null=True)
    property_crimes = models.IntegerField(null=True)
    property_crime_rate = models.DecimalField(max_digits=8, decimal_places=1, null=True)
    fetched_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "fbi_crime"
        managed = False
        ordering = ["fips", "year"]


class NhtsaTraffic(models.Model):
    fips = models.CharField(max_length=5)
    year = models.SmallIntegerField()
    fatalities = models.IntegerField()
    fatality_rate = models.DecimalField(max_digits=6, decimal_places=1, null=True)
    fetched_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "nhtsa_traffic"
        managed = False
        ordering = ["fips", "year"]


class EiaEnergy(models.Model):
    state_fips = models.CharField(max_length=2)
    year = models.SmallIntegerField()
    elec_res_bbtu = models.IntegerField(null=True)
    elec_com_bbtu = models.IntegerField(null=True)
    elec_ind_bbtu = models.IntegerField(null=True)
    elec_total_bbtu = models.IntegerField(null=True)
    gas_res_bbtu = models.IntegerField(null=True)
    gas_com_bbtu = models.IntegerField(null=True)
    gas_ind_bbtu = models.IntegerField(null=True)
    gas_total_bbtu = models.IntegerField(null=True)
    fetched_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "eia_energy"
        managed = False
        ordering = ["state_fips", "year"]


class HudFmr(models.Model):
    fips = models.CharField(max_length=5)
    year = models.SmallIntegerField()
    fmr_0br = models.IntegerField(null=True)
    fmr_1br = models.IntegerField(null=True)
    fmr_2br = models.IntegerField(null=True)
    fmr_3br = models.IntegerField(null=True)
    fmr_4br = models.IntegerField(null=True)
    fetched_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "hud_fmr"
        managed = False
        ordering = ["fips", "year"]


class EdGraduation(models.Model):
    fips = models.CharField(max_length=5)
    school_year = models.SmallIntegerField()
    grad_rate_all = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    grad_rate_ecd = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    cohort_all = models.IntegerField(null=True)
    num_districts = models.SmallIntegerField(null=True)
    fetched_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "ed_graduation"
        managed = False
        ordering = ["fips", "school_year"]


class CountyProfile(models.Model):
    """Read-only view joining all county-level data sources."""
    fips = models.CharField(max_length=5, primary_key=True)
    county_name = models.CharField(max_length=200)
    state_fips = models.CharField(max_length=2)
    # Census ACS5
    census_year = models.SmallIntegerField(null=True)
    population = models.IntegerField(null=True)
    median_income = models.IntegerField(null=True)
    pct_bachelors = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    median_home_value = models.IntegerField(null=True)
    pct_owner_occupied = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pct_poverty = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    census_unemployment_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pct_health_insured = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    mean_commute_minutes = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_white = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pct_black = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pct_hispanic = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pct_asian = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    # CDC PLACES
    places_year = models.SmallIntegerField(null=True)
    pct_obesity = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_diabetes = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_smoking = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_hypertension = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_depression = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_no_lpa = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    pct_poor_mental_health = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    # BLS LAUS
    bls_year = models.SmallIntegerField(null=True)
    labor_force = models.IntegerField(null=True)
    employed = models.IntegerField(null=True)
    unemployed = models.IntegerField(null=True)
    bls_unemployment_rate = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    # USDA Food Environment
    usda_year = models.SmallIntegerField(null=True)
    pct_low_food_access = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    groceries_per_1000 = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    fast_food_per_1000 = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    pct_snap = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    farmers_markets = models.IntegerField(null=True)
    # EPA AQI
    aqi_year = models.SmallIntegerField(null=True)
    median_aqi = models.DecimalField(max_digits=6, decimal_places=1, null=True)
    max_aqi = models.SmallIntegerField(null=True)
    good_days = models.SmallIntegerField(null=True)
    moderate_days = models.SmallIntegerField(null=True)
    unhealthy_sensitive_days = models.SmallIntegerField(null=True)
    unhealthy_days = models.SmallIntegerField(null=True)
    very_unhealthy_days = models.SmallIntegerField(null=True)
    hazardous_days = models.SmallIntegerField(null=True)
    pm25_days = models.SmallIntegerField(null=True)
    ozone_days = models.SmallIntegerField(null=True)
    # FBI Crime
    crime_year = models.SmallIntegerField(null=True)
    violent_crimes = models.IntegerField(null=True)
    violent_crime_rate = models.DecimalField(max_digits=8, decimal_places=1, null=True)
    property_crimes = models.IntegerField(null=True)
    property_crime_rate = models.DecimalField(max_digits=8, decimal_places=1, null=True)
    # NHTSA Traffic Fatalities
    traffic_year = models.SmallIntegerField(null=True)
    fatalities = models.IntegerField(null=True)
    fatality_rate = models.DecimalField(max_digits=6, decimal_places=1, null=True)
    # HUD Fair Market Rents
    hud_year = models.SmallIntegerField(null=True)
    fmr_0br = models.IntegerField(null=True)
    fmr_1br = models.IntegerField(null=True)
    fmr_2br = models.IntegerField(null=True)
    fmr_3br = models.IntegerField(null=True)
    fmr_4br = models.IntegerField(null=True)
    # Education Graduation Rates
    grad_year = models.SmallIntegerField(null=True)
    grad_rate_all = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    grad_rate_ecd = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    cohort_all = models.IntegerField(null=True)
    num_districts = models.SmallIntegerField(null=True)

    class Meta:
        db_table = "county_profile"
        managed = False
        ordering = ["fips"]
