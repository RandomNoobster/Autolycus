"""Damage Calculator API facade."""

import logging
import os
from typing import Any, Dict

from logic.api_client import call as call_api
from logic.damage import calculate_damage as calculate_damage_logic

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_KEY")
_BOT_KEY = os.getenv("BOT_KEY")


async def _call_pnw(query: str, *, use_bot_key: bool = False) -> dict[str, Any]:
    if not _API_KEY:
        raise RuntimeError("API_KEY environment variable must be set for damage calculations")
    return await call_api(query, api_key=_API_KEY, use_bot_key=use_bot_key, bot_key=_BOT_KEY)


async def calculate_damage(nation1_id: str, nation2_id: str) -> Dict[str, Any]:
    try:
        return await calculate_damage_logic(
            call_pnw=_call_pnw,
            nation1_id=nation1_id,
            nation2_id=nation2_id,
        )
    except Exception as exc:  # pragma: no cover - surface for API logs
        logger.error("Damage calculation failed", exc_info=True)
        raise exc
