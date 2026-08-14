"""Credentials management API route.

Storage priority (fallback chain):
  1. System keyring (primary) — encrypted via `keyring` library
  2. os.environ (secondary) — runtime process memory
  3. .env file (fallback, lowest) — loaded by load_dotenv() in api/main.py

Security guarantees:
  - GET /api/credentials never returns plaintext keys (only masked preview)
  - PUT /api/credentials writes to encrypted keyring, not to plaintext files
  - DELETE /api/credentials/{key} removes from both keyring and environ
"""
import os
from fastapi import APIRouter
from pydantic import BaseModel
import keyring

router = APIRouter(prefix="/api/credentials", tags=["credentials"])

KEYRING_SERVICE = "ScholarAgent"

CREDENTIAL_KEYS = ["LLM_API_KEY", "SEMANTIC_SCHOLAR_API_KEY", "GOOGLE_SCHOLAR_COOKIE"]


class CredentialUpdate(BaseModel):
    key: str
    value: str


def _mask(value: str) -> str:
    """Return first 4 chars + '****' — never reveal the full key."""
    if not value:
        return ""
    visible = value[:4]
    return f"{visible}****"


def _read_from_keyring(key: str) -> str | None:
    """Read a credential from system keyring. Returns None if not found."""
    try:
        return keyring.get_password(KEYRING_SERVICE, key)
    except Exception:
        return None


def _write_to_keyring(key: str, value: str) -> None:
    """Write a credential to system keyring."""
    keyring.set_password(KEYRING_SERVICE, key, value)


def _delete_from_keyring(key: str) -> None:
    """Delete a credential from system keyring. No-op if not found."""
    try:
        keyring.delete_password(KEYRING_SERVICE, key)
    except keyring.errors.PasswordDeleteError:
        pass


def _resolve_credential(key: str) -> str | None:
    """Resolve credential value via priority chain: keyring → environ → .env."""
    # 1. Try system keyring (primary, encrypted)
    value = _read_from_keyring(key)
    if value:
        return value
    # 2. Try os.environ (secondary, includes .env contents loaded by main.py)
    value = os.getenv(key)
    if value:
        return value
    return None


@router.get("")
async def get_credential_status():
    """Return credential status for all known keys. Never returns plaintext."""
    status = {}
    for key in CREDENTIAL_KEYS:
        value = _resolve_credential(key)
        status[key] = {
            "configured": bool(value),
            "preview": _mask(value) if value else "",
        }
    return {"credentials": status}


@router.put("")
async def update_credential(update: CredentialUpdate):
    """Update a credential. Writes to keyring (encrypted) + os.environ."""
    if update.key not in CREDENTIAL_KEYS:
        return {"status": "error", "message": f"Unknown credential: {update.key}"}

    # Write to encrypted keyring (primary storage)
    _write_to_keyring(update.key, update.value)
    # Also set in os.environ for current process
    os.environ[update.key] = update.value

    return {"status": "updated", "key": update.key}


@router.delete("/{key}")
async def clear_credential(key: str):
    """Clear a credential from keyring and os.environ."""
    if key not in CREDENTIAL_KEYS:
        return {"status": "error", "message": f"Unknown credential: {key}"}

    # Remove from keyring
    _delete_from_keyring(key)
    # Remove from os.environ
    os.environ.pop(key, None)

    return {"status": "cleared", "key": key}