"""Tests for nation lookups when a ``global_users`` profile has no linked nation.

The website creates reminder-only profiles (``user`` + beige alert settings, no ``id``).
Lookups must treat them as "no nation" instead of raising ``KeyError``.
"""

import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.discord_utils import helpers

STUB_PROFILE = {"user": 1, "beige_alerts": [], "beige_alerts_config": []}
LINKED_PROFILE = {"user": 1, "id": "123"}
NATION = {"id": 123, "nation_name": "Testland", "leader_name": "Tester"}


class FakeMember:
    def __init__(self, member_id: int, name: str, display_name: str | None = None) -> None:
        self.id = member_id
        self.name = name
        self.display_name = display_name or name

    def __str__(self) -> str:
        return self.name


class FakeBot:
    def __init__(self, members: list[FakeMember] | None = None) -> None:
        self.members = members or []
        self.member_scans = 0

    def get_all_members(self):
        self.member_scans += 1
        return iter(self.members)


def _patch_lookups(monkeypatch: pytest.MonkeyPatch, *, users: dict, nations: dict) -> list:
    """Replace SQLite/Mongo lookups with in-memory fakes keyed by ``str(arg)``."""
    nation_lookups: list = []

    def fake_find_nation(arg, include_discord=True):
        nation_lookups.append(arg)
        found = nations.get(str(arg))
        if found is None and include_discord:
            found = nations.get(f"discord:{arg}")
        return dict(found) if found else None

    async def fake_get_global_user_by_any(arg):
        return users.get(str(arg))

    monkeypatch.setattr("database.sqlite_cache.find_nation", fake_find_nation)
    monkeypatch.setattr(helpers, "db_find_nation", fake_find_nation)
    monkeypatch.setattr(helpers, "get_global_user_by_any", fake_get_global_user_by_any)
    return nation_lookups


# --- helpers.find_nation_plus / linked_nation_id ---


@pytest.mark.parametrize("arg", [1, "1"])
def test_find_nation_plus_returns_none_for_reminder_only_profile(monkeypatch, arg):
    lookups = _patch_lookups(monkeypatch, users={"1": STUB_PROFILE}, nations={"123": NATION})
    bot = FakeBot([FakeMember(1, "1")])

    assert asyncio.run(helpers.find_nation_plus(bot, arg)) is None
    assert lookups == [arg]  # no follow-up lookup with a missing nation id
    assert bot.member_scans == 0  # a matched profile never triggers the member scan


def test_find_nation_plus_returns_nation_for_linked_profile(monkeypatch):
    lookups = _patch_lookups(monkeypatch, users={"1": LINKED_PROFILE}, nations={"123": NATION})

    assert asyncio.run(helpers.find_nation_plus(FakeBot(), 1)) == NATION
    assert lookups == [1, "123"]


def test_find_nation_plus_member_scan_skips_reminder_only_profiles(monkeypatch):
    _patch_lookups(
        monkeypatch,
        users={"1": STUB_PROFILE, "2": {"user": 2, "id": "123"}},
        nations={"123": NATION},
    )
    bot = FakeBot([FakeMember(1, "tester"), FakeMember(2, "tester_alt", display_name="Tester")])

    assert asyncio.run(helpers.find_nation_plus(bot, "tester")) == NATION


def test_find_nation_plus_ignores_partial_member_names(monkeypatch):
    # "Rose" must not resolve to the verified member "primrose".
    _patch_lookups(monkeypatch, users={"2": {"user": 2, "id": "123"}}, nations={"123": NATION})
    bot = FakeBot([FakeMember(2, "primrose")])

    assert asyncio.run(helpers.find_nation_plus(bot, "Rose")) is None


def test_verified_member_beats_the_in_game_discord_field(monkeypatch):
    impostor = {"id": 999, "nation_name": "Impostor"}
    _patch_lookups(
        monkeypatch,
        users={"2": {"user": 2, "id": "123"}},
        nations={"123": NATION, "discord:alice": impostor},
    )
    bot = FakeBot([FakeMember(2, "alice")])

    assert asyncio.run(helpers.find_nation_plus(bot, "alice")) == NATION
    # Without a verified member, the in-game field is still a last resort.
    assert asyncio.run(helpers.find_nation_plus(FakeBot(), "alice")) == impostor


def test_member_lookup_asks_the_guild_when_the_cache_misses(monkeypatch):
    _patch_lookups(monkeypatch, users={"2": {"user": 2, "id": "123"}}, nations={"123": NATION})

    class FakeGuild:
        async def query_members(self, query, limit):
            return [FakeMember(2, "bob"), FakeMember(3, "bobby")]

    assert asyncio.run(helpers.find_nation_plus(FakeBot(), "Bob", guild=FakeGuild())) == NATION


def test_find_nation_plus_member_scan_with_only_reminder_profiles_returns_none(monkeypatch):
    _patch_lookups(monkeypatch, users={"1": STUB_PROFILE}, nations={"123": NATION})
    bot = FakeBot([FakeMember(1, "tester")])

    assert asyncio.run(helpers.find_nation_plus(bot, "tester")) is None


@pytest.mark.parametrize(
    ("user_doc", "expected"),
    [
        (None, None),
        ({}, None),
        (STUB_PROFILE, None),
        ({"user": 1, "id": None}, None),
        ({"user": 1, "id": ""}, None),
        ({"user": 1, "id": "   "}, None),
        ({"user": 1, "id": True}, None),
        ({"user": 1, "id": "123"}, "123"),
        ({"user": 1, "id": 123}, "123"),
    ],
)
def test_linked_nation_id(user_doc, expected):
    assert helpers.linked_nation_id(user_doc) == expected


# --- bot.cogs.general commands ---


class FakeCtx:
    """Minimal ApplicationContext stand-in that records sent/edited content."""

    def __init__(self, author_id: int = 1) -> None:
        self.author = SimpleNamespace(id=author_id, name="tester")
        self.guild = None
        self.messages: list[str | None] = []

    async def defer(self, *args, **kwargs) -> None:
        return None

    async def respond(self, content=None, **kwargs) -> None:
        self.messages.append(content)

    async def edit(self, content=None, **kwargs) -> None:
        self.messages.append(content)


class FakeLoadingDisplay:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def start(self, message: str) -> None:
        return None

    async def update(self, *args, **kwargs) -> None:
        return None

    async def clear(self) -> None:
        return None


def _cog_self(bot: FakeBot) -> SimpleNamespace:
    async def reraise(ctx, error, *, command_name):
        raise error

    return SimpleNamespace(bot=bot, _handle_command_exception=reraise)


def test_who_self_lookup_with_reminder_only_profile_asks_to_verify(monkeypatch):
    from bot.cogs import general

    _patch_lookups(monkeypatch, users={"1": STUB_PROFILE}, nations={"123": NATION})
    ctx = FakeCtx(author_id=1)

    asyncio.run(general.Background.who.callback(_cog_self(FakeBot()), ctx))

    assert ctx.messages == [helpers.NATION_NOT_LINKED_MESSAGE]


def test_who_lookup_of_other_person_keeps_not_found_message(monkeypatch):
    from bot.cogs import general

    _patch_lookups(monkeypatch, users={"1": STUB_PROFILE}, nations={"123": NATION})
    ctx = FakeCtx(author_id=2)

    asyncio.run(general.Background.who.callback(_cog_self(FakeBot()), ctx, person="1"))

    assert ctx.messages == ["I did not find that nation!"]


def test_revenue_nation_self_lookup_with_reminder_only_profile_asks_to_verify(monkeypatch):
    from bot.cogs import general

    lookups = _patch_lookups(monkeypatch, users={"1": STUB_PROFILE}, nations={"123": NATION})
    monkeypatch.setattr(general, "LoadingDisplay", FakeLoadingDisplay)
    ctx = FakeCtx(author_id=1)

    asyncio.run(general.Background.nation_revenue.callback(_cog_self(FakeBot()), ctx))

    assert lookups == [1]  # fell back to the SQLite lookup instead of reading user['id']
    assert ctx.messages[-1] == helpers.NATION_NOT_LINKED_MESSAGE


def test_revenue_nation_other_person_with_reminder_only_profile_not_found(monkeypatch):
    from bot.cogs import general

    _patch_lookups(monkeypatch, users={"1": STUB_PROFILE}, nations={"123": NATION})
    monkeypatch.setattr(general, "LoadingDisplay", FakeLoadingDisplay)
    ctx = FakeCtx(author_id=2)

    asyncio.run(general.Background.nation_revenue.callback(_cog_self(FakeBot()), ctx, person="1"))

    assert ctx.messages[-1] == "I could not find that person!"


def test_unverify_leaves_a_reminder_only_profile_alone(monkeypatch):
    from bot.cogs import general

    deleted = []

    async def get_verification(user_id):
        return STUB_PROFILE

    async def delete_verification(user_id):
        deleted.append(user_id)
        return STUB_PROFILE

    monkeypatch.setattr(general, "get_verification", get_verification)
    monkeypatch.setattr(general, "delete_verification", delete_verification)
    ctx = FakeCtx(author_id=1)
    embeds = []

    async def respond(content=None, embed=None, **kwargs):
        embeds.append(embed)

    ctx.respond = respond
    asyncio.run(general.Background.unverify.callback(_cog_self(FakeBot()), ctx))

    assert deleted == []  # their reminders survive
    assert embeds[0].title == "Not linked"
