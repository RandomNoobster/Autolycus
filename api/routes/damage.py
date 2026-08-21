"""
Damage API Routes

This module provides API endpoints for the damage calculator feature,
returning detailed attack damage analysis for war planning.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from api.security import optional_discord_session
from database.mongo import get_sync_db
from logic import queries
from api.calculations.damage_calc import calculate_damage
from database.sqlite_cache import get_all_nations
from logic.api_client import call as call_api
from logic.damage import calculate_damage as calculate_damage_logic
from logic.merge_utils import get_query

logger = logging.getLogger(__name__)

damage_bp = Blueprint('damage', __name__, url_prefix='/api/damage')

_API_KEY = os.getenv("API_KEY")
_BOT_KEY = os.getenv("BOT_KEY")

# Attack types configuration
ATTACK_TYPES = [
    {'type': 'ground', 'maps': 3, 'label': 'Ground'},
    {'type': 'airvair', 'maps': 4, 'label': 'Air vs Air'},
    {'type': 'airvinfra', 'maps': 4, 'label': 'Air vs Infra'},
    {'type': 'airvsoldiers', 'maps': 4, 'label': 'Air vs Soldiers'},
    {'type': 'airvtanks', 'maps': 4, 'label': 'Air vs Tanks'},
    {'type': 'airvships', 'maps': 4, 'label': 'Air vs Ships'},
    {'type': 'navalvinfra', 'maps': 4, 'label': 'Naval vs Other'},
    {'type': 'navalvships', 'maps': 4, 'label': 'Naval vs Naval'},
    {'type': 'nuke', 'maps': 12, 'label': 'Nuke'},
    {'type': 'missile', 'maps': 8, 'label': 'Missile'},
]


async def _call_pnw(query: str, *, use_bot_key: bool = False) -> dict[str, Any]:
    """Call the Politics & War API with shared credentials."""
    if not _API_KEY:
        raise RuntimeError("api_key environment variable must be set for damage routes")
    return await call_api(query, api_key=_API_KEY, use_bot_key=use_bot_key, bot_key=_BOT_KEY)


async def _fetch_battle_nations(nation_ids: list[int]) -> dict[int, dict[str, Any]]:
    unique_ids = sorted({int(nid) for nid in nation_ids if nid})
    if not unique_ids:
        return {}

    query = (
        "{"
        f"nations(id:[{','.join(map(str, unique_ids))}])"
        "{data"
        f"{get_query(queries.BATTLE_CALC)}"
        "}}"
    )

    response = await _call_pnw(query)
    nation_list = response.get("data", {}).get("nations", {}).get("data", [])
    return {int(nation["id"]): nation for nation in nation_list}


@damage_bp.route('/', methods=['GET'])
def get_damage() -> tuple[Any, int]:
    """
    Get damage calculator results (public endpoint).
    
    Query parameters:
        - nation1: First nation ID
        - nation2: Second nation ID
    
    Returns:
        JSON response with:
        - nation1: First nation's data and name
        - nation2: Second nation's data and name
        - attacks: Detailed attack damage breakdown for each nation
        - chartData: Pre-formatted data for visualization charts
        - generatedAt: ISO timestamp of data generation
    """
    try:
        # Read nation1 and nation2 from query parameters
        nation1_id = request.args.get('nation1')
        nation2_id = request.args.get('nation2')

        if not nation1_id or not nation2_id:
            return jsonify({
                'error': 'Missing parameter',
                'message': 'Both nation1 and nation2 are required',
                'code': 'MISSING_NATIONS'
            }), 400

        # Convert to integers
        try:
            nation1_id = int(nation1_id)
            nation2_id = int(nation2_id)
        except ValueError:
            return jsonify({
                'error': 'Invalid parameter',
                'message': 'nation1 and nation2 must be integers',
                'code': 'INVALID_PARAMETER'
            }), 400

        # Run async calculation in event loop
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(
                calculate_damage(str(nation1_id), str(nation2_id))
            )
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        chart_data = _generate_chart_data(results)
        inputs = _build_prefill_inputs(results, nation1_id, nation2_id)

        return jsonify(
            _build_damage_response(
                results,
                inputs=inputs,
                chart_data=chart_data,
            )
        ), 200

    except Exception as e:
        logger.error(f"Error in get_damage: {e}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred.',
            'code': 'INTERNAL_ERROR'
        }), 500


@damage_bp.route('/calculate', methods=['POST'])
def calculate_damage_custom() -> tuple[Any, int]:
    """Calculate damage using custom inputs (public endpoint)."""
    try:
        payload = request.get_json(silent=True) or {}
        nation1_id = _parse_int(payload.get("nation1Id"))
        nation2_id = _parse_int(payload.get("nation2Id"))

        if not nation1_id or not nation2_id:
            return jsonify({
                'error': 'Missing parameter',
                'message': 'nation1Id and nation2Id are required',
                'code': 'MISSING_NATIONS'
            }), 400

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            nation_map = loop.run_until_complete(_fetch_battle_nations([nation1_id, nation2_id]))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        if nation1_id not in nation_map or nation2_id not in nation_map:
            return jsonify({
                'error': 'Nation not found',
                'message': 'One or both nations could not be loaded',
                'code': 'NATION_NOT_FOUND'
            }), 404

        nation1 = nation_map[nation1_id]
        nation2 = nation_map[nation2_id]

        _apply_nation_overrides(nation1, payload.get("nation1", {}))
        _apply_nation_overrides(nation2, payload.get("nation2", {}))
        _apply_war_override(nation1, nation1_id, nation2_id, payload.get("war", {}))

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(
                calculate_damage_logic(
                    call_pnw=_call_pnw,
                    nation1=nation1,
                    nation2=nation2,
                )
            )
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        chart_data = _generate_chart_data(results)
        inputs = _build_prefill_inputs(results, nation1_id, nation2_id)

        return jsonify(
            _build_damage_response(
                results,
                inputs=inputs,
                chart_data=chart_data,
            )
        ), 200

    except Exception as e:
        logger.error(f"Error in calculate_damage_custom: {e}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred.',
            'code': 'INTERNAL_ERROR'
        }), 500


@damage_bp.route('/linked-active-wars', methods=['GET'])
@optional_discord_session
def get_linked_active_wars() -> tuple[Any, int]:
    """Active wars for the Discord-linked nation (live PnW), for damage presets."""
    user_id = getattr(request, "session_user_id", None)
    if user_id is None:
        return jsonify({
            "linked": False,
            "nation_id": None,
            "wars": [],
        }), 200

    mongo_db = get_sync_db()
    if mongo_db is None:
        return jsonify({
            "error": "Database unavailable",
            "message": "MongoDB is not configured.",
            "code": "DB_UNAVAILABLE",
        }), 503

    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return jsonify({
            "error": "Invalid user id",
            "message": "user_id must be numeric.",
            "code": "INVALID_USER",
        }), 400

    profile = mongo_db.global_users.find_one({"user": uid}) or {}
    raw_nid = profile.get("id")
    nation_id_text = str(raw_nid).strip() if raw_nid is not None else ""
    if not nation_id_text:
        return jsonify({
            "linked": False,
            "nation_id": None,
            "wars": [],
        }), 200

    try:
        linked_id = int(nation_id_text)
    except ValueError:
        return jsonify({
            "linked": False,
            "nation_id": None,
            "wars": [],
        }), 200

    if not _API_KEY:
        return jsonify({
            "error": "Configuration error",
            "message": "API_KEY is not set.",
            "code": "CONFIG_ERROR",
        }), 503

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        raw_wars = loop.run_until_complete(
            _fetch_linked_nation_active_wars_raw(linked_id)
        )
    except RuntimeError as exc:
        logger.error("linked-active-wars PnW failure: %s", exc, exc_info=True)
        return jsonify({
            "error": "Upstream API error",
            "message": "Could not load active wars from Politics & War.",
            "code": "LINKED_WARS_FETCH_FAILED",
        }), 502
    except Exception as exc:
        logger.error("linked-active-wars unexpected: %s", exc, exc_info=True)
        return jsonify({
            "error": "Internal server error",
            "message": "An unexpected error occurred while loading active wars.",
            "code": "INTERNAL_ERROR",
        }), 500
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    seen: set = set()
    wars_out: list[dict[str, Any]] = []
    for war in raw_wars:
        if not isinstance(war, dict):
            continue
        item = _build_linked_war_preset_item(war, linked_id)
        if not item:
            continue
        key = (item["attacker_id"], item["defender_id"])
        if key in seen:
            continue
        seen.add(key)
        wars_out.append(item)

    return jsonify({
        "linked": True,
        "nation_id": nation_id_text,
        "wars": wars_out,
    }), 200


@damage_bp.route('/nations/search', methods=['GET'])
def search_nations() -> tuple[Any, int]:
    """
    Search for nations by name, leader, or ID (fuzzy matching).

    Query Parameters:
        - q: Search query string (required)
        - limit: Maximum results to return (default: 10)

    Returns:
        JSON response with matching nations.
    """
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify([]), 200

        limit = int(request.args.get('limit', 10))
        limit = min(limit, 50)

        data_path = Path(current_app.root_path).parent / 'data' / 'nations.db'
        if not data_path.exists():
            logger.warning("[nations/search] nations.db not found")
            return jsonify([]), 200

        nations_data = get_all_nations(data_path)
        nations = nations_data.get('nations', [])
        if not nations:
            logger.info("[nations/search] nations.db loaded but empty")
            return jsonify([]), 200

        query_lower = query.lower()
        results = []
        for nation in nations:
            nation_id = str(nation.get('id', ''))
            nation_name = str(nation.get('nation_name') or nation.get('nationName') or '')
            leader_name = str(nation.get('leader_name') or nation.get('leaderName') or '')

            if not nation_name and not leader_name:
                continue

            name_lower = nation_name.lower()
            leader_lower = leader_name.lower()

            score = 0
            if query_lower == name_lower or query_lower == leader_lower or query == nation_id:
                score = 1000
            elif name_lower.startswith(query_lower) or leader_lower.startswith(query_lower):
                score = 100
            elif query_lower in name_lower or query_lower in leader_lower:
                score = 50
            elif query in nation_id:
                score = 25
            else:
                continue

            label = f"{nation_name} — {leader_name} (ID {nation_id})" if leader_name else f"{nation_name} (ID {nation_id})"
            results.append({
                'value': nation_name,
                'label': label,
                'id': nation_id,
                'nationName': nation_name,
                'leaderName': leader_name,
                'score': score,
            })

        results.sort(key=lambda x: (-x['score'], x['nationName'].lower()))
        results = results[:limit]
        for result in results:
            del result['score']

        return jsonify(results), 200

    except Exception as exc:
        logger.error(f"Error searching nations: {exc}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'message': 'Failed to search nations.',
            'code': 'INTERNAL_ERROR'
        }), 500


def _extract_nation_data(results: dict[str, Any], nation_key: str) -> dict[str, Any]:
    """
    Extract nation-specific data from results.
    
    Args:
        results: Raw results dict from cache.
        nation_key: Either 'nation1' or 'nation2'.
    
    Returns:
        Formatted nation info object.
    """
    nation_info = results.get(nation_key, {})
    cities = nation_info.get('cities') or []
    
    raw_flag = nation_info.get("flag")
    if raw_flag is None or raw_flag == "":
        flag_url = None
    else:
        s = str(raw_flag).strip()
        flag_url = s or None

    return {
        'id': nation_info.get('id', 0),
        'nationName': nation_info.get('nation_name', 'Unknown'),
        'numCities': len(cities),
        'flagUrl': flag_url,
        'vds': nation_info.get('vds', False),  # Vital Defense System
        'irond': nation_info.get('irond', False),  # Iron Dome
        'groundWinRate': results.get(f'{nation_key}_ground_win_rate', 0.5),
        'airWinRate': results.get(f'{nation_key}_air_win_rate', 0.5),
        'navalWinRate': results.get(f'{nation_key}_naval_win_rate', 0.5),
    }


def _parse_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        parsed = int(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _war_turns_left(war: dict[str, Any]) -> int:
    for key in ("turns_left", "turnsleft"):
        raw = war.get(key)
        if raw is None:
            continue
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            continue
    return 0


def _war_att_def_ids(war: dict[str, Any]) -> tuple[int | None, int | None]:
    att = _parse_int(war.get("att_id") or war.get("attid"))
    deff = _parse_int(war.get("def_id") or war.get("defid"))
    return att, deff


def _control_nation_id(war: dict[str, Any]) -> int | None:
    for key in ("ground_control", "groundcontrol"):
        raw = war.get(key)
        if raw is None or raw == "":
            continue
        try:
            v = int(raw)
            return v if v > 0 else None
        except (TypeError, ValueError):
            continue
    return None


def _air_superiority_id(war: dict[str, Any]) -> int | None:
    for key in ("air_superiority", "airsuperiority"):
        raw = war.get(key)
        if raw is None or raw == "":
            continue
        try:
            v = int(raw)
            return v if v > 0 else None
        except (TypeError, ValueError):
            continue
    return None


def _naval_blockade_id(war: dict[str, Any]) -> int | None:
    for key in ("naval_blockade", "navalblockade"):
        raw = war.get(key)
        if raw is None or raw == "":
            continue
        try:
            v = int(raw)
            return v if v > 0 else None
        except (TypeError, ValueError):
            continue
    return None


def _war_bool(war: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        if key in war and war[key] is not None:
            return bool(war[key])
    return False


def _war_nonneg_int(war: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key in war and war[key] is not None:
            try:
                return max(0, int(war[key]))
            except (TypeError, ValueError):
                continue
    return 0


def _normalize_damage_war_type(raw: Any) -> str:
    s = str(raw or "ORDINARY").strip().upper()
    if s in ("RAID", "ORDINARY", "ATTRITION"):
        return s
    return "ORDINARY"


def _alliance_display(alliance: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not alliance:
        return None, None
    name = str(alliance.get("name") or "").strip()
    acronym = str(alliance.get("acronym") or "").strip()
    label = name or acronym or None
    flag = str(alliance.get("flag") or "").strip() or None
    return label, flag


def _nation_flag_name(
    nation: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    nid = _parse_int(nation.get("id"))
    nname = str(nation.get("nation_name") or nation.get("nationName") or "").strip()
    flag = str(nation.get("flag") or "").strip() or None
    return (str(nid) if nid else None), (nname or None), flag


def _opponent_nation_blob(
    war: dict[str, Any], linked_id: int
) -> dict[str, Any]:
    attacker = war.get("attacker") if isinstance(war.get("attacker"), dict) else {}
    defender = war.get("defender") if isinstance(war.get("defender"), dict) else {}
    att_id, def_id = _war_att_def_ids(war)
    if att_id == linked_id:
        return defender
    if def_id == linked_id:
        return attacker
    return {}


def _fortify_slots_from_att_def(
    nation1_id: int,
    nation2_id: int,
    attacker_id: int,
    att_fortify: bool,
    def_fortify: bool,
) -> tuple[bool, bool]:
    """Map game attacker/defender fortify flags to calculator nation1/nation2 slots."""
    if attacker_id == nation1_id:
        return bool(att_fortify), bool(def_fortify)
    if attacker_id == nation2_id:
        return bool(def_fortify), bool(att_fortify)
    return False, False


def _fortify_att_def_from_slots(
    nation1_id: int,
    nation2_id: int,
    attacker_id: int,
    nation1_fortified: bool,
    nation2_fortified: bool,
) -> tuple[bool, bool]:
    """Map calculator nation1/nation2 fortify toggles to game attacker/defender flags."""
    if attacker_id == nation1_id:
        return bool(nation1_fortified), bool(nation2_fortified)
    if attacker_id == nation2_id:
        return bool(nation2_fortified), bool(nation1_fortified)
    return False, False


def _build_linked_war_preset_item(war: dict[str, Any], linked_id: int) -> dict[str, Any] | None:
    att_id, def_id = _war_att_def_ids(war)
    if not att_id or not def_id:
        return None
    if linked_id not in (att_id, def_id):
        return None
    if _war_turns_left(war) <= 0:
        return None

    opp = _opponent_nation_blob(war, linked_id)
    opp_id = _parse_int(opp.get("id"))
    if not opp_id:
        opp_id = def_id if att_id == linked_id else att_id
    _, opp_name, opp_flag = _nation_flag_name(opp) if opp else (None, None, None)
    if not opp_name:
        opp_name = f"Nation {opp_id}"
    alliance = opp.get("alliance") if isinstance(opp.get("alliance"), dict) else None
    al_name, al_flag = _alliance_display(alliance)

    wtype = _normalize_damage_war_type(war.get("war_type") or war.get("warType"))
    gc = _control_nation_id(war)
    air = _air_superiority_id(war)
    naval = _naval_blockade_id(war)

    att_f = _war_bool(war, "att_fortify", "attFortify")
    def_f = _war_bool(war, "def_fortify", "defFortify")
    n1_fort, n2_fort = _fortify_slots_from_att_def(
        linked_id, opp_id, att_id, att_f, def_f
    )

    war_payload = {
        "attackerId": att_id,
        "defenderId": def_id,
        "warType": wtype,
        "groundControlId": gc,
        "airSuperiorityId": air,
        "navalBlockadeId": naval,
        "nation1Fortified": n1_fort,
        "nation2Fortified": n2_fort,
        "attackerPeace": _war_bool(war, "att_peace", "attpeace", "attPeace"),
        "defenderPeace": _war_bool(war, "def_peace", "defpeace", "defPeace"),
    }

    wid = war.get("id")
    try:
        war_id = int(wid) if wid is not None else None
    except (TypeError, ValueError):
        war_id = None

    att_res = _war_nonneg_int(war, "att_resistance", "attResistance")
    def_res = _war_nonneg_int(war, "def_resistance", "defResistance")
    att_pts = _war_nonneg_int(war, "att_points", "attpoints", "attPoints")
    def_pts = _war_nonneg_int(war, "def_points", "defpoints", "defPoints")

    linked_is_attacker = att_id == linked_id
    if linked_is_attacker:
        your_maps = att_pts
        enemy_resistance = def_res
        linked_stance = "offensive"
    else:
        your_maps = def_pts
        enemy_resistance = att_res
        linked_stance = "defensive"

    return {
        "war_id": war_id,
        "attacker_id": att_id,
        "defender_id": def_id,
        "opponent_id": opp_id,
        "opponent_name": opp_name,
        "opponent_flag_url": opp_flag,
        "opponent_alliance_name": al_name,
        "opponent_alliance_flag_url": al_flag,
        "linked_stance": linked_stance,
        "your_maps": your_maps,
        "enemy_resistance": enemy_resistance,
        "war": war_payload,
    }


async def _fetch_linked_nation_active_wars_raw(nation_id: int) -> list[dict[str, Any]]:
    query = f"""
{{
  nations(id: [{nation_id}]) {{
    data {{
      id
      wars(active: true, limit: 40) {{
        id
        war_type
        turns_left
        att_id
        def_id
        ground_control
        air_superiority
        naval_blockade
        att_peace
        def_peace
        att_fortify
        def_fortify
        att_resistance
        def_resistance
        att_points
        def_points
        attacker {{
          id
          nation_name
          flag
          alliance {{ name acronym flag }}
        }}
        defender {{
          id
          nation_name
          flag
          alliance {{ name acronym flag }}
        }}
      }}
    }}
  }}
}}
"""
    response = await _call_pnw(query)
    if response.get("errors"):
        err = response["errors"]
        logger.error("PnW linked-active-wars GraphQL errors: %s", err)
        raise RuntimeError("Politics & War API returned errors for active wars query")
    nations = (
        (response.get("data") or {}).get("nations") or {}
    ).get("data") or []
    if not nations:
        return []
    return nations[0].get("wars") or []


def _apply_nation_overrides(nation: dict[str, Any], overrides: dict[str, Any]) -> None:
    if not overrides:
        return

    for field in ["soldiers", "tanks", "aircraft", "ships", "missiles", "nukes"]:
        if field in overrides and overrides[field] is not None:
            nation[field] = max(int(overrides[field]), 0)

    if "warpolicy" in overrides and overrides["warpolicy"] is not None:
        nation["warpolicy"] = overrides["warpolicy"]

    for field, key in [
        ("vds", "vds"),
        ("irond", "irond"),
        ("falloutShelter", "fallout_shelter"),
        ("guidingSatellite", "guiding_satellite"),
        ("militarySalvage", "military_salvage"),
        ("advancedPirateEconomy", "advanced_pirate_economy"),
    ]:
        if field in overrides and overrides[field] is not None:
            nation[key] = bool(overrides[field])

    if "soldiersUseMunitions" in overrides and overrides["soldiersUseMunitions"] is not None:
        nation["soldiers_use_munitions"] = bool(overrides["soldiersUseMunitions"])

    city_infra = overrides.get("cityInfrastructure")
    city_land = overrides.get("cityLand")
    if city_infra is not None or city_land is not None:
        infra_value = float(city_infra) if city_infra is not None else None
        land_value = float(city_land) if city_land is not None else None
        nation["cities"] = [
            {
                "infrastructure": infra_value if infra_value is not None else 0,
                "land": land_value if land_value is not None else 0,
            }
        ]


def _apply_war_override(
    nation: dict[str, Any], nation1_id: int, nation2_id: int, war: dict[str, Any]
) -> None:
    if not war:
        return

    attacker_id = _parse_int(war.get("attackerId")) or nation1_id
    defender_id = _parse_int(war.get("defenderId")) or nation2_id

    def _id_or_none(value: Any) -> str | None:
        parsed = _parse_int(value)
        return str(parsed) if parsed else None

    uses_nation_slots = any(
        k in war for k in ("nation1Fortified", "nation2Fortified")
    )
    if uses_nation_slots:
        att_fortify, def_fortify = _fortify_att_def_from_slots(
            nation1_id,
            nation2_id,
            attacker_id,
            bool(war.get("nation1Fortified", False)),
            bool(war.get("nation2Fortified", False)),
        )
    else:
        att_fortify = bool(war.get("attackerFortified", False))
        def_fortify = bool(war.get("defenderFortified", False))

    war_entry = {
        "attid": str(attacker_id),
        "defid": str(defender_id),
        "turnsleft": 1,
        "war_type": war.get("warType") or "ORDINARY",
        "groundcontrol": _id_or_none(war.get("groundControlId")),
        "airsuperiority": _id_or_none(war.get("airSuperiorityId")),
        "navalblockade": _id_or_none(war.get("navalBlockadeId")),
        "att_fortify": att_fortify,
        "def_fortify": def_fortify,
        "attpeace": bool(war.get("attackerPeace", False)),
        "defpeace": bool(war.get("defenderPeace", False)),
    }

    nation["wars"] = [war_entry]


def _build_prefill_inputs(
    results: dict[str, Any], nation1_id: int, nation2_id: int
) -> dict[str, Any]:
    nation1 = results.get("nation1", {})
    nation2 = results.get("nation2", {})

    def _nation_inputs(nation: dict[str, Any], nation_key: str) -> dict[str, Any]:
        city = nation.get("city", {})
        return {
            "id": int(nation.get("id", 0)),
            "soldiers": int(nation.get("soldiers", 0)),
            "tanks": int(nation.get("tanks", 0)),
            "aircraft": int(nation.get("aircraft", 0)),
            "ships": int(nation.get("ships", 0)),
            "missiles": int(nation.get("missiles", 0)),
            "nukes": int(nation.get("nukes", 0)),
            "warpolicy": nation.get("warpolicy", ""),
            "vds": bool(nation.get("vds", False)),
            "irond": bool(nation.get("irond", False)),
            "falloutShelter": bool(nation.get("fallout_shelter", False)),
            "guidingSatellite": bool(nation.get("guiding_satellite", False)),
            "militarySalvage": bool(nation.get("military_salvage", False)),
            "advancedPirateEconomy": bool(nation.get("advanced_pirate_economy", False)),
            "soldiersUseMunitions": bool(results.get(f"{nation_key}_soldiers_use_munitions", True)),
            "cityInfrastructure": float(city.get("infrastructure", 0)),
            "cityLand": float(city.get("land", 0)),
        }

    war = _extract_active_war(nation1.get("wars", []), nation1_id, nation2_id)

    if war:
        attacker_id = int(war.get("attid", nation1_id))
        defender_id = int(war.get("defid", nation2_id))
        war_type = war.get("war_type") or "ORDINARY"
        ground_control = _parse_int(war.get("groundcontrol"))
        air_superiority = _parse_int(war.get("airsuperiority"))
        naval_blockade = _parse_int(war.get("navalblockade"))
        att_fortify = bool(war.get("att_fortify", False))
        def_fortify = bool(war.get("def_fortify", False))
        attacker_peace = bool(war.get("attpeace", False))
        defender_peace = bool(war.get("defpeace", False))
    else:
        attacker_id = nation1_id
        defender_id = nation2_id
        war_type = "ORDINARY"
        ground_control = None
        air_superiority = None
        naval_blockade = None
        att_fortify = False
        def_fortify = False
        attacker_peace = False
        defender_peace = False

    nation1_fortified, nation2_fortified = _fortify_slots_from_att_def(
        nation1_id, nation2_id, attacker_id, att_fortify, def_fortify
    )

    return {
        "nation1Id": nation1_id,
        "nation2Id": nation2_id,
        "nation1": _nation_inputs(nation1, "nation1"),
        "nation2": _nation_inputs(nation2, "nation2"),
        "war": {
            "attackerId": attacker_id,
            "defenderId": defender_id,
            "warType": war_type,
            "groundControlId": ground_control,
            "airSuperiorityId": air_superiority,
            "navalBlockadeId": naval_blockade,
            "nation1Fortified": nation1_fortified,
            "nation2Fortified": nation2_fortified,
            "attackerPeace": attacker_peace,
            "defenderPeace": defender_peace,
        },
    }


def _extract_active_war(
    wars: list[dict[str, Any]], nation1_id: int, nation2_id: int
) -> dict[str, Any] | None:
    for war in wars or []:
        if int(war.get("turnsleft", 0)) <= 0:
            continue
        att_id = int(war.get("attid", 0))
        def_id = int(war.get("defid", 0))
        if {att_id, def_id} == {nation1_id, nation2_id}:
            return war
    return None


def _build_damage_response(
    results: dict[str, Any],
    *,
    inputs: dict[str, Any],
    chart_data: dict[str, Any],
) -> dict[str, Any]:
    nation1_info = _extract_nation_data(results, "nation1")
    nation2_info = _extract_nation_data(results, "nation2")

    scenario1_attacker = _build_attack_analysis(results, "nation1", "nation2", perspective="attacker")
    scenario1_defender = _build_attack_analysis(results, "nation2", "nation1", perspective="attacker")
    scenario2_attacker = _build_attack_analysis(results, "nation2", "nation1", perspective="attacker")
    scenario2_defender = _build_attack_analysis(results, "nation1", "nation2", perspective="attacker")

    return {
        "nations": {
            "nation1": nation1_info,
            "nation2": nation2_info,
        },
        "scenarios": {
            "nation1Attacks": {
                "attacker": {"info": nation1_info, "stats": scenario1_attacker},
                "defender": {"info": nation2_info, "stats": scenario1_defender},
            },
            "nation2Attacks": {
                "attacker": {"info": nation2_info, "stats": scenario2_attacker},
                "defender": {"info": nation1_info, "stats": scenario2_defender},
            },
        },
        "attackTypes": ATTACK_TYPES,
        "chartData": chart_data,
        "warStatus": {
            "nation1Modifiers": results.get("nation1_append", ""),
            "nation2Modifiers": results.get("nation2_append", ""),
            "groundControl": results.get("gc", {}).get("nation_name") if results.get("gc") else None,
        },
        "inputs": inputs,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _build_attack_analysis(
    results: dict[str, Any],
    attacker: str,
    defender: str,
    *,
    perspective: str,
) -> dict[str, Any]:
    """
    Build comprehensive attack analysis for an attacker.
    
    Args:
        results: Raw results dict from cache.
        attacker: Key for attacking nation ('nation1' or 'nation2').
        defender: Key for defending nation.
    
    Returns:
        Object containing per-resistance, per-MAP, and total stats.
    """
    attacker_info = results.get(attacker, {})
    vds = attacker_info.get('vds', False)
    irond = attacker_info.get('irond', False)

    is_attacker_view = perspective == 'attacker'
    side_key = attacker if is_attacker_view else defender
    net_sign = 1 if is_attacker_view else -1
    
    per_resistance = []
    per_map = []
    total_stats = []
    
    for attack_config in ATTACK_TYPES:
        attack_type = attack_config['type']
        maps = attack_config['maps']
        label = attack_config['label']
        
        # Calculate resistance based on attack type and win rates
        resistance = _calculate_resistance(
            attack_type, 
            results.get(f'{attacker}_ground_win_rate', 0.5),
            results.get(f'{attacker}_air_win_rate', 0.5),
            results.get(f'{attacker}_naval_win_rate', 0.5),
            vds,
            irond
        )
        
        # Base values from results
        net_damage = results.get(f'{attacker}_{attack_type}_net', 0)
        attacker_total = results.get(f'{attacker}_{attack_type}_{attacker}_total', 0)
        defender_total = results.get(f'{attacker}_{attack_type}_{defender}_total', 0)
        side_gas = results.get(f'{attacker}_{attack_type}_{side_key}_gas', 0)
        side_mun = results.get(f'{attacker}_{attack_type}_{side_key}_mun', 0)
        side_steel = results.get(f'{attacker}_{attack_type}_{side_key}_steel', 0)
        side_alum = results.get(f'{attacker}_{attack_type}_{side_key}_alum', 0)
        side_money = results.get(f'{attacker}_{attack_type}_{side_key}_money', 0)
        side_uranium = results.get(f'{attacker}_{attack_type}_{side_key}_uranium', 0)
        side_food = results.get(f'{attacker}_{attack_type}_{side_key}_food', 0)
        infra_destroyed = results.get(f'{attacker}_{attack_type}_{defender}_lost_infra_avg_value', 0)

        if attack_type == 'nuke' and side_uranium == 0 and side_key == attacker:
            side_uranium = 500
        
        # Per resistance stats (for when you're winning)
        if resistance > 0:
            per_resistance.append({
                'attackType': attack_type,
                'label': label,
                'netDamage': round(net_damage * net_sign / resistance),
                'damageDealt': round((defender_total if is_attacker_view else attacker_total) / resistance),
                'damageReceived': round((attacker_total if is_attacker_view else defender_total) / resistance),
                'gasConsumed': round(side_gas / resistance),
                'munConsumed': round(side_mun / resistance),
                'steelConsumed': round(side_steel / resistance),
                'alumConsumed': round(side_alum / resistance),
                'uraniumConsumed': round(side_uranium / resistance),
                'foodConsumed': round(side_food / resistance),
                'moneyUsed': round(side_money / resistance),
                'infraDestroyed': round(infra_destroyed / resistance),
            })
        else:
            per_resistance.append({
                'attackType': attack_type,
                'label': label,
                'netDamage': 0,
                'damageDealt': 0,
                'damageReceived': 0,
                'gasConsumed': 0,
                'munConsumed': 0,
                'steelConsumed': 0,
                'alumConsumed': 0,
                'uraniumConsumed': 0,
                'foodConsumed': 0,
                'moneyUsed': 0,
                'infraDestroyed': 0,
            })
        
        # Per MAP stats (for when you're losing)
        per_map.append({
            'attackType': attack_type,
            'label': label,
            'netDamage': round(net_damage * net_sign / maps),
            'damageDealt': round((defender_total if is_attacker_view else attacker_total) / maps),
            'damageReceived': round((attacker_total if is_attacker_view else defender_total) / maps),
            'gasConsumed': round(side_gas / maps),
            'munConsumed': round(side_mun / maps),
            'steelConsumed': round(side_steel / maps),
            'alumConsumed': round(side_alum / maps),
            'uraniumConsumed': round(side_uranium / maps),
            'foodConsumed': round(side_food / maps),
            'moneyUsed': round(side_money / maps),
            'infraDestroyed': round(infra_destroyed / maps),
        })
        
        # Total stats (reference values)
        total_stats.append({
            'attackType': attack_type,
            'label': label,
            'netDamage': round(net_damage * net_sign),
            'damageDealt': round(defender_total if is_attacker_view else attacker_total),
            'damageReceived': round(attacker_total if is_attacker_view else defender_total),
            'gasConsumed': round(side_gas),
            'munConsumed': round(side_mun),
            'steelConsumed': round(side_steel),
            'alumConsumed': round(side_alum),
            'uraniumConsumed': round(side_uranium),
            'foodConsumed': round(side_food),
            'moneyUsed': round(side_money),
            'infraDestroyed': round(infra_destroyed),
        })
    
    return {
        'perResistance': per_resistance,
        'perMap': per_map,
        'perAttack': total_stats,
    }


def _calculate_resistance(
    attack_type: str,
    ground_win_rate: float,
    air_win_rate: float,
    naval_win_rate: float,
    vds: bool,
    irond: bool
) -> float:
    """
    Calculate resistance dealt per attack based on type and win rates.
    
    Args:
        attack_type: The type of attack being performed.
        ground_win_rate: Probability of winning ground battles.
        air_win_rate: Probability of winning air battles.
        naval_win_rate: Probability of winning naval battles.
        vds: Whether defender has Vital Defense System.
        irond: Whether defender has Iron Dome.
    
    Returns:
        Expected resistance dealt per attack.
    """
    if attack_type == 'ground':
        return 10 * ground_win_rate
    elif attack_type.startswith('air'):
        return 12 * air_win_rate
    elif attack_type.startswith('naval'):
        return 14 * naval_win_rate
    elif attack_type == 'nuke':
        return 25 * (1 - 0.2 * int(vds))
    elif attack_type == 'missile':
        return 18 * (1 - 0.5 * int(irond))
    return 0


def _generate_chart_data(results: dict[str, Any]) -> dict[str, Any]:
    """
    Generate pre-formatted data for frontend charts.
    
    Args:
        results: Raw results dict from cache.
    
    Returns:
        Chart-ready data structure for Mantine Charts.
    """
    nation1_name = results.get('nation1', {}).get('nation_name', 'Nation 1')
    nation2_name = results.get('nation2', {}).get('nation_name', 'Nation 2')
    
    # Net damage comparison bar chart data
    net_damage_chart = []
    for attack_config in ATTACK_TYPES:
        attack_type = attack_config['type']
        label = attack_config['label']
        
        nation1_net = results.get(f'nation1_{attack_type}_net', 0)
        nation2_net = results.get(f'nation2_{attack_type}_net', 0)
        
        net_damage_chart.append({
            'attackType': label,
            nation1_name: round(nation1_net),
            nation2_name: round(nation2_net),
        })
    
    return {
        'netDamageComparison': {
            'data': net_damage_chart,
            'series': [
                {'name': nation1_name, 'color': 'blue.6'},
                {'name': nation2_name, 'color': 'red.6'},
            ],
        },
    }
