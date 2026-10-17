import pytest

from apps.accounts.models import User
from apps.devices.models import Device

from .models import ConnectionRequest, TransferLog
from .services import (
    ConnectionRequestError,
    get_accepted_connection,
    log_transfer_outcome,
    other_device_in_connection,
)

pytestmark = pytest.mark.django_db


def _make_device(telegram_user_id, label):
    user = User.objects.create_user(telegram_user_id=telegram_user_id)
    return Device.objects.create(user=user, device_label=label)


def test_get_accepted_connection_requires_accepted_status():
    a = _make_device(1, "A")
    b = _make_device(2, "B")
    conn = ConnectionRequest.objects.create(
        from_device=a, to_device=b, status=ConnectionRequest.STATUS_PENDING
    )

    with pytest.raises(ConnectionRequestError):
        get_accepted_connection(conn.id, a)

    conn.status = ConnectionRequest.STATUS_ACCEPTED
    conn.save(update_fields=["status"])

    assert get_accepted_connection(conn.id, a).id == conn.id
    assert get_accepted_connection(conn.id, b).id == conn.id


def test_get_accepted_connection_rejects_unrelated_device():
    a = _make_device(11, "A")
    b = _make_device(12, "B")
    stranger = _make_device(13, "Stranger")
    conn = ConnectionRequest.objects.create(
        from_device=a, to_device=b, status=ConnectionRequest.STATUS_ACCEPTED
    )

    with pytest.raises(ConnectionRequestError):
        get_accepted_connection(conn.id, stranger)


def test_other_device_in_connection():
    a = _make_device(21, "A")
    b = _make_device(22, "B")
    conn = ConnectionRequest.objects.create(
        from_device=a, to_device=b, status=ConnectionRequest.STATUS_ACCEPTED
    )

    assert other_device_in_connection(conn, a).id == b.id
    assert other_device_in_connection(conn, b).id == a.id


def test_log_transfer_outcome_creates_record_for_participant():
    a = _make_device(31, "A")
    b = _make_device(32, "B")
    conn = ConnectionRequest.objects.create(
        from_device=a, to_device=b, status=ConnectionRequest.STATUS_ACCEPTED
    )

    log = log_transfer_outcome(
        device=a,
        request_id=conn.id,
        status=TransferLog.STATUS_REJECTED_NON_LOCAL,
        local_verified=False,
        reason="relay candidate",
    )

    assert log.connection_id == conn.id
    assert log.status == TransferLog.STATUS_REJECTED_NON_LOCAL
    assert log.local_verified is False


def test_log_transfer_outcome_rejects_non_participant():
    a = _make_device(41, "A")
    b = _make_device(42, "B")
    stranger = _make_device(43, "Stranger")
    conn = ConnectionRequest.objects.create(
        from_device=a, to_device=b, status=ConnectionRequest.STATUS_ACCEPTED
    )

    with pytest.raises(ConnectionRequestError):
        log_transfer_outcome(
            device=stranger,
            request_id=conn.id,
            status=TransferLog.STATUS_FAILED,
            local_verified=False,
        )
