from fastapi import APIRouter
from pydantic import BaseModel
import os

router = APIRouter(prefix="/api/credentials", tags=["credentials"])

CREDENTIAL_KEYS = ["LLM_API_KEY", "SEMANTIC_SCHOLAR_API_KEY", "GOOGLE_SCHOLAR_COOKIE"]


class CredentialUpdate(BaseModel):
    key: str
    value: str


@router.get("")
async def get_credential_status():
    """Return credential status (configured yes/no). Never returns plaintext."""
    status = {}
    for key in CREDENTIAL_KEYS:
        val = os.getenv(key, "")
        status[key] = {
            "configured": bool(val),
            "preview": val[:4] + "****" if val else "",
        }
    return {"credentials": status}


@router.put("")
async def update_credential(update: CredentialUpdate):
    """Update a credential (stored in memory, not persisted to .env)."""
    if update.key not in CREDENTIAL_KEYS:
        return {"status": "error", "message": f"Unknown credential: {update.key}"}
    from agent.memory.persistent import PersistentMemory
    mem = PersistentMemory()
    mem.set(f"credential_{update.key}", update.value)
    os.environ[update.key] = update.value
    return {"status": "updated", "key": update.key}


@router.delete("/{key}")
async def clear_credential(key: str):
    """Clear a stored credential."""
    if key not in CREDENTIAL_KEYS:
        return {"status": "error", "message": f"Unknown credential: {key}"}
    from agent.memory.persistent import PersistentMemory
    mem = PersistentMemory()
    mem.delete(f"credential_{key}")
    os.environ.pop(key, None)
    return {"status": "cleared", "key": key}
