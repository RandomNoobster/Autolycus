"""Tests for raids-table helpers and shared date/treasure helpers they rely on."""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import aiohttp
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from infra.pnw_subscriptions import PnwSubscription, SubscriptionError
from logic.common import parse_war_date
from logic.raids import (calculate_days_inactive, derive_def_slots_and_time_since_war,
                         stored_time_since_war)
from logic.revenue import calculate_treasure_bonus

UTC = timezone.utc
NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


def test_offsetless_iso_dates_are_utc():
    # What coerce_payload makes of "2026-11-01 10:20:30".
    assert calculate_days_inactive("2026-11-01T10:20:30", NOW) == 13
    assert parse_war_date("2026-11-10T10:00:00") == datetime(2026, 11, 10, 10, tzinfo=UTC)


def test_timestamps_slightly_ahead_of_the_clock_are_not_negative():
    ahead = (NOW + timedelta(seconds=3)).isoformat()
    assert calculate_days_inactive(ahead, NOW) == 0
    nation = {"id": 7, "wars": [{"attid": "7", "defid": "8", "turnsleft": 0, "date": ahead}]}
    assert derive_def_slots_and_time_since_war(nation, NOW) == (0, 0)


def test_def_slots_read_current_names_and_skip_bad_wars():
    nation = {
        "id": 7,
        "wars": [
            {"def_id": "7", "turns_left": 10, "date": "2026-11-13T10:00:00+00:00"},
            {"defid": "7", "turnsleft": None, "date": "2026-11-12T10:00:00+00:00"},
            "not a war",
        ],
    }
    assert derive_def_slots_and_time_since_war(nation, NOW) == (1, 0)


@pytest.mark.parametrize(("stored", "shown"), [(None, "14+"), ("3", 3), (4, 4), ("14+", "14+")])
def test_stored_time_since_war(stored, shown):
    assert stored_time_since_war(stored) == shown


def test_treasure_bonus_matches_int_ids_from_live_updates():
    treasures = [
        {"bonus": 10, "nation": {"id": "112233", "alliance_id": "42"}},
        {"bonus": 5, "nation": {"id": "998877", "alliance_id": "42"}},
    ]
    scanned = {"id": "112233", "alliance_id": "42", "alliance": {"id": "42"}}
    live = {"id": 112233, "alliance_id": 42, "alliance": {"id": "42"}}
    assert calculate_treasure_bonus(live, treasures) == pytest.approx(
        calculate_treasure_bonus(scanned, treasures)
    )
    assert calculate_treasure_bonus(live, treasures) > 1.1


def test_subscribe_errors_do_not_repeat_the_api_key():
    class FailingSession:
        def get(self, url, params=None, timeout=None):
            raise aiohttp.ClientResponseError(
                aiohttp.RequestInfo(
                    url=aiohttp.client.URL(f"{url}?api_key={params['api_key']}"),
                    method="GET",
                    headers={},
                    real_url=aiohttp.client.URL(f"{url}?api_key={params['api_key']}"),
                ),
                (),
                status=400,
                message="Invalid header value char",
            )

    subscription = PnwSubscription("SECRET-KEY", "nation", "update", session=FailingSession())
    with pytest.raises(SubscriptionError) as failed:
        asyncio.run(subscription._request_channel())
    assert "SECRET-KEY" not in str(failed.value)
    assert failed.value.__cause__ is None and failed.value.__suppress_context__
