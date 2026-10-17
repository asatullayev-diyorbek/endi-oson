from django.contrib import admin
from django.urls import include, path

from apps.accounts import views as accounts_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/telegram/", include("apps.telegram_auth.urls")),
    path("", accounts_views.home, name="home"),
]
