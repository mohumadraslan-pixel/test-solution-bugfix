import time
import asyncio
from typing import Any, Optional, Tuple

_MAX_CACHE_SIZE = 10_000


class Cache:
    """Thread-safe in-memory cache with TTL and size limit."""

    def __init__(self):
        self._store: dict[str, Tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at and time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int = 300):
        async with self._lock:
            if len(self._store) >= _MAX_CACHE_SIZE and key not in self._store:
                # Evict oldest entry
                oldest = min(self._store.keys(), key=lambda k: self._store[k][1])
                del self._store[oldest]
            self._store[key] = (value, time.monotonic() + ttl)

    async def delete(self, key: str):
        async with self._lock:
            self._store.pop(key, None)

    async def invalidate_prefix(self, prefix: str):
        async with self._lock:
            keys_to_delete = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._store[k]

    async def clear(self):
        async with self._lock:
            self._store.clear()

    async def refresh_expired(self):
        async with self._lock:
            now = time.monotonic()
            expired = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired:
                del self._store[k]

    async def size(self) -> int:
        async with self._lock:
            return len(self._store)
