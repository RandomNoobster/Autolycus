from __future__ import annotations
from typing import TYPE_CHECKING, Awaitable
from async_property import async_cached_property
from enums import *
from ...utils import get_date_from_string, execute_query
from . import Nation, BaseClass, Treasure, TreatyType


__all__ = ["Alliance", "AlliancePrivate", "Treaty"]


class Alliance(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.name = str(self.name)
        self.acronym = str(self.acronym)
        self.score = float(self.score)
        self.color = Color(self.color)
        self.date = get_date_from_string(self.date)
        self.average_score = float(self.average_score)
        self.accept_members = bool(self.accept_members)
        self.flag = str(self.flag)
        self.forum_link = str(self.forum_link)
        self.discord_link = str(self.discord_link)
        self.wiki_link = str(self.wiki_link)

        if TYPE_CHECKING:
            # Type hinting for async properties
            self.members: Awaitable[list[Nation]]
            self.private: Awaitable[AlliancePrivate]
            self.treasures: Awaitable[list[Treasure]]

    @async_cached_property
    async def members(self) -> Awaitable[list[Nation]]:
        members = await execute_query(f"SELECT * FROM `nations` WHERE `alliance_id` = {self.id}")
        return [Nation(member) for member in members]

    @async_cached_property
    async def private(self) -> Awaitable[AlliancePrivate]:
        alliance = await execute_query(f"SELECT * FROM `alliances_private` WHERE `id` = {self.id}")
        return AlliancePrivate(alliance[0])
    
    @async_cached_property
    async def treasures(self) -> Awaitable[AlliancePrivate]:
        treasures = await execute_query(f"SELECT * FROM `treasures` WHERE `nation_id` IN (SELECT `id` FROM `nations` WHERE `alliance_id` = {self.id})")
        return [Treasure(treasure) for treasure in treasures]
    



class AlliancePrivate(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
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


class Treaty(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)
        self.id = int(self.id)

        # Ensuring types
        self.date = get_date_from_string(self.date)
        self.treaty_type = TreatyType(self.treaty_type)
        self.treaty_url = str(self.treaty_url)
        self.turns_left = int(self.turns_left)
        self.sender_id = int(self.sender_id)
        self.receiver_id = int(self.receiver_id)
        self.approved = bool(self.approved)

        # Type hinting for async properties
        self.sender: Awaitable[Alliance]
        self.receiver: Awaitable[Alliance]

    @async_cached_property
    async def sender(self) -> Awaitable[Alliance]:
        alliance = await execute_query(f"SELECT * FROM `alliances` WHERE `id` = {self.sender_id}")
        return Alliance(alliance[0])

    @async_cached_property
    async def receiver(self) -> Awaitable[Alliance]:
        alliance = await execute_query(f"SELECT * FROM `alliances` WHERE `id` = {self.receiver_id}")
        return Alliance(alliance[0])
