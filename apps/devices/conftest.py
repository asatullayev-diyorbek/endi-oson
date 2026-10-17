import asyncio

import pytest

from .consumers import _pending_watch_tasks


@pytest.fixture(autouse=True)
async def _cancel_pending_watch_tasks():
    """Har bir testdan keyin ortda qolgan `_watch_timeout` task'larini tozalaydi.

    Aks holda ular keyingi test DB'ni tozalashga urinayotganda ochiq
    ulanishni ushlab turib, "database is being accessed by other users"
    xatosiga olib keladi.
    """
    yield
    pending = [t for t in _pending_watch_tasks if not t.done()]
    for task in pending:
        task.cancel()
    for task in pending:
        try:
            await task
        except asyncio.CancelledError:
            pass
    _pending_watch_tasks.clear()
