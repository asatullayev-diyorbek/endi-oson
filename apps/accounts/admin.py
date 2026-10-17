from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    model = User
    ordering = ("-created_at",)
    list_display = ("telegram_user_id", "telegram_username", "display_name", "is_staff", "created_at")
    search_fields = ("telegram_user_id", "telegram_username", "display_name")
    readonly_fields = ("created_at", "last_login")
    fieldsets = (
        (None, {"fields": ("telegram_user_id", "password")}),
        ("Profil", {"fields": ("telegram_username", "display_name")}),
        (
            "Ruxsatlar",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Sanalar", {"fields": ("last_login", "created_at")}),
    )
    add_fieldsets = (
        (None, {"fields": ("telegram_user_id", "password1", "password2")}),
    )
