from django.db import models


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
