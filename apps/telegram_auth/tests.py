import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User

from .models import LoginAttempt
from .services import (
    LoginAttemptError,
    complete_login_attempt,
    confirm_login_attempt,
    start_login_attempt,
)

pytestmark = pytest.mark.django_db


def test_start_creates_pending_attempt_and_does_not_store_raw_token():
    token, attempt = start_login_attempt("browser-1")
    assert attempt.status == LoginAttempt.STATUS_PENDING
    assert attempt.token_hash != token
    assert LoginAttempt.objects.filter(token_hash=attempt.token_hash).exists()


def test_confirm_creates_user_and_marks_attempt_confirmed():
    token, attempt = start_login_attempt("browser-1")

    confirm_login_attempt(token, telegram_user_id=111)

    attempt.refresh_from_db()
    assert attempt.status == LoginAttempt.STATUS_CONFIRMED
    assert attempt.telegram_user_id == 111
    assert User.objects.filter(telegram_user_id=111).count() == 1


def test_confirm_is_idempotent_safe_against_reuse():
    token, attempt = start_login_attempt("browser-1")
    confirm_login_attempt(token, telegram_user_id=111)

    with pytest.raises(LoginAttemptError):
        confirm_login_attempt(token, telegram_user_id=111)


def test_confirm_rejects_expired_token():
    token, attempt = start_login_attempt("browser-1")
    attempt.expires_at = timezone.now() - timezone.timedelta(seconds=1)
    attempt.save(update_fields=["expires_at"])

    with pytest.raises(LoginAttemptError):
        confirm_login_attempt(token, telegram_user_id=111)

    attempt.refresh_from_db()
    assert attempt.status == LoginAttempt.STATUS_EXPIRED


def test_complete_requires_matching_browser_session():
    token, attempt = start_login_attempt("browser-1")
    confirm_login_attempt(token, telegram_user_id=111)

    with pytest.raises(LoginAttemptError):
        complete_login_attempt(attempt.id, "browser-2")

    user = complete_login_attempt(attempt.id, "browser-1")
    assert user.telegram_user_id == 111


def test_complete_requires_confirmed_status():
    _, attempt = start_login_attempt("browser-1")

    with pytest.raises(LoginAttemptError):
        complete_login_attempt(attempt.id, "browser-1")


def test_full_http_flow_logs_user_in():
    client = Client()

    client.get("/auth/telegram/login/")  # sets CSRF cookie + browser session

    start_response = client.post("/auth/telegram/start/")
    assert start_response.status_code == 200
    body = start_response.json()
    token = body["deep_link"].split("start=")[1]
    attempt_id = body["attempt_id"]

    confirm_login_attempt(token, telegram_user_id=222)

    poll_response = client.get(f"/auth/telegram/poll/{attempt_id}/")
    assert poll_response.json()["status"] == "confirmed"

    complete_response = client.post(f"/auth/telegram/complete/{attempt_id}/")
    assert complete_response.status_code == 200

    home_response = client.get("/")
    assert home_response.status_code == 200
    assert b"222" in home_response.content
