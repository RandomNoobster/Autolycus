"""Tests for cache key building: callables are ignored and secrets never reach keys."""

import asyncio
import copy
import os
import subprocess
import sys
import types
from functools import partial

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from aiocache import Cache

import infra.cache as cache_mod
from infra.cache import build_key_from_all_args, build_key_ignoring_callables

SECRET = "SECRET123"

_GAME_CONTEXT_RESPONSE = {
    "data": {
        "colors": [{"color": "aqua", "turn_bonus": 10}],
        "game_info": {
            "game_date": "2024-07-01",
            "radiation": {
                "global": 10,
                "north_america": 1,
                "south_america": 2,
                "africa": 3,
                "europe": 4,
                "asia": 5,
                "australia": 6,
                "antarctica": 7,
            },
        },
        "tradeprices": {"data": [{"coal": 100.0, "steel": 3000.0}]},
        "treasures": [],
    }
}


async def fake_call(query: str, api_key: str | None = None) -> dict:
    return {"query": query, "api_key": api_key}


async def cached_target(*args, **kwargs):
    """Stand-in for a decorated function; only its identity matters for keys."""
    return None


class Client:
    async def call(self, query: str) -> dict:
        return {}


def test_key_contains_module_and_function_name():
    key = build_key_ignoring_callables(cached_target, "coal", days=30)
    assert cached_target.__module__ in key
    assert cached_target.__name__ in key


@pytest.mark.parametrize("builder", [build_key_ignoring_callables, build_key_from_all_args])
def test_different_callables_share_one_key(builder):
    keys = {
        builder(cached_target, lambda q: q, lambda q: q, types),
        builder(cached_target, lambda q: fake_call(q, api_key="A"), str.upper, os),
        builder(cached_target, partial(fake_call, api_key="A"), fake_call, sys),
        builder(cached_target, partial(fake_call, api_key="B"), Client().call, Client),
        builder(cached_target, call_func=lambda q: q, queries_module=types),
        builder(cached_target),
    }
    assert len(keys) == 1


def test_secret_never_appears_in_key():
    partial_key = build_key_ignoring_callables(cached_target, partial(fake_call, api_key=SECRET), types)
    assert SECRET not in partial_key
    raw_key = build_key_ignoring_callables(cached_target, SECRET, api_key=SECRET, nested={"key": [SECRET]})
    assert SECRET not in raw_key


def test_meaningful_args_give_different_keys():
    call = partial(fake_call, api_key=SECRET)
    base = build_key_ignoring_callables(cached_target, call, resource="coal", days=30)
    assert build_key_ignoring_callables(cached_target, call, resource="coal", days=7) != base
    assert build_key_ignoring_callables(cached_target, call, resource="steel", days=30) != base
    assert build_key_ignoring_callables(cached_target, "coal", 30) != build_key_ignoring_callables(cached_target, "coal", 7)
    assert build_key_ignoring_callables(cached_target, 1) != build_key_ignoring_callables(cached_target, "1")
    assert build_key_ignoring_callables(cached_target, 1) != build_key_ignoring_callables(cached_target, True)
    assert build_key_ignoring_callables(cached_target, [1, 2]) != build_key_ignoring_callables(cached_target, (1, 2))


def test_function_identity_is_part_of_key():
    async def other_target(*args, **kwargs):
        return None

    assert build_key_ignoring_callables(cached_target, "coal") != build_key_ignoring_callables(other_target, "coal")


def test_equal_values_give_equal_keys():
    assert build_key_ignoring_callables(cached_target, {"a": 1, "b": 2}) == build_key_ignoring_callables(
        cached_target, {"b": 2, "a": 1}
    )
    assert build_key_ignoring_callables(cached_target, a=1, b=2) == build_key_ignoring_callables(cached_target, b=2, a=1)
    assert build_key_ignoring_callables(cached_target, {"coal", "steel"}) == build_key_ignoring_callables(
        cached_target, frozenset({"steel", "coal"})
    )


def test_key_is_stable_across_processes():
    """Redis is shared by several processes, so keys must not depend on hash randomization."""
    script = (
        "from infra.cache import build_key_ignoring_callables\n"
        "def target(): pass\n"
        "print(build_key_ignoring_callables(target, {'coal', 'steel', 'food', 'oil'}, {'b': 2, 'a': 1}, days=30))\n"
    )
    keys = set()
    for seed in ("0", "1", "2"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        keys.add(result.stdout.strip().splitlines()[-1])
    assert len(keys) == 1


@pytest.mark.parametrize(
    "factory",
    [
        cache_mod.cache_prices,
        cache_mod.cache_game_context,
        cache_mod.cache_historical_prices,
        cache_mod.cache_builds,
        cache_mod.cache_revenue_context,
    ],
)
def test_cache_factories_use_callable_ignoring_key_builder(factory):
    assert factory(ttl=60).key_builder is build_key_ignoring_callables


def test_game_context_served_from_cache_for_fresh_callables(monkeypatch):
    """A new lambda/partial per call must not trigger another P&W API request."""
    monkeypatch.setattr(cache_mod, "CACHE_BACKEND", Cache.MEMORY)
    monkeypatch.setattr(cache_mod, "REDIS_CONFIG", {})
    from logic import revenue

    api_keys_used: list[str | None] = []

    async def counting_call(query: str, api_key: str | None = None) -> dict:
        api_keys_used.append(api_key)
        return copy.deepcopy(_GAME_CONTEXT_RESPONSE)

    fake_queries = types.ModuleType("fake_queries")
    fake_queries.PRICES = "prices"
    get_game_context = cache_mod.cache_game_context(ttl=60)(revenue.get_cached_game_context.__wrapped__)

    async def run():
        await get_game_context.cache.clear()
        first = await get_game_context(partial(counting_call, api_key=SECRET), lambda _: "{coal}", fake_queries)
        second = await get_game_context(lambda q: counting_call(q, api_key="OTHER"), lambda _: "{coal}", fake_queries)
        return first, second

    first, second = asyncio.run(run())
    assert api_keys_used == [SECRET]
    assert first == second
