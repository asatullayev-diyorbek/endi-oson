from django.conf import settings
from django.db import models


class Device(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices"
    )
    device_label = models.CharField(max_length=128, default="Noma'lum qurilma")
    channel_name = models.CharField(max_length=255, null=True, blank=True)
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_seen"]

    def __str__(self):
        return f"{self.device_label} ({self.user_id})"
