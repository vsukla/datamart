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
