"""/raids and /nuketargets target selection, plus the shared date and turn helpers."""

import asyncio
import contextlib
import os
import sqlite3
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.cogs import military
from database.sqlite_cache import ensure_table_and_columns, find_nation, get_nations_by_ids, upsert
from logic.raids import turns_since

UTC = timezone.utc
NOW = datetime(2026, 11, 14, 13, 30, tzinfo=UTC)  # turn started 12:00 UTC
WRITTEN_THIS_TURN = int(datetime(2026, 11, 14, 12, 10, tzinfo=UTC).timestamp())
WRITTEN_LAST_TURN = int(datetime(2026, 11, 14, 11, 50, tzinfo=UTC).timestamp())


def _row(nation_id: int, **fields) -> dict:
    row = {
        "id": nation_id,
        "nation_name": f"Nation {nation_id}",
        "alliance_id": "0",
        "alliance_position": "NOALLIANCE",
        "score": 1000.0,
        "color": "red",
        "beige_turns": 0,
        "vacation_mode_turns": 0,
        "last_active": "2026-11-01T10:00:00+00:00",
        "soldiers": 1000,
        "tanks": 10,
        "aircraft": 5,
        "ships": 1,
        "missiles": 0,
        "nukes": 0,
        "population": 100000,
        "nation_loot_value": 1_000_000,
        "monetary_net_num": 50_000,
        "net_cash_num": 40_000,
        "def_slots": 0,
        "treasure_count": 0,
        "_created_at": WRITTEN_THIS_TURN,
    }
    row.update(fields)
    return row


def _select(rows, **overrides):
    options = dict(
        who=military.WHO_ALL,
        max_wars=3,
        inactive_limit=0,
        include_beige=True,
        minimum_loot=0,
        excluded_alliances=set(military._EXCLUDED_RAID_ALLIANCES),
        now=NOW,
        fallback_written_at=None,
    )
    options.update(overrides)
    return {t["id"]: t for t in military.select_raid_targets(rows, **options)}


def test_live_update_rows_do_not_break_raids():
    rows = [
        # Subscription rows: offset-less times, NULL counts and positions.
        _row(1, last_active="2026-11-02T10:00:00", soldiers=None, population=None, alliance_position=None),
        _row(2, last_active="-0001-11-30 00:00:00", alliance_position=3, alliance_id="77"),
    ]
    targets = _select(rows)
    assert targets[1]["days_inactive"] == 12
    assert targets[2]["alliance_position"] == "OFFICER"
    ground, air, naval = military.raid_win_rates({"soldiers": 1000, "tanks": 0}, targets[1])
    assert 0 <= ground <= 1 and 0 <= air <= 1 and 0 <= naval <= 1


def test_raids_use_the_stored_defensive_slots_and_skip_vacation_mode():
    rows = [_row(1, def_slots=2), _row(2, def_slots=0), _row(3, vacation_mode_turns=12)]
    assert sorted(_select(rows, max_wars=1)) == [2]
    assert 3 not in _select(rows)


def test_turns_count_down_from_when_the_row_was_written():
    rows = [
        _row(1, beige_turns=1, _created_at=WRITTEN_LAST_TURN),  # left beige at 12:00
        _row(2, beige_turns=1, _created_at=WRITTEN_THIS_TURN),
        _row(3, beige_turns=0, _created_at=WRITTEN_LAST_TURN),  # never below 0
    ]
    targets = _select(rows)
    assert [targets[i]["beige_turns"] for i in (1, 2, 3)] == [0, 1, 0]
    assert sorted(_select(rows, include_beige=False)) == [1, 3]


def test_who_and_do_not_raid_filters():
    rows = [
        _row(1),
        _row(2, alliance_id="50", alliance_position="APPLICANT"),
        _row(3, alliance_id="50", alliance_position="MEMBER"),
        _row(4, alliance_id="4729", alliance_position="MEMBER"),
        _row(5, alliance_id="900", alliance_position="MEMBER"),
    ]
    assert sorted(_select(rows)) == [1, 2, 3, 5]
    assert sorted(_select(rows, who=military.WHO_APPLICANTS)) == [1, 2]
    assert sorted(_select(rows, who=military.WHO_NO_ALLIANCE)) == [1]
    assert 5 not in _select(rows, excluded_alliances={"900"})


def test_performance_filter_drops_nations_with_no_recorded_loot():
    target = {"groundwin": 0.9, "nation_loot_value": 0, "net_cash_num": 50_000}
    assert military.is_bad_raid_target(target)
    assert not military.is_bad_raid_target({**target, "nation_loot_value": 5})


def test_turns_since_counts_even_hour_turn_changes():
    assert turns_since(WRITTEN_THIS_TURN, NOW) == 0
    assert turns_since(WRITTEN_LAST_TURN, NOW) == 1
    assert turns_since(None, NOW) == 0


def _nuke_row(nation_id, **fields):
    row = {
        "id": nation_id,
        "nation_name": f"N{nation_id}",
        "alliance_id": "0",
        "alliance_position": "NOALLIANCE",
        "score": 1000.0,
        "color": "red",
        "beige_turns": 0,
        "vacation_mode_turns": 0,
        "def_slots": 0,
        "cities": [{"infrastructure": 2000, "land": 1000}],
        "_created_at": WRITTEN_THIS_TURN,
    }
    row.update(fields)
    return row


def _rank(rows, user=None, **overrides):
    user = user or {"id": "1", "wars": [], "guiding_satellite": False}
    options = dict(alliance_ids=set(), include_beige=False, include_slotted=False,
                   sort_key="nuke_damage", now=NOW, fallback_written_at=None)
    options.update(overrides)
    return [row["id"] for row in military.rank_nuke_targets(user, rows, **options)]


def test_nuke_targets_skip_slotted_and_current_enemies_by_id_text():
    user = {"id": "1", "wars": [{"attid": "1", "defid": "3", "turnsleft": 20, "war_type": "ATTRITION"}]}
    rows = [_nuke_row(1), _nuke_row(2, def_slots=3), _nuke_row(3), _nuke_row(4)]
    assert _rank(rows, user) == ["4"]
    assert sorted(_rank(rows, user, include_slotted=True)) == ["2", "3", "4"]


def test_nuke_targets_never_list_vacation_mode_and_respect_alliances():
    rows = [_nuke_row(2, vacation_mode_turns=5), _nuke_row(3, alliance_id="7"), _nuke_row(4)]
    assert sorted(_rank(rows, include_beige=True)) == ["3", "4"]
    assert _rank(rows, alliance_ids={"7"}) == ["3"]


def test_nuke_damage_matches_the_website_ranking():
    rows = [_nuke_row(2, cities=[{"infrastructure": 1000, "land": 1000}]),
            _nuke_row(3, cities=[{"infrastructure": 3000, "land": 1000}])]
    ranked = military.rank_nuke_targets({"id": "1", "wars": []}, rows, alliance_ids=set(), include_beige=False,
                                        include_slotted=False, sort_key="nuke_damage", now=NOW,
                                        fallback_written_at=None)
    assert [row["id"] for row in ranked] == ["3", "2"]
    assert ranked[0]["max_infra"] == 3000


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Raid on Rose (123456)", "123456"), ("Raids (week 3)", None), ("war (12) (34)", "34"), ("chat", None)],
)
def test_thread_nation_id(name, expected):
    thread = discord.Thread.__new__(discord.Thread)
    thread.name = name
    assert military.thread_nation_id(thread) == expected
    assert military.thread_nation_id(SimpleNamespace(name=name)) is None  # not a thread


def test_war_fields_stop_before_discords_embed_limit():
    embed = discord.Embed(title="t", description="d" * 600)
    fields = []
    for i in range(10):
        fields.append(("​", "​", False))
        fields.append((f"Enemy {i}", "x" * 800, True))
    military.add_fields_within_limit(embed, fields, noun="wars")
    assert len(embed) <= 6000
    assert embed.fields[-1].name.endswith("more wars not shown")


def test_get_nations_by_ids_and_find_nation_without_the_discord_column(tmp_path, monkeypatch):
    path = tmp_path / "nations.db"
    with contextlib.closing(sqlite3.connect(path)) as conn:
        for row in ({"id": 5, "nation_name": "Five", "leader_name": "L5", "discord": "alice",
                     "cities": '[{"infrastructure": 10}]'},
                    {"id": 6, "nation_name": "Six", "leader_name": "L6", "discord": "bob", "cities": None}):
            ensure_table_and_columns(conn, "nations", row)
            upsert(conn, "nations", row)
        conn.commit()
    found = get_nations_by_ids(path, ["5", 6, "x"], ["cities"], {"cities"})
    assert found[5]["cities"] == [{"infrastructure": 10}]
    assert set(found) == {5, 6}

    monkeypatch.setattr("database.sqlite_cache.get_nations_db_path", lambda: path)
    assert find_nation("alice")["id"] == 5
    assert find_nation("alice", include_discord=False) is None


def test_damage_links_without_running_the_damage_calculation(monkeypatch):
    cog = military.TargetFinding(bot=SimpleNamespace())
    cog.battle_calc = AsyncMock(side_effect=AssertionError("not needed for a link"))

    async def resolve(ctx, nation1, nation2):
        return "11", "22"

    monkeypatch.setattr(cog, "_resolve_nation_pair", resolve)
    ctx = SimpleNamespace(defer=AsyncMock(), respond=AsyncMock())
    asyncio.run(military.TargetFinding.damage.callback(cog, ctx, None, None))
    assert "nation1=11&nation2=22" in ctx.respond.await_args.kwargs["content"]


def test_own_nation_and_alliance_are_not_targets():
    rows = [_row(1), _row(2, alliance_id="50", alliance_position="MEMBER"), _row(3)]
    assert sorted(_select(rows, attacker_id="1", attacker_alliance_id="50")) == [3]
    nukes = [_nuke_row(1), _nuke_row(2, alliance_id="50"), _nuke_row(3)]
    user = {"id": "1", "wars": [], "alliance": {"id": "50", "name": "Us"}}
    assert _rank(nukes, user) == ["3"]
