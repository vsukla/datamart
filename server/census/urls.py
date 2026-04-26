from django.urls import path
from .views import (
    GeoListView, GeoDetailView, EstimatesListView,
    AggNationalSummaryView, AggStateSummaryView, AggRankingsView, AggYoYView,
)

urlpatterns = [
    path("geo/", GeoListView.as_view()),
    path("geo/<str:fips>/", GeoDetailView.as_view()),
    path("estimates/", EstimatesListView.as_view()),
    path("aggregates/national/", AggNationalSummaryView.as_view()),
    path("aggregates/state-summary/", AggStateSummaryView.as_view()),
    path("aggregates/rankings/", AggRankingsView.as_view()),
    path("aggregates/yoy/", AggYoYView.as_view()),
]
