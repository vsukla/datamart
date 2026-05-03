from django.urls import path, include
from dashboard.views import ProfileView

urlpatterns = [
    path("api/", include("census.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("profile/<str:fips>/", ProfileView.as_view()),
]
