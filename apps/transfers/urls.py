from django.urls import path

from . import views

app_name = "transfers"

urlpatterns = [
    path("log/", views.log_transfer, name="log"),
]
