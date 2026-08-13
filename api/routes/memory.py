from fastapi import APIRouter
from api.models import MemoryUpdate
from agent.memory.persistent import PersistentMemory

router = APIRouter(prefix="/api/memory", tags=["memory"])
_memory = PersistentMemory()


@router.get("")
async def get_all_memory():
    return {"preferences": _memory.get_all()}


@router.get("/auto-load")
async def get_auto_load_preferences():
    """Return default preferences for the ResearchCreation form."""
    prefs = {}
    for key in ("default_source", "year_start", "year_end", "max_papers", "blacklist"):
        val = _memory.get(key)
        if val is not None:
            prefs[key] = val
    return {
        "preferences": prefs,
        "available": {
            "default_source": {"type": "select", "options": ["arxiv", "semantic_scholar", "both"]},
            "year_start": {"type": "number", "min": 2015, "max": 2026},
            "year_end": {"type": "number", "min": 2015, "max": 2026},
            "max_papers": {"type": "number", "min": 5, "max": 100},
            "blacklist": {"type": "text"},
        },
    }


@router.put("")
async def update_memory(update: MemoryUpdate):
    _memory.set(update.key, update.value)
    return {"status": "updated", "key": update.key}


@router.delete("")
async def clear_memory():
    _memory.clear_all()
    return {"status": "cleared"}


@router.delete("/{key}")
async def delete_memory_key(key: str):
    _memory.delete(key)
    return {"status": "deleted", "key": key}
