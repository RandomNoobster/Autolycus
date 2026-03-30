from __future__ import annotations

import logging
import os

from . import queries
from infra.cache import cache_prices

from .api_client import call
from .common import RSS
from .merge_utils import get_query

logger = logging.getLogger(__name__)
_API_KEY = os.getenv("API_KEY")
_BOT_KEY = os.getenv("BOT_KEY")


@cache_prices(ttl=300)  # Cache for 5 minutes - prices update ~hourly
async def get_prices() -> dict[str, float]:
    """Fetch current trade prices for all resources.

    Mirrors legacy pw_utils.get_prices behaviour while using the shared
    api_client module for GraphQL access.
    
    Note: This function is cached to reduce P&W API calls. Cache TTL is 5 minutes.
    """
    logger.debug("Fetching fresh prices from P&W API (cache miss or expired)")
    response = await call(
        f"{{tradeprices(page:1 first:1){{data{get_query(queries.PRICES)}}}}}",
        _API_KEY,
    )
    prices = response['data']['tradeprices']['data'][0]
    prices['money'] = 1
    return prices


async def total_value(resources: dict[str, float]) -> int:
    """Calculate the total market value of the provided resources."""
    prices = await get_prices()
    total = 0
    for resource, amount in resources.items():
        if resource in RSS:
            total += amount * prices[resource]
    return int(total)


async def withdraw(api_key: str, resources: dict[str, float]) -> bool:
    """Perform a bank withdrawal via GraphQL mutation.

    Returns True when the withdrawal succeeds; logs and returns False on error.
    """
    try:
        call_string = ""
        for rs, value in resources.items():
            call_string += f"{rs}:{value} "
        mutation = f"mutation{{{{bankWithdraw({call_string.strip()}){{{{id}}}}}}}}"
        response = await call(mutation, api_key, use_bot_key=True, bot_key=_BOT_KEY)
        if "errors" in response:
            raise Exception(response["errors"])
        return True
    except Exception as exc:  # pragma: no cover - logging side-effect
        logger.error(
            "Error withdrawing resources. Api key: %s Resources: %s Error: %s",
            api_key,
            resources,
            exc,
            exc_info=True,
        )
        return False
