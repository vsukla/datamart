from django.urls import path, include

urlpatterns = [
    path("api/", include("census.urls")),
    path("dashboard/", include("dashboard.urls")),
]
