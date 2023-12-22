from __future__ import annotations
from async_property import async_cached_property
from typing import TYPE_CHECKING, Awaitable
from enums import *
from ...utils import get_date_from_string, PROJECT_BITMAP, execute_query
from . import Nation, Alliance, BaseClass


__all__ = ["ColorBloc", "Treasure", "TaxBracket", "BankRec", "ResourceWrapper"]


class ColorBloc(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.color = Color(self.color)
        self.bloc_name = str(self.bloc_name)
        self.turn_bonus = int(self.turn_bonus)


class Treasure(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.name = str(self.name)
        self.color = Color(self.color)
        self.continent = Continent(self.continent)
        self.bonus = int(self.bonus)
        self.spawn_date = get_date_from_string(self.spawn_date)
        self.nation_id = int(self.nation_id)

        if TYPE_CHECKING:
            # Type hinting for cached properties
            self.nation: Awaitable[Nation]

    @async_cached_property
    async def nation(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.nation_id}")
        return Nation(nation[0])


class TaxBracket(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.alliance_id = int(self.alliance_id)
        self.date = get_date_from_string(self.date)
        self.date_modified = get_date_from_string(self.date_modified)
        self.last_modifier_id = int(self.last_modifier_id)
        self.tax_rate = int(self.tax_rate)
        self.resource_tax_rate = int(self.resource_tax_rate)
        self.bracket_name = str(self.bracket_name)

        if TYPE_CHECKING:
            # Type hinting for cached properties
            self.last_modifier: Awaitable[Nation]
            self.alliance: Awaitable[Alliance]

    @async_cached_property
    async def last_modifier(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.last_modifier_id}")
        return Nation(nation[0])

    @async_cached_property
    async def alliance(self) -> Awaitable[Alliance]:
        alliance = await execute_query(f"SELECT * FROM `alliances` WHERE `id` = {self.alliance_id}")
        return Alliance(alliance[0])


class BankRec(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.date = str(self.date)
        self.sender_id = int(self.sender_id)
        self.sender_type = TransactioneeType(self.sender_type)
        self.receiver_id = int(self.receiver_id)
        self.receiver_type = TransactioneeType(self.receiver_type)
        self.banker_id = int(self.banker_id)
        self.note = str(self.note)
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
        self.tax_id = int(self.tax_id)

        if TYPE_CHECKING:
            # Type hinting for async properties
            self.sender: Awaitable[Nation | Alliance]
            self.receiver: Awaitable[Nation | Alliance]
            self.banker: Awaitable[Nation]

    @async_cached_property
    async def sender(self) -> Awaitable[Nation | Alliance]:
        nation = await execute_query(f"SELECT * FROM `{self.sender_type[1]}` WHERE `id` = {self.sender_id}")
        return Nation(nation[0])

    @async_cached_property
    async def receiver(self) -> Awaitable[Nation | Alliance]:
        nation = await execute_query(f"SELECT * FROM `{self.receiver_type[1]}` WHERE `id` = {self.receiver_id}")
        return Nation(nation[0])

    @async_cached_property
    async def banker(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.banker_id}")
        return Nation(nation[0])


class ResourceWrapper(BaseClass):
    def __init__(self, json: dict = None, include_credits: bool = False, **kwargs) -> None:
        super().__init__(self, json, **kwargs)
        
        self.money = float(self.money) or 0.0
        self.coal = float(self.coal) or 0.0
        self.oil = float(self.oil) or 0.0
        self.uranium = float(self.uranium) or 0.0
        self.iron = float(self.iron) or 0.0
        self.bauxite = float(self.bauxite) or 0.0
        self.lead = float(self.lead) or 0.0
        self.gasoline = float(self.gasoline) or 0.0
        self.munitions = float(self.munitions) or 0.0
        self.steel = float(self.steel) or 0.0
        self.aluminum = float(self.aluminum) or 0.0
        self.food = float(self.food) or 0.0

        if include_credits:
            self.credits = int(self.credits)

    def __iter__(self) -> tuple[ResourceEnum, float | int]:
        for key, value in self.__dict__.items():
            yield ResourceEnum(key), value


