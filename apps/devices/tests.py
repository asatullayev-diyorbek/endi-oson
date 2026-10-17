import pytest
from channels.testing import WebsocketCommunicator

from apps.accounts.models import User
from apps.transfers.models import ConnectionRequest

from .consumers import DeviceConsumer

pytestmark = pytest.mark.django_db


async def _connect(user, device_id=None, label=""):
    query = []
    if device_id:
        query.append(f"device_id={device_id}")
    if label:
        query.append(f"label={label}")
    path = "/ws/devices/"
    if query:
        path += "?" + "&".join(query)

    communicator = WebsocketCommunicator(DeviceConsumer.as_asgi(), path)
    communicator.scope["user"] = user
    connected, _ = await communicator.connect(timeout=5)
    assert connected
    return communicator


@pytest.mark.asyncio
async def test_connect_creates_device_and_broadcasts_list():
    user = await _async_create_user(1001)
    comm = await _connect(user, label="MacBook")

    self_msg = await comm.receive_json_from(timeout=5)
    assert self_msg["type"] == "device.self"

    list_msg = await comm.receive_json_from(timeout=5)
    assert list_msg["type"] == "device.list"
    assert len(list_msg["devices"]) == 1
    assert list_msg["devices"][0]["device_label"] == "MacBook"

    await comm.disconnect()


@pytest.mark.asyncio
async def test_two_devices_see_each_other_online():
    user = await _async_create_user(1002)
    comm_a = await _connect(user, label="A")
    await comm_a.receive_json_from(timeout=5)  # device.self
    await comm_a.receive_json_from(timeout=5)  # device.list (A alone)

    comm_b = await _connect(user, label="B")
    await comm_b.receive_json_from(timeout=5)  # device.self
    await comm_b.receive_json_from(timeout=5)  # device.list (A+B) for B

    list_for_a = await comm_a.receive_json_from(timeout=5)  # pushed update when B joins
    assert len(list_for_a["devices"]) == 2

    await comm_a.disconnect()
    await comm_b.disconnect()


@pytest.mark.asyncio
async def test_connection_request_accept_flow():
    user_a = await _async_create_user(2001)
    user_b = await _async_create_user(2002)

    comm_a = await _connect(user_a, label="A")
    await comm_a.receive_json_from(timeout=5)
    self_a_list = await comm_a.receive_json_from(timeout=5)
    device_a_id = self_a_list["devices"][0]["id"]

    comm_b = await _connect(user_b, label="B")
    self_b = await comm_b.receive_json_from(timeout=5)
    device_b_id = self_b["device_id"]
    await comm_b.receive_json_from(timeout=5)  # device.list

    await comm_a.send_json_to({"type": "connection.request", "to_device_id": device_b_id})

    request_evt = await comm_b.receive_json_from(timeout=5)
    assert request_evt["type"] == "connection.request"
    assert request_evt["from_device_id"] == device_a_id

    await comm_b.send_json_to(
        {"type": "connection.respond", "request_id": request_evt["request_id"], "accept": True}
    )

    response_evt = await comm_a.receive_json_from(timeout=5)
    assert response_evt["type"] == "connection.response"
    assert response_evt["status"] == ConnectionRequest.STATUS_ACCEPTED

    await comm_a.disconnect()
    await comm_b.disconnect()


@pytest.mark.asyncio
async def test_connection_request_times_out():
    user_a = await _async_create_user(3001)
    user_b = await _async_create_user(3002)

    comm_a = await _connect(user_a, label="A")
    await comm_a.receive_json_from(timeout=5)
    await comm_a.receive_json_from(timeout=5)

    comm_b = await _connect(user_b, label="B")
    self_b = await comm_b.receive_json_from(timeout=5)
    device_b_id = self_b["device_id"]
    await comm_b.receive_json_from(timeout=5)

    await comm_a.send_json_to({"type": "connection.request", "to_device_id": device_b_id})
    await comm_b.receive_json_from(timeout=5)  # connection.request on B's side

    response_evt = await comm_a.receive_json_from(timeout=35)
    assert response_evt == {
        "type": "connection.response",
        "request_id": response_evt["request_id"],
        "status": "timeout",
    }

    await comm_a.disconnect()
    await comm_b.disconnect()


async def _async_create_user(telegram_user_id):
    from asgiref.sync import sync_to_async

    return await sync_to_async(User.objects.create_user)(telegram_user_id=telegram_user_id)
