from __future__ import annotations
from typing import TYPE_CHECKING
from cache import AsyncTTL
from .. import execute_query

if TYPE_CHECKING:
    from ...types.classes.nation import ResourceWrapper
    from ...types.classes.trade import TradePrices

__all__ = ["get_prices", "total_value"]

@AsyncTTL(time_to_live=60, maxsize=1)
async def get_prices() -> TradePrices:
    """
    Gets the current trade prices.
    """
    from ...types.classes.trade import TradePrices
    prices = await execute_query("SELECT * FROM `trade_prices` ORDER BY `id` DESC LIMIT 1")
    return TradePrices(prices[0])


async def total_value(resources: ResourceWrapper) -> int:
    """
    Calculates the total value of a resource wrapper.
    """
    prices = await get_prices()
    x = 0
    for resource in resources:
        x += prices[resource] * resources[resource]
    return x
