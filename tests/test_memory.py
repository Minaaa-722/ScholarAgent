import pytest
import json
import tempfile
import os
from pathlib import Path
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