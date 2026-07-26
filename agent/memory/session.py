import json
import os
from typing import Any, Optional
from agent.memory.base import MemoryBase


class SessionMemory(MemoryBase):
    def __init__(self, storage_dir: str = "memory/session"):
        self._data: dict[str, Any] = {}
        self._storage_dir = storage_dir
        self._storage_path = os.path.join(storage_dir, "session.json")
        os.makedirs(storage_dir, exist_ok=True)
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def save(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._persist()

    def clear(self) -> None:
        self._data.clear()
        self._persist()

    def _persist(self) -> None:
        with open(self._storage_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        if os.path.exists(self._storage_path):
            with open(self._storage_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)