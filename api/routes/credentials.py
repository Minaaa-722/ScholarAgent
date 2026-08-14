"""Credentials management API route.

Storage priority (fallback chain):
  1. System keyring (primary) — encrypted via `keyring` library
  2. Process environment variables (explicit, not from .env)
  3. .env file (lowest) — plaintext, documented risk

Security guarantees:
  - GET /api/credentials never returns plaintext keys (only masked preview)
  - PUT /api/credentials writes to encrypted keyring, not to plaintext files
  - DELETE /api/credentials/{key} removes from both keyring and environ
  - GET /api/credentials/init-status identifies first-run state
"""
import logging
import os
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel
import keyring
import dotenv

logger = logging.getLogger(__name__)

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
        logger.exception("Failed to read from keyring for key=%s", key)
        return None


def _write_to_keyring(key: str, value: str) -> None:
    """Write a credential to system keyring. Logs failure without crashing."""
    try:
        keyring.set_password(KEYRING_SERVICE, key, value)
    except Exception:
        logger.exception("Failed to write to keyring for key=%s", key)


def _delete_from_keyring(key: str) -> None:
    """Delete a credential from system keyring. No-op if not found."""
    try:
        keyring.delete_password(KEYRING_SERVICE, key)
    except keyring.errors.PasswordDeleteError:
        pass


def _read_from_dotenv(key: str) -> str | None:
    """Read directly from .env file, bypassing os.environ.

    This is the lowest-priority source in the credential resolution chain.
    By reading .env directly rather than relying on os.environ (which
    already merged .env values via load_dotenv()), we can properly
    distinguish between process env vars and .env values.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return None
    try:
        values = dotenv.dotenv_values(env_path)
        return values.get(key)
    except Exception:
        logger.exception("Failed to read .env file at %s", env_path)
        return None


def _resolve_credential(key: str) -> str | None:
    """Resolve credential value via priority chain: keyring → process env → .env.

    Priority:
      1. System keyring (highest, encrypted)
      2. os.environ (process env vars; after load_dotenv() this also includes
         .env values, but load_dotenv doesn't overwrite existing env vars so
         process env implicitly takes priority over .env)
      3. .env file (lowest, plaintext risk)
    """
    # 1. System keyring (primary, encrypted)
    value = _read_from_keyring(key)
    if value:
        logger.debug("Resolved credential %s from keyring", key)
        return value
    # 2. os.environ (process env vars, already includes .env loaded by main.py)
    value = os.getenv(key)
    if value:
        logger.debug("Resolved credential %s from os.environ", key)
        return value
    # 3. Direct .env read (fallback, for when load_dotenv hasn't been called)
    value = _read_from_dotenv(key)
    if value:
        logger.debug("Resolved credential %s from .env file", key)
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


@router.get("/init-status")
async def get_init_status():
    """Return whether the system needs initialization (no LLM_API_KEY found).

    Checks all sources: keyring, process env, and .env file.
    Returns ``{"needs_initialization": true}`` when LLM_API_KEY is absent
    from all three, indicating this is a first-run scenario.
    """
    llm_key = _resolve_credential("LLM_API_KEY")
    needs_init = llm_key is None
    logger.info("Init-status check: needs_initialization=%s", needs_init)
    return {"needs_initialization": needs_init}


@router.put("")
async def update_credential(update: CredentialUpdate):
    """Update a credential. Writes to keyring (encrypted) + os.environ."""
    if update.key not in CREDENTIAL_KEYS:
        return {"status": "error", "message": f"Unknown credential: {update.key}"}

    logger.info("Updating credential: %s", update.key)

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

    logger.info("Clearing credential: %s", key)

    # Remove from keyring
    _delete_from_keyring(key)
    # Remove from os.environ
    os.environ.pop(key, None)

    return {"status": "cleared", "key": key}