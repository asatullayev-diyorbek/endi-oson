from django.db import models

from apps.devices.models import Device


class ConnectionRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_TIMEOUT = "timeout"
    STATUS_CHOICES = [
        (STATUS_PENDING, "pending"),
        (STATUS_ACCEPTED, "accepted"),
        (STATUS_REJECTED, "rejected"),
        (STATUS_TIMEOUT, "timeout"),
    ]

    from_device = models.ForeignKey(
        Device, related_name="sent_requests", on_delete=models.CASCADE
    )
    to_device = models.ForeignKey(
        Device, related_name="received_requests", on_delete=models.CASCADE
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.from_device_id} -> {self.to_device_id} ({self.status})"
