from django.urls import path
from .views import GeoListView, GeoDetailView, EstimatesListView

urlpatterns = [
    path("geo/", GeoListView.as_view()),
    path("geo/<str:fips>/", GeoDetailView.as_view()),
    path("estimates/", EstimatesListView.as_view()),
]
