import os

from .base import *  # noqa: F401,F403

DEBUG = False

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Render har bir servisga shu env var orqali o'zining tashqi hostini beradi
# (masalan "endi-oson-web.onrender.com") — qo'lda ALLOWED_HOSTS'ga
# qo'shishni unutib qolishning oldini olish uchun avtomatik qo'shamiz.
render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if render_host:
    ALLOWED_HOSTS.append(render_host)  # noqa: F405
    CSRF_TRUSTED_ORIGINS.append(f"https://{render_host}")  # noqa: F405

if not ALLOWED_HOSTS:  # noqa: F405
    raise RuntimeError("Production muhitida ALLOWED_HOSTS to'ldirilishi shart")
