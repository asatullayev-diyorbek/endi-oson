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


class TransferLog(models.Model):
    """Fayl uzatish urinishining meta-ma'lumot jurnali.

    DIQQAT: fayl baytlari bu yerda HECH QACHON saqlanmaydi/oqib o'tmaydi —
    faqat nom/hajm va lokal-only tekshiruv natijasi.
    """

    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_REJECTED_NON_LOCAL = "rejected_non_local"
    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, "in_progress"),
        (STATUS_COMPLETED, "completed"),
        (STATUS_FAILED, "failed"),
        (STATUS_REJECTED_NON_LOCAL, "rejected_non_local"),
    ]

    connection = models.ForeignKey(
        ConnectionRequest, related_name="transfer_logs", on_delete=models.CASCADE
    )
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    local_verified = models.BooleanField(default=False)
    reason = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"TransferLog({self.connection_id}, {self.status})"
