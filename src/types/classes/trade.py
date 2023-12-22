from __future__ import annotations
from typing import TYPE_CHECKING, Awaitable
from async_property import async_cached_property
from enums import *
from ...utils import get_date_from_string, execute_query
from . import BaseClass, Nation, Alliance


__all__ = ["Trade", "TradePrices", "TreasureTrade", "Embargo"]


class Trade(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.type = TradeType(self.type)
        self.date = get_date_from_string(self.date)
        self.sender_id = int(self.sender_id)
        self.receiver_id = int(self.receiver_id)
        self.offer_resource = ResourceEnum(self.offer_resource)
        self.offer_amount = int(self.offer_amount)
        self.buy_or_sell = str(self.buy_or_sell)
        self.price = int(self.price)
        self.accepted = bool(self.accepted)
        self.date_accepted = get_date_from_string(self.date_accepted)
        self.original_trade_id = int(self.original_trade_id)

        if TYPE_CHECKING:
            # Type hinting for async properties
            self.sender: Awaitable[Nation]
            self.receiver: Awaitable[Nation]

    @async_cached_property
    async def sender(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.sender_id}")
        return Nation(nation[0])

    @async_cached_property
    async def receiver(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.receiver_id}")
        return Nation(nation[0])


class TradePrices(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.date = get_date_from_string(self.date)
        self.money = float(self.money)
        self.coal = float(self.coal)
        self.oil = float(self.oil)
        self.uranium = float(self.uranium)
        self.iron = float(self.iron)
        self.bauxite = float(self.bauxite)
        self.lead = float(self.lead)
        self.gasoline = float(self.gasoline)
        self.munitions = float(self.munitions)
        self.steel = float(self.steel)
        self.aluminum = float(self.aluminum)
        self.food = float(self.food)
        self.credits = float(self.credits)
    

class TreasureTrade(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.offer_date = get_date_from_string(self.offer_date)
        self.accept_date = get_date_from_string(self.accept_date)
        self.sender_id = int(self.sender_id)
        self.receiver_id = int(self.receiver_id)
        self.buying = bool(self.buying)
        self.selling = bool(self.selling)
        self.treasure = str(self.treasure)
        self.money = int(self.money)
        self.accepted = bool(self.accepted)
        self.rejected = bool(self.rejected)
        self.seller_cancelled = bool(self.seller_cancelled)

        if TYPE_CHECKING:
            # Type hinting for async properties
            self.sender: Awaitable[Nation]
            self.receiver: Awaitable[Nation]

    @async_cached_property
    async def sender(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.sender_id}")
        return Nation(nation[0])

    @async_cached_property
    async def receiver(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.receiver_id}")
        return Nation(nation[0])


class Embargo(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.date = get_date_from_string(self.date)
        self.sender_id = int(self.sender_id)
        self.receiver_id = int(self.receiver_id)
        self.reason = str(self.reason)
        self.type = EmbargoType(self.type)

        if TYPE_CHECKING:
            # Type hinting for async properties
            self.sender: Awaitable[Nation | Alliance]
            self.receiver: Awaitable[Nation | Alliance]

    @async_cached_property
    async def sender(self) -> Awaitable[Nation | Alliance]:
        if self.type in (EmbargoType.NATION_TO_NATION, EmbargoType.NATION_TO_ALLIANCE):
            sender_type = "nations"
        else:
            sender_type = "alliances"
        nation = await execute_query(f"SELECT * FROM `{sender_type}` WHERE `id` = {self.sender_id}")
        if sender_type == "nations":
            return Nation(nation[0])
        else:
            return Alliance(nation[0])

    @async_cached_property
    async def receiver(self) -> Awaitable[Nation | Alliance]:
        if self.type in (EmbargoType.NATION_TO_NATION, EmbargoType.ALLIANCE_TO_NATION):
            receiver_type = "nations"
        else:
            receiver_type = "alliances"
        nation = await execute_query(f"SELECT * FROM `{receiver_type}` WHERE `id` = {self.receiver_id}")
        if receiver_type == "nations":
            return Nation(nation[0])
        else:
            return Alliance(nation[0])
