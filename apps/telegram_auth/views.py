from django.conf import settings
from django.contrib.auth import login
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from .models import LoginAttempt
from .services import LoginAttemptError, complete_login_attempt, start_login_attempt

BROWSER_SESSION_KEY = "telegram_login_browser_session_id"


def _get_or_create_browser_session_id(request) -> str:
    bsid = request.session.get(BROWSER_SESSION_KEY)
    if not bsid:
        bsid = get_random_string(43)
        request.session[BROWSER_SESSION_KEY] = bsid
    return bsid


@ensure_csrf_cookie
def login_page(request):
    return render(request, "registration/login.html")


@ratelimit(key="ip", rate="10/m", block=True)
@require_POST
def start(request):
    browser_session_id = _get_or_create_browser_session_id(request)
    token, attempt = start_login_attempt(browser_session_id)
    deep_link = f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={token}"
    return JsonResponse({"deep_link": deep_link, "attempt_id": attempt.id})


def poll(request, attempt_id):
    browser_session_id = request.session.get(BROWSER_SESSION_KEY)
    attempt = get_object_or_404(
        LoginAttempt, id=attempt_id, browser_session_id=browser_session_id
    )
    return JsonResponse({"status": attempt.status})


@require_POST
def complete(request, attempt_id):
    browser_session_id = request.session.get(BROWSER_SESSION_KEY)
    if not browser_session_id:
        return JsonResponse({"error": "Sessiya topilmadi"}, status=400)

    try:
        user = complete_login_attempt(attempt_id, browser_session_id)
    except LoginAttemptError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    login(request, user)
    return JsonResponse({"status": "ok"})
