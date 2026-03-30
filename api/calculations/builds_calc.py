"""Builds Calculator API facade."""

import logging
import os
from typing import Any, Dict, Optional

from logic.api_client import call as call_api
from logic.builds import calculate_builds as calculate_builds_logic

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_KEY")
_BOT_KEY = os.getenv("BOT_KEY")


async def _call_pnw(query: str, *, use_bot_key: bool = False) -> dict[str, Any]:
    if not _API_KEY:
        raise RuntimeError("API_KEY environment variable must be set for builds calculations")
    return await call_api(query, api_key=_API_KEY, use_bot_key=use_bot_key, bot_key=_BOT_KEY)


async def calculate_builds(
    nation_id: str,
    infra: Optional[int] = None,
    land: Optional[int] = None,
    mmr: str = "0/0/0/0",
    continent_override: Optional[str] = None,
    use_live_prices: bool = True,
    include_military_upkeep: bool = False,
    projects_override: Optional[list[str]] = None,
    domestic_policy_override: Optional[str] = None,
    military_upkeep_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Delegate build calculations to the shared logic layer.

    Per PWPedia "Infrastructure" article; centralizes all build math in
    logic.builds so HTTP facades only orchestrate parameter handling.
    """
    try:
        return await calculate_builds_logic(
            call_pnw=_call_pnw,
            nation_id=str(nation_id),
            infra=infra,
            land=land,
            mmr=mmr,
            continent_override=continent_override,
            use_live_prices=use_live_prices,
            include_military_upkeep=include_military_upkeep,
            projects_override=projects_override,
            domestic_policy_override=domestic_policy_override,
            military_upkeep_mode=military_upkeep_mode,
        )
    except Exception as exc:  # pragma: no cover - surface for API logs
        logger.error("Build calculation failed", exc_info=True)
        raise exc
