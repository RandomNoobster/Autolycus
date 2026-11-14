"""Scanner persistence: partial live updates, wars merging, failure handling."""

import asyncio
import contextlib
import importlib
import json
import logging
import os
import sqlite3
import sys
import time

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from database.sqlite_cache import prune_missing_ids, upsert, ensure_table_and_columns
from logic.api_client import PnWServerError

PRICES = {"money": 1, "food": 100.0}


@pytest.fixture
def scanner(monkeypatch, tmp_path):
    """Import scanner.py without touching the real logs directory or pytest's log capture."""
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("LOGS_ROOT", str(tmp_path / "logs"))
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    try:
        module = importlib.import_module("scanner")
    finally:
        for handler in list(root.handlers):
            if handler not in saved_handlers:
                root.removeHandler(handler)
                handler.close()
        for handler in saved_handlers:
            if handler not in root.handlers:
                root.addHandler(handler)
        root.setLevel(saved_level)
    return module


@pytest.fixture
def conn(tmp_path):
    with contextlib.closing(sqlite3.connect(tmp_path / "nations.db")) as connection:
        yield connection


def _persist(scanner, conn, row, source):
    return asyncio.run(scanner.persist_nation_row(conn, row, source=source, prices=dict(PRICES)))


def _stored(conn, nation_id):
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM nations WHERE id = ?", (nation_id,)).fetchone()
    conn.row_factory = None
    return dict(row)


def _war(war_id, att, dfn, date, turns, **fields):
    return {"id": war_id, "attid": att, "defid": dfn, "date": date, "turnsleft": turns, **fields}


def _scanned(nation_id=7, wars=None, **fields):
    row = {
        "id": str(nation_id),
        "nation_name": "Seven",
        "num_cities": 2,
        "cities": [{"infrastructure": 1000, "land": 1000}, {"infrastructure": 900, "land": 900}],
        "treasures": [{"name": "Gem"}],
        "wars": wars if wars is not None else [
            _war("1", "100", str(nation_id), "2026-11-10T10:00:00+00:00", 30),
        ],
    }
    row.update(fields)
    return row


def test_update_without_wars_or_treasures_keeps_the_derived_columns(scanner, conn):
    assert _persist(scanner, conn, _scanned(), "scan")["success"]
    before = _stored(conn, 7)
    assert (before["def_slots"], before["treasure_count"]) == (1, 1)

    update = {"id": 7, "nation_name": "Seven", "num_cities": 2, "cities": []}
    assert _persist(scanner, conn, update, "subscription")["success"]

    after = _stored(conn, 7)
    assert after["def_slots"] == 1
    assert str(after["time_since_war"]) == "0"
    assert after["treasure_count"] == 1
    assert len(json.loads(after["cities"])) == 2  # an empty list is a partial snapshot


def test_new_war_in_an_update_is_merged_into_the_cached_wars(scanner, conn):
    # Cached: an ended war with loot (scanned before war ids were queried, so no id).
    history = {"attid": "7", "defid": "300", "date": "2026-11-01T10:00:00+00:00",
               "turnsleft": 0, "winner": "300", "attacks": [{"type": "VICTORY", "money_looted": 5e6}]}
    assert _persist(scanner, conn, _scanned(wars=[history]), "scan")["success"]
    assert _stored(conn, 7)["def_slots"] == 0

    # The update lists only the new active defensive war (current field names).
    update = {"id": 7, "wars": [{"id": 9, "att_id": "400", "def_id": "7", "turns_left": 60,
                                 "date": "2026-11-14T08:00:00+00:00", "war_type": "RAID"}]}
    assert _persist(scanner, conn, update, "subscription")["success"]

    stored = _stored(conn, 7)
    wars = json.loads(stored["wars"])
    assert stored["def_slots"] == 1
    assert len(wars) == 2
    assert wars[0]["attacks"][0]["type"] == "VICTORY"  # history kept
    assert wars[1]["defid"] == "7" and wars[1]["turnsleft"] == 60  # scan names filled in


def test_update_for_a_cached_war_replaces_its_turns_left(scanner, conn):
    war = _war("5", "400", "7", "2026-11-12T10:00:00+00:00", 40,
               attacks=[{"id": "1", "type": "GROUND", "money_looted": 10.0}])
    assert _persist(scanner, conn, _scanned(wars=[war]), "scan")["success"]
    assert _stored(conn, 7)["def_slots"] == 1

    ended = {"id": 5, "att_id": 400, "def_id": 7, "date": "2026-11-12T10:00:00+00:00",
             "turns_left": 0, "attacks": [{"id": 2, "type": "VICTORY", "money_looted": None}]}
    assert _persist(scanner, conn, {"id": 7, "wars": [ended]}, "subscription")["success"]

    stored = _stored(conn, 7)
    [merged] = json.loads(stored["wars"])
    assert stored["def_slots"] == 0
    assert merged["turnsleft"] == 0
    assert [a["type"] for a in merged["attacks"]] == ["GROUND", "VICTORY"]


def test_war_policy_from_an_update_reaches_the_scan_column(scanner, conn):
    assert _persist(scanner, conn, _scanned(warpolicy="Turtle"), "scan")["success"]
    assert _persist(scanner, conn, {"id": 7, "war_policy": "ATTRITION"}, "subscription")["success"]
    stored = _stored(conn, 7)
    assert (stored["warpolicy"], stored["war_policy"]) == ("Attrition", "ATTRITION")


def test_income_is_computed_on_copies_of_the_cities(scanner, conn, monkeypatch):
    seen = []

    def fake_revenue(nation, **kwargs):
        nation["cities"][0]["pollution"] = 99
        seen.append(nation)
        return {"monetary_net_num": 1234.4, "net_cash_num": 1000}

    monkeypatch.setattr(scanner, "revenue_calc_sync", fake_revenue)
    context = (PRICES, ({}, PRICES, [], {}, {}))
    result = asyncio.run(scanner.persist_nation_row(
        conn, _scanned(), source="scan", prices=context[0], revenue_context=context[1]
    ))
    assert result["income_computed"]
    stored = _stored(conn, 7)
    assert stored["monetary_net_num"] == 1234
    assert "pollution" not in json.loads(stored["cities"])[0]


def test_failed_write_is_rolled_back(scanner, conn, monkeypatch):
    def broken_upsert(connection, table, row):
        connection.execute("INSERT INTO nations (id) VALUES (8)")
        raise sqlite3.OperationalError("disk I/O error")

    _persist(scanner, conn, _scanned(), "scan")
    monkeypatch.setattr(scanner, "upsert", broken_upsert)
    result = _persist(scanner, conn, _scanned(nation_id=8), "scan")

    assert result["success"] is False
    assert not conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM nations WHERE id = 8").fetchone()[0] == 0


def test_metadata_write_failure_does_not_raise(scanner, tmp_path):
    connection = sqlite3.connect(tmp_path / "meta.db")
    connection.close()  # every statement now fails
    scanner._record_metadata(connection, "last_subscription_event_ts")


def test_failed_context_fetch_is_retried_not_cached(scanner, monkeypatch):
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise PnWServerError("down")
        return PRICES, ({}, PRICES, [], {}, {})

    monkeypatch.setattr(scanner, "_fetch_persist_context", flaky)
    monkeypatch.setattr(scanner, "_subscription_persist_context", None)
    monkeypatch.setattr(scanner, "_subscription_persist_context_at", float("-inf"))
    monkeypatch.setattr(scanner, "_subscription_persist_context_failed_at", float("-inf"))
    monkeypatch.setattr(scanner, "_subscription_persist_context_refresh", None)

    async def scenario():
        first = await scanner._get_subscription_persist_context()
        # Within the retry delay nothing is fetched again.
        again = await scanner._get_subscription_persist_context()
        scanner._subscription_persist_context_failed_at = (
            time.monotonic() - scanner.SUBSCRIPTION_PERSIST_CONTEXT_RETRY_SECONDS
        )
        await scanner._get_subscription_persist_context()  # starts a background refresh
        await scanner._subscription_persist_context_refresh
        return first, again, await scanner._get_subscription_persist_context()

    first, again, later = asyncio.run(scenario())
    assert first == again == (None, None)
    assert later[0] == PRICES
    assert len(calls) == 2


def test_server_errors_are_retried(scanner, monkeypatch):
    replies = [PnWServerError("502"), {"data": {"ok": True}}]

    async def fake_call(query):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(scanner, "call_api", fake_call)
    monkeypatch.setattr(scanner.asyncio, "sleep", no_sleep)
    assert asyncio.run(scanner._fetch_with_retry("{q}", scan_type="nation", page=1)) == {"data": {"ok": True}}


def test_prune_keeps_rows_written_during_the_scan(tmp_path):
    with contextlib.closing(sqlite3.connect(tmp_path / "prune.db")) as connection:
        for nation_id, written in ((1, 100), (2, 100), (3, 500)):
            row = {"id": nation_id, "_created_at": written}
            ensure_table_and_columns(connection, "nations", row)
            upsert(connection, "nations", row)
        # The scan started at 400 and saw only nation 1; 3 was refreshed meanwhile.
        prune_missing_ids(connection, "nations", [1], written_before=400)
        remaining = [r[0] for r in connection.execute("SELECT id FROM nations ORDER BY id")]
    assert remaining == [1, 3]


def test_reconnect_backoff(scanner):
    assert scanner._subscription_backoff_seconds(1, 4200) == 2
    assert scanner._subscription_backoff_seconds(4, None) == 16
    assert scanner._subscription_backoff_seconds(1, 4001) == scanner.SUBSCRIPTION_BOOTSTRAP_BACKOFF_MAX_SECONDS
