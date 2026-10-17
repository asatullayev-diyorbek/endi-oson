from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.devices.models import Device

from .models import ConnectionRequest, TransferLog


class ConnectionRequestError(Exception):
    """Ulanish so'rovini yaratish/javob berish mumkin bo'lmaganda ko'tariladi."""


def create_connection_request(from_device: Device, to_device_id) -> ConnectionRequest:
    to_device = (
        Device.objects.filter(id=to_device_id, is_online=True)
        .exclude(id=from_device.id)
        .first()
    )
    if not to_device:
        raise ConnectionRequestError("Qurilma topilmadi yoki hozir onlayn emas")

    return ConnectionRequest.objects.create(from_device=from_device, to_device=to_device)


@transaction.atomic
def respond_to_connection_request(
    request_id, responder_device: Device, accept: bool
) -> ConnectionRequest:
    try:
        request = ConnectionRequest.objects.select_for_update().get(
            id=request_id, to_device=responder_device
        )
    except ConnectionRequest.DoesNotExist as exc:
        raise ConnectionRequestError("So'rov topilmadi") from exc

    if request.status != ConnectionRequest.STATUS_PENDING:
        raise ConnectionRequestError("So'rov allaqachon yakunlangan")

    request.status = (
        ConnectionRequest.STATUS_ACCEPTED if accept else ConnectionRequest.STATUS_REJECTED
    )
    request.responded_at = timezone.now()
    request.save(update_fields=["status", "responded_at"])
    return request


@transaction.atomic
def expire_if_still_pending(request_id):
    """30 soniyalik timeout tugaganda chaqiriladi — faqat hali 'pending' bo'lsa yakunlaydi."""
    try:
        request = ConnectionRequest.objects.select_for_update().get(id=request_id)
    except ConnectionRequest.DoesNotExist:
        return None

    if request.status != ConnectionRequest.STATUS_PENDING:
        return None

    request.status = ConnectionRequest.STATUS_TIMEOUT
    request.responded_at = timezone.now()
    request.save(update_fields=["status", "responded_at"])
    return request


def get_accepted_connection(request_id, device: Device) -> ConnectionRequest:
    """Signaling (5-bosqich) faqat tasdiqlangan ulanish doirasida ishlashi uchun.

    `device` so'ralgan ConnectionRequest'ning ikki tarafidan biri bo'lishi
    shart — aks holda begona qurilma boshqa birovlar orasiga signaling
    xabari in'ektsiya qila olmasligi kerak.
    """
    try:
        connection = ConnectionRequest.objects.get(
            id=request_id, status=ConnectionRequest.STATUS_ACCEPTED
        )
    except ConnectionRequest.DoesNotExist as exc:
        raise ConnectionRequestError("Ulanish topilmadi yoki tasdiqlanmagan") from exc

    if connection.from_device_id != device.id and connection.to_device_id != device.id:
        raise ConnectionRequestError("Bu ulanishga ruxsatingiz yo'q")

    return connection


def other_device_in_connection(connection: ConnectionRequest, device: Device) -> Device:
    return connection.to_device if connection.from_device_id == device.id else connection.from_device


def log_transfer_outcome(
    device: Device,
    request_id,
    status: str,
    local_verified: bool,
    reason: str = "",
    file_name: str = "",
    file_size=None,
) -> TransferLog:
    connection = ConnectionRequest.objects.filter(
        Q(from_device=device) | Q(to_device=device), id=request_id
    ).first()
    if not connection:
        raise ConnectionRequestError("Ulanish topilmadi")

    return TransferLog.objects.create(
        connection=connection,
        status=status,
        local_verified=local_verified,
        reason=reason[:255],
        file_name=file_name[:255],
        file_size=file_size,
    )


_FINISHED_STATUSES = {
    TransferLog.STATUS_COMPLETED,
    TransferLog.STATUS_FAILED,
    TransferLog.STATUS_REJECTED_NON_LOCAL,
}


def update_transfer_log_status(
    log_id, device: Device, status: str, reason: str = ""
) -> TransferLog:
    """Mavjud TransferLog yozuvini yakunlaydi (masalan, "in_progress" -> "completed").

    Alohida qator yaratish o'rniga bitta fayl uzatishning boshlanish/tugash
    faktini bitta qatorda saqlaydi (started_at allaqachon bor, finished_at
    shu yerda to'ldiriladi).
    """
    try:
        log = TransferLog.objects.select_related("connection").get(id=log_id)
    except TransferLog.DoesNotExist as exc:
        raise ConnectionRequestError("Jurnal yozuvi topilmadi") from exc

    connection = log.connection
    if connection.from_device_id != device.id and connection.to_device_id != device.id:
        raise ConnectionRequestError("Bu yozuvga ruxsatingiz yo'q")

    log.status = status
    if reason:
        log.reason = reason[:255]
    if status in _FINISHED_STATUSES:
        log.finished_at = timezone.now()
    log.save(update_fields=["status", "reason", "finished_at"])
    return log
