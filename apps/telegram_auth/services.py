import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User

from .models import LoginAttempt

TOKEN_TTL = timedelta(minutes=5)


class LoginAttemptError(Exception):
    """Login urinishi tasdiqlanishi/yakunlanishi mumkin bo'lmaganda ko'tariladi."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def start_login_attempt(browser_session_id: str) -> tuple[str, LoginAttempt]:
    """Yangi bir martalik, qisqa muddatli login tokeni yaratadi.

    Xom token faqat shu funksiyadan qaytariladi va deep-link ichida ishlatiladi —
    bazaga faqat uning hashi yoziladi.
    """
    token = secrets.token_urlsafe(32)  # ~43 URL-safe belgi, 64 dan kam
    attempt = LoginAttempt.objects.create(
        token_hash=_hash_token(token),
        browser_session_id=browser_session_id,
        expires_at=timezone.now() + TOKEN_TTL,
    )
    return token, attempt


def confirm_login_attempt(token: str, telegram_user_id: int) -> LoginAttempt:
    """Bot tomonidan chaqiriladi: tokenni tekshiradi va foydalanuvchini bog'laydi.

    select_for_update() + atomik tranzaksiya bir token bilan parallel ikki
    tasdiqlash (race condition) yuz berishining oldini oladi.

    Eslatma: muddati tugagan holatni "expired"ga belgilash qasddan asosiy
    atomik blokdan tashqarida qilinadi — aks holda LoginAttemptError
    ko'tarilganda butun tranzaksiya (shu status yozuvi bilan birga) orqaga
    qaytariladi.
    """
    token_hash = _hash_token(token)
    expired = False

    with transaction.atomic():
        try:
            attempt = LoginAttempt.objects.select_for_update().get(token_hash=token_hash)
        except LoginAttempt.DoesNotExist as exc:
            raise LoginAttemptError("Token topilmadi yoki noto'g'ri") from exc

        if attempt.status != LoginAttempt.STATUS_PENDING:
            raise LoginAttemptError("Token allaqachon ishlatilgan")

        if attempt.is_expired():
            expired = True
        else:
            # Telegram user ID — Telegram update'ning o'zidan, foydalanuvchi matnidan emas.
            User.objects.get_or_create(telegram_user_id=telegram_user_id)
            attempt.status = LoginAttempt.STATUS_CONFIRMED
            attempt.telegram_user_id = telegram_user_id
            attempt.consumed_at = timezone.now()
            attempt.save(update_fields=["status", "telegram_user_id", "consumed_at"])

    if expired:
        attempt.status = LoginAttempt.STATUS_EXPIRED
        attempt.save(update_fields=["status"])
        raise LoginAttemptError("Token muddati tugagan, qaytadan urinib ko'ring")

    return attempt


def complete_login_attempt(attempt_id: int, browser_session_id: str) -> User:
    """Brauzer tomonidan chaqiriladi: tasdiqlangan urinishni shu sessiyaga yakunlaydi.

    browser_session_id moslashini tekshirish — tokenni ko'rgan boshqa birov
    (masalan, tasdiqlash kutilayotganda havolani ushlab olgan) uni boshqa
    brauzerdan ishlatib sessiya ocha olmasligini ta'minlaydi.
    """
    try:
        attempt = LoginAttempt.objects.get(id=attempt_id, browser_session_id=browser_session_id)
    except LoginAttempt.DoesNotExist as exc:
        raise LoginAttemptError("Login urinishi topilmadi") from exc

    if attempt.status != LoginAttempt.STATUS_CONFIRMED:
        raise LoginAttemptError("Login hali Telegram orqali tasdiqlanmagan")

    return User.objects.get(telegram_user_id=attempt.telegram_user_id)
