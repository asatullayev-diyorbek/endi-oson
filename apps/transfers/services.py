from django.db import transaction
from django.utils import timezone

from apps.devices.models import Device

from .models import ConnectionRequest


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
