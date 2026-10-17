from django.contrib import admin

from .models import ConnectionRequest


@admin.register(ConnectionRequest)
class ConnectionRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "from_device", "to_device", "status", "created_at", "responded_at")
    list_filter = ("status",)
    readonly_fields = [f.name for f in ConnectionRequest._meta.fields]

    def has_add_permission(self, request):
        return False
