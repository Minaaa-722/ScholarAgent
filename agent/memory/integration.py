import os
import uuid
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

        Generates a UUID for each entry, stores papers in frontend-friendly
        format, and saves final_paper text to a separate file.
        Maintains a rolling window of the last 20 tasks.
        """
        history: list = self.session.get("task_history", [])
        entry_id = uuid.uuid4().hex[:8]

        # Format papers for frontend
        task_papers = result.get("papers", [])
        formatted_papers = [self._format_paper(p) for p in task_papers]

        # Save final_paper to separate file
        final_paper = result.get("paper", "")
        paper_path = self._save_paper_text(entry_id, final_paper)

        entry = {
            "id": entry_id,
            "topic": task.topic,
            "keywords": task.keywords,
            "goal": task.goal,
            "max_papers": task.max_papers,
            "status": result.get("status", ""),
            "has_warnings": result.get("has_warnings", False),
            "rounds": result.get("rounds", 0),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "papers": formatted_papers,
            "paper_path": paper_path,
        }
        history.append(entry)
        # Keep last 20 tasks
        if len(history) > 20:
            history = history[-20:]
        self.session.save("task_history", history)

    def _format_paper(self, p: dict) -> dict:
        """Convert a raw paper dict to frontend-friendly format."""
        authors = p.get("authors", [])[:3]
        author_str = ", ".join(authors) if authors else "Unknown"
        if len(p.get("authors", [])) > 3:
            author_str += " et al."
        return {
            "title": p.get("title", "Untitled"),
            "authors": author_str,
            "year": p.get("year", ""),
            "citations": p.get("citation_count", 0),
            "source": "arxiv" if p.get("arxiv_id") else "semantic_scholar",
        }

    def _save_paper_text(self, entry_id: str, text: str) -> str:
        """Write final_paper text to a separate file. Returns relative path."""
        papers_dir = os.path.join(self.session._storage_dir, "papers")
        os.makedirs(papers_dir, exist_ok=True)
        file_path = os.path.join(papers_dir, f"{entry_id}.tex")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        return file_path

    def save_feedback_history(self, history: list[dict]) -> None:
        """Persist feedback history to session memory."""
        self.session.save("feedback_history", history)

    def get_task_history(self) -> list[dict]:
        """Retrieve recent task history from session memory."""
        return self.session.get("task_history", [])

    def get_task_history_entry(self, entry_id: str) -> dict | None:
        """Retrieve a single history entry by ID, including final_paper text."""
        history = self.get_task_history()
        for entry in history:
            if entry.get("id") == entry_id:
                result = dict(entry)
                # Read final_paper from separate file
                paper_path = entry.get("paper_path", "")
                if paper_path and os.path.exists(paper_path):
                    with open(paper_path, "r", encoding="utf-8") as f:
                        result["final_paper"] = f.read()
                else:
                    result["final_paper"] = ""
                return result
        return None

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a single preference value."""
        return self.persistent.get(key, default)

    def set_preference(self, key: str, value: Any) -> None:
        """Set a single preference value."""
        self.persistent.set(key, value)