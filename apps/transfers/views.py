import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.devices.models import Device

from .models import TransferLog
from .services import ConnectionRequestError, log_transfer_outcome

ALLOWED_STATUSES = {choice for choice, _ in TransferLog.STATUS_CHOICES}


@login_required(login_url="/auth/telegram/login/")
@require_POST
def log_transfer(request):
    """Frontend WebRTC lokal-only tekshiruvining natijasini audit sifatida yozadi.

    Fayl bayt uzatish bu yerda qatnashmaydi — faqat metadata.
    """
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Noto'g'ri so'rov tanasi"}, status=400)

    status = data.get("status")
    if status not in ALLOWED_STATUSES:
        return JsonResponse({"error": "Noto'g'ri status"}, status=400)

    device_id = data.get("device_id")
    if not device_id:
        return JsonResponse({"error": "device_id majburiy"}, status=400)

    device = Device.objects.filter(id=device_id, user=request.user).first()
    if not device:
        return JsonResponse({"error": "Qurilma topilmadi"}, status=404)

    try:
        log = log_transfer_outcome(
            device=device,
            request_id=data.get("request_id"),
            status=status,
            local_verified=bool(data.get("local_verified")),
            reason=data.get("reason", ""),
            file_name=data.get("file_name", ""),
            file_size=data.get("file_size"),
        )
    except ConnectionRequestError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse({"status": "ok", "log_id": log.id})
