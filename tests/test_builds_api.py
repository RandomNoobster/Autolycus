"""Tests for calculate_builds ranking/prices and the /api/builds error mapping."""
import asyncio
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api.routes.builds as builds_routes
import logic.builds as builds_logic
from database.sqlite_cache import IMPROVEMENT_FIELDS, get_builds_db_path

PRICES = {
    "money": 1, "coal": 100, "oil": 100, "uranium": 2000, "iron": 100, "bauxite": 100, "lead": 100,
    "gasoline": 3000, "munitions": 2000, "steel": 3500, "aluminum": 2500, "food": 150, "credits": 0,
}

needs_db = pytest.mark.skipif(not get_builds_db_path().exists(), reason="data/city_builds.db not present")


@pytest.fixture
def game_context(monkeypatch):
    """Fake the cached game context and the 30-day price history."""
    history = {"prices": {resource: value * 2 for resource, value in PRICES.items()}}

    async def fake_pre_revenue_calc(message, *, query_for_nation, parsed_nation, call_func, get_query_func, queries_module):
        colors = {"beige": 0}
        radiation = {code: 0.0 for code in ("na", "sa", "eu", "af", "as", "au", "an")}
        seasonal = {code: 1.0 for code in radiation}
        return parsed_nation, colors, dict(PRICES), [], radiation, seasonal

    async def fake_history(call_pnw):
        return history["prices"]

    monkeypatch.setattr(builds_logic, "pre_revenue_calc", fake_pre_revenue_calc)
    monkeypatch.setattr(builds_logic, "_fetch_historical_prices", fake_history)
    return history


async def _no_api(_query):
    raise AssertionError("manual configuration should not call the API")


def _builds(**kwargs):
    params = {"call_pnw": _no_api, "infra": 1500, "land": 2000, "mmr": "5/5/5/3", "continent_override": "na"}
    params.update(kwargs)
    return asyncio.run(builds_logic.calculate_builds(**params))


def test_rank_builds_breaks_resource_ties_by_net_income():
    cities = [
        {"id": "a", "net income": 10, "steel": 5},
        {"id": "b", "net income": 30, "steel": 5},
        {"id": "c", "net income": 20, "steel": 1},
    ]

    ranked, best = builds_logic._rank_builds_sync(cities, ["steel", "net income"])

    assert [city["id"] for city in ranked] == ["b", "c", "a"]
    assert best["steel"]["id"] == "b"
    assert best["net income"]["id"] == "b"


@needs_db
def test_average_prices_are_reported_only_when_used(game_context):
    assert _builds(use_live_prices=False)["prices"]["mode"] == "average"

    game_context["prices"] = None  # the 30-day fetch failed
    assert _builds(use_live_prices=False)["prices"]["mode"] == "live"


@needs_db
def test_unit_upkeep_is_charged_once_and_only_when_requested(game_context):
    without = _builds(include_military_upkeep=False)
    with_upkeep = _builds(include_military_upkeep=True)

    def layout(build):
        return tuple(build[field] for field in IMPROVEMENT_FIELDS)

    build = without["uniqueBuilds"][0]
    same = next(b for b in with_upkeep["uniqueBuilds"] if layout(b) == layout(build))
    upkeep = build["unit_upkeep"]["total"]
    assert upkeep > 0
    for key in ("net income", "net_cash_num", "money"):
        assert build[key] - same[key] == pytest.approx(upkeep, abs=1), key


@needs_db
def test_nation_average_infra_is_floored_to_a_full_chunk(game_context):
    nation = {
        "id": "7", "nation_name": "Seven", "leader_name": "L", "continent": "na", "color": "beige",
        "num_cities": 2, "dompolicy": "", "alliance_id": "0", "alliance": None, "date": "2020-01-01",
        "cities": [{"infrastructure": 1030.0, "land": 2000.0}, {"infrastructure": 1030.0, "land": 2000.0}],
    }

    async def fetch_nation(_query):
        return {"data": {"nations": {"data": [nation]}}}

    result = _builds(call_pnw=fetch_nation, nation_id="7", infra=None, land=None)

    assert result["infrastructure"] == 1000


def test_unknown_nation_raises_not_found():
    async def no_nations(_query):
        return {"data": {"nations": {"data": []}}}

    with pytest.raises(builds_logic.NationNotFoundError):
        _builds(call_pnw=no_nations, nation_id="999")


def test_bad_mmr_is_an_input_error():
    with pytest.raises(builds_logic.BuildInputError):
        builds_logic.parse_mmr("abc")


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(builds_routes.builds_bp)
    return app.test_client()


@pytest.mark.parametrize("query", ["infra=1500&land=0", "infra=1500&land=-5", "infra=10&land=2000", "infra=abc&land=2000"])
def test_invalid_infra_or_land_returns_400(client, monkeypatch, query):
    monkeypatch.setattr(builds_routes, "run_sync", lambda *a, **k: pytest.fail("should not calculate"))

    response = client.get(f"/api/builds/?{query}")

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_PARAMETER"


def _raise_from_run_sync(monkeypatch, exc):
    def fake_run_sync(coro, timeout=None):
        coro.close()
        raise exc

    monkeypatch.setattr(builds_routes, "run_sync", fake_run_sync)


@pytest.mark.parametrize(
    "exc,status,code",
    [
        (builds_logic.BuildInputError("Invalid MMR format: x"), 400, "INVALID_PARAMETER"),
        (builds_logic.NationNotFoundError("Nation 9 not found in API"), 404, "NATION_NOT_FOUND"),
        (TimeoutError(), 504, "UPSTREAM_TIMEOUT"),
        (RuntimeError("boom"), 500, "INTERNAL_ERROR"),
    ],
)
def test_calculation_errors_map_to_status_codes(client, monkeypatch, exc, status, code):
    _raise_from_run_sync(monkeypatch, exc)

    response = client.get("/api/builds/?infra=1500&land=2000&mmr=x")

    assert response.status_code == status
    assert response.get_json()["code"] == code


def test_revenue_project_fields_match_the_api_project_list():
    from api.constants import PROJECT_FIELD_NAMES

    assert set(builds_logic.REVENUE_PROJECT_FIELDS) == set(PROJECT_FIELD_NAMES)


def test_build_template_is_the_bulk_import_json():
    import json

    build = {field: 1 for field in IMPROVEMENT_FIELDS}
    build["infrastructure"] = 1525

    template = json.loads(builds_logic.generate_build_template(build))

    assert template["infra_needed"] == 1525
    assert template["imp_total"] == 30
    assert template["imp_hangars"] == 1
    assert len(template) == 29


def test_continent_names_are_accepted(client, monkeypatch):
    seen = {}

    async def fake_calculate_builds(**kwargs):
        seen["continent"] = kwargs["continent_override"]
        raise builds_logic.BuildInputError("stop here")

    monkeypatch.setattr(builds_routes, "calculate_builds", fake_calculate_builds)
    monkeypatch.setattr(builds_routes, "run_sync", lambda coro, timeout=None: asyncio.run(coro))

    assert client.get("/api/builds/?infra=1500&land=2000&continent=North%20America").status_code == 400
    assert seen["continent"] == "na"
    response = client.get("/api/builds/?infra=1500&land=2000&continent=atlantis")
    assert response.status_code == 400
    assert "continent must be one of" in response.get_json()["message"]
