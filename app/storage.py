import sqlite3
import threading
from typing import Any, List


class Storage:
    """Thread-safe SQLite storage with connection pooling per thread."""

    def __init__(self):
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    async def connect(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO items (name, price, quantity) VALUES ('Widget A', 9.99, 100);
            INSERT INTO items (name, price, quantity) VALUES ('Widget B', 14.99, 50);
            INSERT INTO items (name, price, quantity) VALUES ('Gadget X', 29.99, 25);
        """)

    async def disconnect(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def query(self, sql: str, *params: Any) -> List[dict]:
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Storage not connected")
            cursor = self._conn.execute(sql, params)
            if sql.strip().upper().startswith("SELECT"):
                return [dict(row) for row in cursor.fetchall()]
            self._conn.commit()
            if "RETURNING" in sql.upper():
                return [dict(row) for row in cursor.fetchall()]
            return []
