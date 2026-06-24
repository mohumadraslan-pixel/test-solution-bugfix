import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_background_task: Optional[asyncio.Task] = None
_running = False


async def _loop(cache, storage):
    global _running
    while _running:
        try:
            await cache.refresh_expired()
        except Exception as e:
            logger.error(f"Background refresh failed: {e}")
        await asyncio.sleep(60)


def start_background_refresh(cache, storage):
    global _background_task, _running
    if _background_task is not None and not _background_task.done():
        logger.warning("Background refresh already running")
        return

    _running = True
    _background_task = asyncio.create_task(_loop(cache, storage))
    _background_task.add_done_callback(
        lambda t: logger.error(
            f"Background task died: {t.exception()}"
        ) if t.exception() else None
    )


async def stop_background_refresh():
    global _background_task, _running
    _running = False
    if _background_task and not _background_task.done():
        _background_task.cancel()
        try:
            await _background_task
        except asyncio.CancelledError:
            pass
        _background_task = None
