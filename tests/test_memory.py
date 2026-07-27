import pytest
import json
import os
from agent.memory.session import SessionMemory
from agent.memory.persistent import PersistentMemory


def test_session_memory_save_and_get():
    mem = SessionMemory()
    mem.save("papers", [{"title": "Paper A"}])
    assert mem.get("papers") == [{"title": "Paper A"}]


def test_session_memory_get_nonexistent():
    mem = SessionMemory()
    assert mem.get("nonexistent") is None


def test_session_memory_update():
    mem = SessionMemory()
    mem.save("papers", [{"title": "A"}])
    mem.save("papers", [{"title": "A"}, {"title": "B"}])
    assert len(mem.get("papers")) == 2


def test_session_memory_clear():
    mem = SessionMemory()
    mem.save("key", "value")
    mem.clear()
    assert mem.get("key") is None


def test_session_memory_save_to_file(tmp_path):
    mem = SessionMemory(storage_dir=str(tmp_path))
    mem.save("topic", "Test")
    mem._persist()
    assert os.path.exists(os.path.join(tmp_path, "session.json"))


def test_session_memory_load_from_file(tmp_path):
    data = {"topic": "Test", "papers": []}
    with open(os.path.join(tmp_path, "session.json"), "w") as f:
        json.dump(data, f)
    mem = SessionMemory(storage_dir=str(tmp_path))
    mem._load()
    assert mem.get("topic") == "Test"


def test_persistent_memory_set_and_get():
    mem = PersistentMemory(db_path=":memory:")
    mem.set("default_source", "arxiv")
    assert mem.get("default_source") == "arxiv"


def test_persistent_memory_get_default():
    mem = PersistentMemory(db_path=":memory:")
    assert mem.get("nonexistent", "default_val") == "default_val"


def test_persistent_memory_get_all():
    mem = PersistentMemory(db_path=":memory:")
    mem.set("key1", "val1")
    mem.set("key2", "val2")
    all_items = mem.get_all()
    assert len(all_items) >= 2


def test_persistent_memory_delete():
    mem = PersistentMemory(db_path=":memory:")
    mem.set("key", "value")
    mem.delete("key")
    assert mem.get("key") is None


def test_persistent_memory_clear_all():
    mem = PersistentMemory(db_path=":memory:")
    mem.set("key1", "val1")
    mem.set("key2", "val2")
    mem.clear_all()
    assert mem.get_all() == []


def test_memory_integration_load_preferences():
    """Test MemoryIntegration.load_preferences returns existing preferences."""
    from agent.memory.integration import MemoryIntegration
    mem = MemoryIntegration()
    mem.persistent = PersistentMemory(db_path=":memory:")
    mem.persistent.set("year_start", "2020")
    prefs = mem.load_preferences(["year_start", "year_end", "max_papers"])
    assert prefs.get("year_start") == "2020"
    assert "year_end" not in prefs
    assert "max_papers" not in prefs


def test_memory_integration_save_task_history_with_papers():
    """Test that save_task_history stores papers and final_paper separately."""
    from agent.memory.integration import MemoryIntegration
    from agent.core.pipeline import TaskInfo

    mem = MemoryIntegration()
    mem.session.clear()
    task = TaskInfo(topic="Test", keywords=["ai"], goal="Goal")
    raw_papers = [
        {"title": "Paper One", "authors": ["Alice"], "year": "2023", "citation_count": 10, "arxiv_id": "2301.001"},
        {"title": "Paper Two", "authors": ["Bob", "Charlie"], "year": "2024", "citation_count": 5, "source": "semantic_scholar"},
    ]
    result = {
        "status": "complete",
        "paper": "\\section{Full Paper}\nContent here.",
        "papers": raw_papers,
        "rounds": 2,
        "has_warnings": False,
    }
    mem.save_task_history(task, result)
    history = mem.get_task_history()
    assert len(history) == 1
    entry = history[0]
    assert "id" in entry
    assert len(entry["id"]) == 8
    assert entry["topic"] == "Test"
    assert entry["papers"] == [
        {"title": "Paper One", "authors": "Alice", "year": "2023", "citations": 10, "source": "arxiv"},
        {"title": "Paper Two", "authors": "Bob, Charlie", "year": "2024", "citations": 5, "source": "semantic_scholar"},
    ]
    assert entry["rounds"] == 2
    # Verify final_paper is stored separately
    paper_path = os.path.join(mem.session._storage_dir, "papers", f"{entry['id']}.tex")
    assert os.path.exists(paper_path)
    with open(paper_path, "r", encoding="utf-8") as f:
        assert f.read() == "\\section{Full Paper}\nContent here."


def test_memory_integration_save_task_history_rotates():
    """Test that rolling window keeps max 20 entries."""
    from agent.memory.integration import MemoryIntegration
    from agent.core.pipeline import TaskInfo

    mem = MemoryIntegration()
    mem.session.clear()
    for i in range(22):
        task = TaskInfo(topic=f"Task {i}", keywords=[], goal="")
        mem.save_task_history(task, {"status": "complete", "paper": "", "papers": []})
    history = mem.get_task_history()
    assert len(history) == 20
    # Oldest entries should be evicted (Task 0, Task 1)
    assert history[0]["topic"] == "Task 2"
    assert history[-1]["topic"] == "Task 21"


def test_memory_integration_get_task_history_empty():
    """Test that get_task_history returns empty list when no history."""
    from agent.memory.integration import MemoryIntegration

    mem = MemoryIntegration()
    mem.session.clear()
    assert mem.get_task_history() == []


def test_memory_integration_preference_crud():
    """Test MemoryIntegration preference CRUD via persistent memory."""
    from agent.memory.integration import MemoryIntegration
    from agent.memory.persistent import PersistentMemory

    mem = MemoryIntegration()
    mem.persistent = PersistentMemory(db_path=":memory:")
    mem.set_preference("theme", "dark")
    assert mem.get_preference("theme") == "dark"
    assert mem.get_preference("nonexistent", "default") == "default"
