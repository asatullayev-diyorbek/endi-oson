from django.urls import path

from . import views

app_name = "telegram_auth"

urlpatterns = [
    path("login/", views.login_page, name="login_page"),
    path("start/", views.start, name="start"),
    path("poll/<int:attempt_id>/", views.poll, name="poll"),
    path("complete/<int:attempt_id>/", views.complete, name="complete"),
]
