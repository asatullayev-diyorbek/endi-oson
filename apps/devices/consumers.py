import asyncio
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.transfers.services import (
    ConnectionRequestError,
    create_connection_request,
    expire_if_still_pending,
    get_accepted_connection,
    other_device_in_connection,
    respond_to_connection_request,
)

from .models import Device

CONNECTION_REQUEST_TIMEOUT_SECONDS = 30

# Testlarda (teardown paytida) ortda qolgan timeout kutuvchi task'larni
# bekor qilish uchun kuzatib boriladi — aks holda ular DB ulanishini
# keyingi test bazasini tozalashga xalaqit beradigan tarzda ushlab turadi.
_pending_watch_tasks: set = set()


class DeviceConsumer(AsyncJsonWebsocketConsumer):
    """Foydalanuvchining qurilmalar ro'yxatini real-time yuritadi (presence).

    Ulanganda mavjud `device_id` qayta ishlatiladi (qurilma qaytadan onlayn
    bo'ladi), bo'lmasa yangi Device yoziladi. Guruh (`user_<id>`) orqali
    shu foydalanuvchining barcha ochiq WS ulanishlariga online/offline
    o'zgarishlar push qilinadi.
    """

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4001)
            return

        self.user = user
        self.group_name = f"user_{user.id}"

        query = parse_qs(self.scope["query_string"].decode())
        device_id = query.get("device_id", [None])[0]
        label = (query.get("label", [None])[0] or "").strip()[:128]

        self.device = await self._get_or_create_device(device_id, label)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self._mark_online()
        await self.send_json({"type": "device.self", "device_id": self.device.id})
        await self._broadcast_device_list()

    async def disconnect(self, close_code):
        if getattr(self, "device", None):
            await self._mark_offline()
            await self._broadcast_device_list()
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type")
        if msg_type == "rename":
            label = (content.get("label") or "").strip()[:128]
            if label:
                await self._rename(label)
                await self._broadcast_device_list()
        elif msg_type == "connection.request":
            await self._handle_connection_request(content)
        elif msg_type == "connection.respond":
            await self._handle_connection_respond(content)
        elif msg_type == "signaling.relay":
            await self._handle_signaling_relay(content)

    async def device_list_push(self, event):
        await self.send_json(event["payload"])

    # --- Ulanish so'rovi (4-bosqich) -------------------------------------

    async def _handle_connection_request(self, content):
        to_device_id = content.get("to_device_id")
        try:
            request = await sync_to_async(create_connection_request)(
                self.device, to_device_id
            )
        except ConnectionRequestError as exc:
            await self.send_json({"type": "connection.error", "error": str(exc)})
            return

        to_channel = await sync_to_async(lambda: request.to_device.channel_name)()
        if to_channel:
            await self.channel_layer.send(
                to_channel,
                {
                    "type": "connection.request",
                    "request_id": request.id,
                    "from_device_id": self.device.id,
                    "from_device_label": self.device.device_label,
                },
            )

        task = asyncio.create_task(self._watch_timeout(request.id))
        _pending_watch_tasks.add(task)
        task.add_done_callback(_pending_watch_tasks.discard)

    async def _handle_connection_respond(self, content):
        request_id = content.get("request_id")
        accept = bool(content.get("accept"))

        try:
            request = await sync_to_async(respond_to_connection_request)(
                request_id, self.device, accept
            )
        except ConnectionRequestError as exc:
            await self.send_json({"type": "connection.error", "error": str(exc)})
            return

        from_channel = await sync_to_async(lambda: request.from_device.channel_name)()
        if from_channel:
            await self.channel_layer.send(
                from_channel,
                {
                    "type": "connection.response",
                    "request_id": request.id,
                    "status": request.status,
                },
            )

    async def connection_request(self, event):
        await self.send_json(event)

    async def connection_response(self, event):
        await self.send_json(event)

    # --- WebRTC signaling (5-bosqich) -------------------------------------
    #
    # Faqat SDP offer/answer va ICE candidate JSON paketlarini relay qiladi —
    # fayl baytlari bu yerdan HECH QACHON o'tmaydi. Target qurilma
    # client'dan emas, faqat tasdiqlangan ConnectionRequest'dan aniqlanadi —
    # shunday qilib begona qurilma boshqalar orasiga signaling xabari
    # in'ektsiya qila olmaydi.

    async def _handle_signaling_relay(self, content):
        request_id = content.get("request_id")
        payload = content.get("payload")

        try:
            target_channel = await sync_to_async(self._resolve_signaling_target)(request_id)
        except ConnectionRequestError as exc:
            await self.send_json({"type": "connection.error", "error": str(exc)})
            return

        if target_channel:
            await self.channel_layer.send(
                target_channel,
                {
                    "type": "signaling.relay",
                    "request_id": request_id,
                    "payload": payload,
                },
            )

    def _resolve_signaling_target(self, request_id):
        connection = get_accepted_connection(request_id, self.device)
        target = other_device_in_connection(connection, self.device)
        return target.channel_name

    async def signaling_relay(self, event):
        await self.send_json(event)

    async def _watch_timeout(self, request_id):
        await asyncio.sleep(CONNECTION_REQUEST_TIMEOUT_SECONDS)
        request = await sync_to_async(expire_if_still_pending)(request_id)
        if not request:
            return

        from_channel, to_channel = await sync_to_async(
            lambda: (request.from_device.channel_name, request.to_device.channel_name)
        )()
        for channel in (from_channel, to_channel):
            if channel:
                await self.channel_layer.send(
                    channel,
                    {
                        "type": "connection.response",
                        "request_id": request.id,
                        "status": "timeout",
                    },
                )

    @sync_to_async
    def _get_or_create_device(self, device_id, label):
        if device_id:
            device = Device.objects.filter(id=device_id, user=self.user).first()
            if device:
                return device
        return Device.objects.create(
            user=self.user, device_label=label or "Noma'lum qurilma"
        )

    @sync_to_async
    def _mark_online(self):
        self.device.channel_name = self.channel_name
        self.device.is_online = True
        self.device.save(update_fields=["channel_name", "is_online", "last_seen"])

    @sync_to_async
    def _mark_offline(self):
        self.device.is_online = False
        self.device.save(update_fields=["is_online", "last_seen"])

    @sync_to_async
    def _rename(self, label):
        self.device.device_label = label
        self.device.save(update_fields=["device_label"])

    @sync_to_async
    def _online_devices(self):
        return list(
            Device.objects.filter(user=self.user, is_online=True).values(
                "id", "device_label"
            )
        )

    async def _broadcast_device_list(self):
        devices = await self._online_devices()
        payload = {
            "type": "device.list",
            "devices": [
                {"id": d["id"], "device_label": d["device_label"]} for d in devices
            ],
        }
        await self.channel_layer.group_send(
            self.group_name, {"type": "device_list_push", "payload": payload}
        )
