"""End-to-end: the scanner's subscription worker persists recorded nation updates."""

import asyncio
import contextlib
import importlib
import json
import logging
import os
import sqlite3
import sys
from functools import partial
from pathlib import Path

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from infra.pnw_subscriptions import PnwSubscription
from tests.pnw_fake_pusher import FIXTURE, FakePusher, wait_for

PRICES = {
    "money": 1, "coal": 4000.0, "oil": 3500.0, "uranium": 3000.0, "iron": 4000.0,
    "bauxite": 4000.0, "lead": 4000.0, "gasoline": 3800.0, "munitions": 2000.0,
    "steel": 4300.0, "aluminum": 2600.0, "food": 140.0,
}
# Derived from the wall clock when the row is written.
_TIME_DEPENDENT_COLUMNS = {"_created_at", "time_since_war"}


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


def _nation_rows(path: Path) -> dict[int, dict]:
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute("SELECT * FROM nations")]
    return {
        row["id"]: {k: v for k, v in row.items() if k not in _TIME_DEPENDENT_COLUMNS}
        for row in rows
    }


def _has_metadata(path: Path, key: str) -> bool:
    if not path.exists():
        return False
    with contextlib.closing(sqlite3.connect(path)) as conn:
        try:
            found = conn.execute("SELECT 1 FROM metadata WHERE key = ?", (key,)).fetchone()
            return found is not None
        except sqlite3.OperationalError:
            return False


def test_worker_persists_recorded_updates_as_pnwkit_rows_were(scanner, monkeypatch, tmp_path):
    db_path = tmp_path / "nations.db"
    expected_path = tmp_path / "expected.db"
    monkeypatch.setattr(scanner, "get_nations_db_path", lambda: db_path)

    async def persist_context():
        return dict(PRICES), None

    monkeypatch.setattr(scanner, "_get_subscription_persist_context", persist_context)

    async def scenario():
        async with FakePusher() as server:
            local = partial(PnwSubscription, **server.urls())
            monkeypatch.setattr(scanner, "PnwSubscription", local)
            worker = asyncio.create_task(scanner.nation_subscription_worker())
            try:
                # The worker records the stream ending (close code 4200) before backing off.
                await wait_for(lambda: _has_metadata(db_path, "last_subscription_error_ts"))
            finally:
                worker.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker
        # What the worker stored when pnwkit produced these rows.
        with contextlib.closing(sqlite3.connect(expected_path)) as conn:
            for row in FIXTURE["expected_rows"]:
                result = await scanner.persist_nation_row(
                    conn, row, source="subscription", prices=dict(PRICES)
                )
                assert result["success"]
        return server

    server = asyncio.run(scenario())

    stored = _nation_rows(db_path)
    assert sorted(stored) == [112233, 246810, 998877]
    assert stored == _nation_rows(expected_path)
    assert server.sockets_opened == 1
    assert _has_metadata(db_path, "last_subscription_reconnect_ts")
    assert _has_metadata(db_path, "last_subscription_event_ts")

    raider = stored[246810]
    assert "__dict__" not in raider
    assert raider["nation_loot_value"] > 0
    assert json.loads(raider["wars"])[0]["attacks"][1]["type"] == "VICTORY"
    # Empty or null wars in an update must not clear wars (none were cached here).
    assert stored[112233]["wars"] is None and stored[998877]["wars"] is None
