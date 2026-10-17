import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_asgi_app = get_asgi_application()

# Har bir app o'z websocket_urlpatterns'ini qo'shadi (signaling — 5-bosqichda).
from apps.devices.routing import websocket_urlpatterns as device_urlpatterns  # noqa: E402

websocket_urlpatterns = [*device_urlpatterns]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # AuthMiddlewareStack — Django sessiya cookie'sidan scope["user"]ni
        # to'ldiradi, shuning uchun consumer'lar HTTP login bilan bir xil
        # foydalanuvchini ko'radi.
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
