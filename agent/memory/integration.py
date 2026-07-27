import time
from typing import Any, Optional

from agent.core.pipeline import TaskInfo
from agent.memory.session import SessionMemory
from agent.memory.persistent import PersistentMemory


class MemoryIntegration:
    """Wraps SessionMemory and PersistentMemory for the Harness.

    Provides auto-load of user preferences before research creation,
    and persists session data (task history, feedback history).
    """

    def __init__(self):
        self.session = SessionMemory()
        self.persistent = PersistentMemory()

    def load_preferences(self, keys: list[str]) -> dict[str, Any]:
        """Load user preferences from persistent memory.

        Args:
            keys: List of preference keys to load (e.g. year_start, year_end, max_papers).

        Returns:
            Dict of key -> value for keys that exist in persistent memory.
        """
        prefs = {}
        for key in keys:
            val = self.persistent.get(key)
            if val is not None:
                prefs[key] = val
        return prefs

    def save_task_history(self, task: TaskInfo, result: dict) -> None:
        """Save task info and result to session memory.

        Maintains a rolling window of the last 20 tasks.
        """
        history: list = self.session.get("task_history", [])
        entry = {
            "topic": task.topic,
            "keywords": task.keywords,
            "goal": task.goal,
            "status": result.get("status", ""),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        history.append(entry)
        # Keep last 20 tasks
        if len(history) > 20:
            history = history[-20:]
        self.session.save("task_history", history)

    def save_feedback_history(self, history: list[dict]) -> None:
        """Persist feedback history to session memory."""
        self.session.save("feedback_history", history)

    def get_task_history(self) -> list[dict]:
        """Retrieve recent task history from session memory."""
        return self.session.get("task_history", [])

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a single preference value."""
        return self.persistent.get(key, default)

    def set_preference(self, key: str, value: Any) -> None:
        """Set a single preference value."""
        self.persistent.set(key, value)