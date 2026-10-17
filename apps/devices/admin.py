from django.contrib import admin

from .models import Device


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "device_label", "is_online", "last_seen")
    list_filter = ("is_online",)
    search_fields = ("device_label", "user__telegram_user_id")
