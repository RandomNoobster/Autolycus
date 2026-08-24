"""Optional live Politics & War API check for beige loot fields.

Run with:
  API_KEY=... PYTHONPATH=. python3 -m pytest tests/test_beige_loot_live.py -q
"""

from __future__ import annotations

import os

import pytest
import requests

from logic.common import compute_beige_loot


# Recently beiged nation with many defensive defeats (see politicsandwar.com/nation/id=55556).
LIVE_NATION_ID = 55556


def _graphql(api_key: str, query: str) -> dict:
    url = f"https://api.politicsandwar.com/graphql?api_key={api_key}"
    response = requests.post(url, json={"query": query}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise AssertionError(payload["errors"])
    return payload


def test_live_nation_has_structured_victory_loot():
    api_key = (os.getenv("API_KEY") or "").strip()
    if not api_key:
        pytest.skip("API_KEY not set")

    query = (
        "{"
        f"nations(id:{LIVE_NATION_ID},first:1)"
        "{data{id nation_name beige_turns color "
        "wars{"
        "date war_type defid turnsleft "
        "attacker{war_policy advanced_pirate_economy} "
        "attacks{"
        "type loot_info victor moneystolen money_looted "
        "coal_looted oil_looted uranium_looted iron_looted bauxite_looted "
        "lead_looted gasoline_looted munitions_looted steel_looted "
        "aluminum_looted food_looted"
        "}}}}}"
        "}"
    )
    prices_query = (
        "{tradeprices(first:1){data{coal oil uranium iron bauxite lead "
        "gasoline munitions steel aluminum food}}}"
    )

    nation_resp = _graphql(api_key, query)
    prices_resp = _graphql(api_key, prices_query)

    nations = nation_resp["data"]["nations"]["data"]
    assert nations, f"nation {LIVE_NATION_ID} not returned"
    nation = nations[0]

    prices = prices_resp["data"]["tradeprices"]["data"][0]
    prices["money"] = 1

    empty_loot_info = 0
    structured_victory = 0
    for war in nation.get("wars") or []:
        if str(war.get("defid")) != str(nation["id"]):
            continue
        for attack in war.get("attacks") or []:
            if (attack.get("type") or "").upper() != "VICTORY":
                continue
            if not attack.get("loot_info"):
                empty_loot_info += 1
            if attack.get("money_looted") is not None or attack.get("food_looted") is not None:
                structured_victory += 1

    assert structured_victory > 0, (
        f"expected VICTORY attacks with *_looted fields on nation {LIVE_NATION_ID}"
    )
    # Document the production bug: loot_info is commonly empty while structured fields exist.
    assert empty_loot_info > 0 or compute_beige_loot(nation, prices) not in (None, 0)

    loot = compute_beige_loot(nation, prices)
    assert loot is not None and loot > 0, (
        f"expected non-zero beige loot for nation {LIVE_NATION_ID}, got {loot!r}"
    )
