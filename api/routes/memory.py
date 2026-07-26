from fastapi import APIRouter
from api.models import MemoryUpdate
from agent.memory.persistent import PersistentMemory

router = APIRouter(prefix="/api/memory", tags=["memory"])
_memory = PersistentMemory()


@router.get("")
async def get_all_memory():
    return {"preferences": _memory.get_all()}


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