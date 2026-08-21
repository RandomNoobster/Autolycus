from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any, Optional

from infra.cache import get_cache

ACTIVE_STATUSES = {"active", "awaiting"}
TERMINAL_STATUSES = {"completed", "expired", "cancelled", "failed"}
DEFAULT_TTL_SECONDS = 3600
_SESSION_NS = "ix_session"
_LOCK_NS = "ix_lock"


def _now_ts() -> int:
    return int(time.time())


def _gen_session_id() -> str:
    return secrets.token_urlsafe(12)


def _session_key(session_id: str) -> str:
    return f"{_SESSION_NS}:{session_id}"


def _lock_key(session_id: str) -> str:
    return f"{_LOCK_NS}:{session_id}"


async def _load_session(cache, session_id: str) -> Optional[dict[str, Any]]:
    raw = await cache.get(_session_key(session_id))
    if isinstance(raw, dict):
        return raw
    return None


async def _store_session(cache, session: dict[str, Any]) -> None:
    ttl = max(1, int(session.get("expires_at", _now_ts() + DEFAULT_TTL_SECONDS) - _now_ts()))
    await cache.set(_session_key(session["session_id"]), session, ttl=ttl)


async def ensure_indexes() -> None:
    """Redis-backed sessions require no index setup."""
    return None


async def create_session(
    *,
    command: str,
    handler_key: str,
    user_id: int,
    guild_id: Optional[int],
    channel_id: int,
    message_id: int,
    state: Optional[dict[str, Any]] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    flow_type: str = "custom",
) -> dict[str, Any]:
    """Create and persist a new Redis-backed interaction session."""
    cache = get_cache()
    now = _now_ts()
    expires_at = now + max(1, int(ttl_seconds))
    for _ in range(5):
        sid = _gen_session_id()
        payload: dict[str, Any] = {
            "session_id": sid,
            "command": command,
            "handler_key": handler_key,
            "flow_type": flow_type,
            "user_id": int(user_id),
            "guild_id": int(guild_id) if guild_id is not None else None,
            "channel_id": int(channel_id),
            "message_id": int(message_id),
            "state": state or {},
            "status": "active",
            "version": 0,
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
        }
        if await cache.exists(_session_key(sid)):
            continue
        await _store_session(cache, payload)
        return payload
    raise RuntimeError("Could not create interaction session id after retries")


async def get_session(session_id: str) -> Optional[dict[str, Any]]:
    cache = get_cache()
    return await _load_session(cache, session_id)


async def set_session_message(session_id: str, message_id: int) -> None:
    cache = get_cache()
    session = await _load_session(cache, session_id)
    if session is None:
        return
    now = _now_ts()
    session["message_id"] = int(message_id)
    session["updated_at"] = now
    await _store_session(cache, session)


async def try_transition(
    *,
    session_id: str,
    expected_version: int,
    new_state: Optional[dict[str, Any]] = None,
    new_status: Optional[str] = None,
    extend_ttl_seconds: Optional[int] = None,
) -> bool:
    """Best-effort compare-and-set transition by version."""
    cache = get_cache()
    lock_key = _lock_key(session_id)
    for _ in range(8):
        try:
            await cache.add(lock_key, "1", ttl=2)
        except Exception:
            await asyncio.sleep(0.01)
            continue
        try:
            session = await _load_session(cache, session_id)
            if session is None:
                return False
            if int(session.get("version", -1)) != int(expected_version):
                return False
            if session.get("status") not in ACTIVE_STATUSES:
                return False

            now = _now_ts()
            if new_state is not None:
                session["state"] = new_state
            if new_status is not None:
                session["status"] = new_status
            if extend_ttl_seconds is not None:
                session["expires_at"] = now + max(1, int(extend_ttl_seconds))
            session["updated_at"] = now
            session["version"] = int(session.get("version", 0)) + 1
            await _store_session(cache, session)
            return True
        finally:
            await cache.delete(lock_key)
    return False


async def mark_terminal(session_id: str, status: str) -> None:
    cache = get_cache()
    session = await _load_session(cache, session_id)
    if session is None:
        return
    now = _now_ts()
    status_value = status if status in TERMINAL_STATUSES else "failed"
    session["status"] = status_value
    session["updated_at"] = now
    await _store_session(cache, session)


def is_expired(session_doc: dict[str, Any]) -> bool:
    return int(session_doc.get("expires_at", 0)) <= _now_ts()
