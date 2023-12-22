from __future__ import annotations
import re
from typing import Union
from ...env import ASYNC_MONGO
from .. import listify


__all__ = (
    "find_user",
    "find_nation",
    "find_nation_plus",
)


async def find_user(self, arg):
    if isinstance(arg, str):
        arg = arg.strip()

    db = ASYNC_MONGO.global_users

    if str(arg).isdigit():
        if x := await db.find_one({"id": str(arg)}):
            return x
        elif x := await db.find_one({"user": int(arg)}):
            return x
    elif "@" in arg or ".com" in arg:
        new_arg = re.sub("[^0-9]", "", arg)
        if len(new_arg) > 0:
            if x := await db.find_one({"id": new_arg}):
                return x
            elif x := await db.find_one({"user": int(new_arg)}):
                return x
    else:
        members = self.bot.get_all_members()
        for member in members:
            if arg.lower() in member.name.lower():
                if x := await db.find_one({"user": member.id}):
                    return x
            elif arg.lower() in member.display_name.lower():
                if x := await db.find_one({"user": member.id}):
                    return x
            elif str(member).lower() == arg.lower():
                if x := await db.find_one({"user": member.id}):
                    return x

    return {}


async def find_nation(arg: Union[str, int]) -> Union[dict, None]:
    if isinstance(arg, str):
        arg = arg.strip()

    new_arg = re.sub("[^0-9]", "", str(arg))
    if result := await listify(ASYNC_MONGO.world_nations.find({"id": str(new_arg)}).collation({"locale": "en", "strength": 1})):
        return result[0]
    elif result := await listify(ASYNC_MONGO.world_nations.find({"nation_name": arg}).collation({"locale": "en", "strength": 1})):
        return result[0]
    elif result := await listify(ASYNC_MONGO.world_nations.find({"leader_name": arg}).collation({"locale": "en", "strength": 1})):
        return result[0]
    elif result := await listify(ASYNC_MONGO.world_nations.find({"discord": arg}).collation({"locale": "en", "strength": 1})):
        return result[0]
    else:
        return None


# only returns a nation if it is at least 1 hour old
async def find_nation_plus(self, arg: Union[str, int]) -> Union[dict, None]:
    if isinstance(arg, str):
        arg = arg.strip()
    nation = await find_nation(arg)
    if nation == None:
        nation = await find_user(self, arg)
        if not nation:
            return None
        else:
            nation = await find_nation(nation['id'])
            if nation == None:
                return None
    return nation


