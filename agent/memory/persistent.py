import sqlite3
import os
from typing import Any, Optional
from agent.memory.base import MemoryBase


class PersistentMemory(MemoryBase):
    def __init__(self, db_path: str = "memory/persistent/scholar_memory.db"):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        cursor = self._conn.execute(
            "SELECT value FROM user_preferences WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else default

    def save(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO user_preferences (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, str(value)),
        )
        self._conn.commit()

    def set(self, key: str, value: Any) -> None:
        self.save(key, value)

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM user_preferences WHERE key = ?", (key,))
        self._conn.commit()

    def get_all(self) -> list[dict]:
        cursor = self._conn.execute(
            "SELECT key, value, updated_at FROM user_preferences ORDER BY key"
        )
        return [{"key": k, "value": v, "updated_at": t} for k, v, t in cursor.fetchall()]

    def clear_all(self) -> None:
        self._conn.execute("DELETE FROM user_preferences")
        self._conn.commit()

    def clear(self) -> None:
        self.clear_all()