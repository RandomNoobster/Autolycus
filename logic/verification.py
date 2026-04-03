"""
Shared verification service for bot and web flows.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, TypedDict

from database.users import (
    get_verification,
    get_verification_by_nation_id,
    get_verification_by_nation_id_sync,
    get_verification_sync,
    set_verification,
    set_verification_sync,
)
from logic import queries
from logic.api_client import query_sync
from logic.merge_utils import get_query


class VerificationResult(TypedDict):
    ok: bool
    code: str
    nation_id: str | None
    message: str
    relinked: bool


VerifyCall = Callable[[str], Awaitable[dict[str, Any]]]


def normalize_nation_id(nation_input: str) -> str:
    """Extract numeric nation id from raw input."""
    return re.sub(r"[^0-9]", "", str(nation_input or ""))


async def verify_discord_nation_link(
    *,
    discord_user_id: int,
    discord_username: str,
    nation_input: str,
    call_func: VerifyCall,
) -> VerificationResult:
    nation_id = normalize_nation_id(nation_input)
    if not nation_id:
        return {
            "ok": False,
            "code": "INVALID_NATION_ID",
            "nation_id": None,
            "message": "Nation id is required.",
            "relinked": False,
        }

    response = await call_func(f"{{nations(first:1 id:{nation_id}){{data{get_query(queries.VERIFY)}}}}}")
    nations = (((response or {}).get("data") or {}).get("nations") or {}).get("data") or []
    if not nations:
        return {
            "ok": False,
            "code": "NOT_FOUND",
            "nation_id": nation_id,
            "message": f"I could not find a nation with an id of `{nation_id}`",
            "relinked": False,
        }

    nation = nations[0] or {}
    nation_discord = str(nation.get("discord") or "").strip().lower()
    if nation_discord != str(discord_username or "").strip().lower():
        return {
            "ok": False,
            "code": "OWNERSHIP_MISMATCH",
            "nation_id": nation_id,
            "message": "Nation Discord username does not match the signed-in Discord username.",
            "relinked": False,
        }

    conflict = await get_verification_by_nation_id(nation_id)
    if conflict and int(conflict.get("user", 0)) != int(discord_user_id):
        return {
            "ok": False,
            "code": "LINK_CONFLICT",
            "nation_id": nation_id,
            "message": "That nation is already linked to a different Discord user.",
            "relinked": False,
        }

    existing = await get_verification(discord_user_id)
    relinked = bool(existing and str(existing.get("id", "")) != nation_id)
    await set_verification(discord_user_id, nation_id)
    return {
        "ok": True,
        "code": "SUCCESS",
        "nation_id": nation_id,
        "message": "Verification successful.",
        "relinked": relinked,
    }


def verify_discord_nation_link_sync(
    *,
    discord_user_id: int,
    discord_username: str,
    nation_input: str,
    api_key: str,
) -> VerificationResult:
    """Same behavior as verify_discord_nation_link for WSGI: uses sync I/O only.

    Avoids asyncio.run() with Motor, which can raise 'Event loop is closed' when
    the global AsyncIOMotorClient is reused across per-request event loops.
    """
    nation_id = normalize_nation_id(nation_input)
    if not nation_id:
        return {
            "ok": False,
            "code": "INVALID_NATION_ID",
            "nation_id": None,
            "message": "Nation id is required.",
            "relinked": False,
        }

    response = query_sync(
        f"{{nations(first:1 id:{nation_id}){{data{get_query(queries.VERIFY)}}}}}",
        api_key=api_key,
    )
    nations = (((response or {}).get("data") or {}).get("nations") or {}).get("data") or []
    if not nations:
        return {
            "ok": False,
            "code": "NOT_FOUND",
            "nation_id": nation_id,
            "message": f"I could not find a nation with an id of `{nation_id}`",
            "relinked": False,
        }

    nation = nations[0] or {}
    nation_discord = str(nation.get("discord") or "").strip().lower()
    if nation_discord != str(discord_username or "").strip().lower():
        return {
            "ok": False,
            "code": "OWNERSHIP_MISMATCH",
            "nation_id": nation_id,
            "message": "Nation Discord username does not match the signed-in Discord username.",
            "relinked": False,
        }

    conflict = get_verification_by_nation_id_sync(nation_id)
    if conflict and int(conflict.get("user", 0)) != int(discord_user_id):
        return {
            "ok": False,
            "code": "LINK_CONFLICT",
            "nation_id": nation_id,
            "message": "That nation is already linked to a different Discord user.",
            "relinked": False,
        }

    existing = get_verification_sync(discord_user_id)
    relinked = bool(existing and str(existing.get("id", "")) != nation_id)
    set_verification_sync(discord_user_id, nation_id)
    return {
        "ok": True,
        "code": "SUCCESS",
        "nation_id": nation_id,
        "message": "Verification successful.",
        "relinked": relinked,
    }
