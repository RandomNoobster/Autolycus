"""
Nuke Targets API Routes

List nations from SQLite cache with nuke/missile damage metrics and simulated
attrition-war net damage. Table filters (alliance, beige, infra, etc.) are
applied on the web client; GET / only applies score bounds and vacation mode.
"""
import copy
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from flask import Blueprint, jsonify, request

from api.request_utils import optional_session_profile
from api.security import optional_discord_session
from database.sqlite_cache import (get_alliances_db_path, get_all_alliances,
                                   get_all_nations_filtered, get_nation_by_id,
                                   get_nations_db_path)
from database.users import linked_nation_id
from logic.common import normalize_alliance_position
from logic.nuke_targets import (
    IRON_DOME_INTERCEPT_CHANCE,
    MISSILE_RESISTANCE_ON_HIT,
    NUKE_RESISTANCE_ON_HIT,
    VDS_INTERCEPT_CHANCE,
    compute_nuke_missile_metrics,
    defender_summary,
    metrics_to_dict,
)
from logic.raids import calculate_days_inactive, is_in_vacation_mode, stored_time_since_war

logger = logging.getLogger(__name__)

nuke_targets_bp = Blueprint("nuke_targets", __name__, url_prefix="/api/nuke-targets")

# What the table and the per-target metrics read. Wars and other blobs stay unread:
# defensive slots and time since war are precomputed by the scanner, and only the
# attacker's own row (loaded in full) needs its wars.
_NUKE_SELECT_COLUMNS = [
    "id", "nation_name", "leader_name", "alliance_id", "alliance_position", "alliance",
    "num_cities", "score", "color", "beige_turns", "last_active",
    "vacation_mode_turns", "vmode",
    "soldiers", "tanks", "aircraft", "ships", "missiles", "nukes",
    "def_slots", "time_since_war", "cities",
    "warpolicy", "war_policy", "vds", "vital_defense_system", "irond", "iron_dome",
    "fallout_shelter",
    # infra_rebuild_cost discounts (logic/economy.py)
    "dompolicy", "domestic_policy", "government_support_agency",
    "bureau_of_domestic_affairs", "center_for_civil_engineering",
    "advanced_engineering_corps",
]
_NUKE_JSON_FIELDS = {"cities", "alliance"}


def _parse_optional_bool(raw: Optional[str]) -> Optional[bool]:
    if raw is None:
        return None
    return str(raw).lower() in ("true", "1", "yes")


def apply_attacker_damage_overrides(
    attacker: dict[str, Any],
    *,
    attrition: Optional[bool] = None,
    guiding_satellite: Optional[bool] = None,
) -> dict[str, Any]:
    """
    Return a shallow-copied attacker with optional damage-mod overrides.

    ``attrition=True`` forces Attrition (+10% infra dealt); ``False`` clears the
    attacker war policy so dealt-damage policy mods do not apply.
    ``guiding_satellite`` overrides the Guiding Satellite project flag.
    """
    out = copy.copy(attacker)
    if attrition is not None:
        out["warpolicy"] = "Attrition" if attrition else "None"
    if guiding_satellite is not None:
        out["guiding_satellite"] = bool(guiding_satellite)
    return out


def _load_nation(data_path: Path, nation_id: Any) -> Optional[dict[str, Any]]:
    """The full cached row for ``nation_id`` (wars included), or None."""
    try:
        return get_nation_by_id(data_path, nation_id).get("nation")
    except Exception as exc:  # noqa: BLE001 - a missing attacker falls back
        logger.warning("[nuke-targets] could not load nation %s: %s", nation_id, exc)
        return None


def _alliance_name(nation: dict[str, Any], alliances_by_id: dict[str, dict[str, Any]]) -> str:
    """alliances.db first (kept current hourly), then the nation's own alliance data."""
    alliance_id = str(nation.get("alliance_id") or "0")
    candidates = [(alliances_by_id.get(alliance_id) or {}).get("name")]
    alliance_obj = nation.get("alliance")
    if isinstance(alliance_obj, dict):
        candidates.append(alliance_obj.get("name"))
    for name in candidates:
        if name not in (None, ""):
            return str(name).strip()
    return "None"


def _int_or(value: Any, default: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@nuke_targets_bp.route("/", methods=["GET"])
@optional_discord_session
def get_nuke_targets() -> tuple[Any, int]:
    try:
        req_start = time.perf_counter()
        user_id = getattr(request, "session_user_id", None)

        attacker_nation_id = request.args.get("attackerNationId", type=int)
        attrition_override = _parse_optional_bool(request.args.get("attrition"))
        guiding_satellite_override = _parse_optional_bool(
            request.args.get("guidingSatellite")
        )
        req_min_score = request.args.get("minScore", type=float)
        min_score = 15 if req_min_score is None else max(15, req_min_score)
        max_score = request.args.get("maxScore", type=float)
        vmode_param = _parse_optional_bool(request.args.get("vmode", default="false"))

        data_path = get_nations_db_path()
        nations_data = get_all_nations_filtered(
            data_path,
            min_score=min_score,
            max_score=max_score,
            columns=_NUKE_SELECT_COLUMNS,
            json_fields=_NUKE_JSON_FIELDS,
        )
        nations = nations_data["nations"]
        last_fetched = nations_data.get("last_fetched")

        alliances_by_id: dict[str, dict[str, Any]] = {}
        alliances_path = get_alliances_db_path()
        if alliances_path.exists():
            try:
                alliances_data = get_all_alliances(alliances_path)
                alliances_by_id = {
                    str(a.get("id")): a
                    for a in alliances_data.get("alliances", [])
                    if a.get("id") is not None
                }
            except Exception as exc:
                logger.warning("[nuke-targets] failed to load alliances db: %s", exc)

        linked_id = linked_nation_id(optional_session_profile())
        discord_linked = linked_id is not None

        attacker = None
        requested_attacker_missing = False
        if attacker_nation_id:
            attacker = _load_nation(data_path, attacker_nation_id)
            if attacker is None:
                requested_attacker_missing = True
        if attacker is None and linked_id:
            attacker = _load_nation(data_path, linked_id)

        nation_warning = None
        if requested_attacker_missing:
            if attacker:
                fallback_id = attacker.get("id")
                fallback_name = attacker.get("nation_name") or f"Nation {fallback_id}"
                nation_warning = (
                    f"Nation ID {attacker_nation_id} not found in database. "
                    f"Using {fallback_name} (ID {fallback_id}) for damage metrics."
                )
            else:
                nation_warning = (
                    f"Nation ID {attacker_nation_id} not found in database. "
                    "Damage metrics require a valid attacker nation."
                )

        attacker_for_calc = None
        if attacker:
            attacker_for_calc = apply_attacker_damage_overrides(
                attacker,
                attrition=attrition_override,
                guiding_satellite=guiding_satellite_override,
            )

        now_utc = datetime.now(timezone.utc)
        targets: list[dict[str, Any]] = []

        for nation in nations:
            if attacker and str(nation.get("id")) == str(attacker.get("id")):
                continue

            if is_in_vacation_mode(nation) != vmode_param:
                continue

            try:
                if attacker_for_calc:
                    metrics = compute_nuke_missile_metrics(attacker_for_calc, nation)
                    summary = metrics_to_dict(metrics) if metrics is not None else None
                else:
                    summary = defender_summary(nation)
            except Exception as exc:  # noqa: BLE001 - one bad row must not fail the list
                logger.warning("[nuke-targets] skipping nation %s: %s", nation.get("id"), exc)
                continue
            if summary is None:
                continue

            row: dict[str, Any] = {
                "id": int(nation.get("id", 0)),
                "nationName": nation.get("nation_name", "Unknown"),
                "leaderName": nation.get("leader_name", "Unknown"),
                "allianceId": str(nation.get("alliance_id") or "0"),
                "allianceName": _alliance_name(nation, alliances_by_id),
                "alliancePosition": normalize_alliance_position(nation.get("alliance_position")) or "Unknown",
                "numCities": nation.get("num_cities", 0),
                "score": float(nation.get("score", 0) or 0),
                "color": nation.get("color", ""),
                "beigeTurns": nation.get("beige_turns", 0),
                "daysInactive": calculate_days_inactive(nation.get("last_active"), now_utc),
                # Precomputed by the scanner (as on the raids page).
                "defSlots": _int_or(nation.get("def_slots"), 0),
                "timeSinceWar": stored_time_since_war(nation.get("time_since_war")),
                "soldiers": nation.get("soldiers", 0),
                "tanks": nation.get("tanks", 0),
                "aircraft": nation.get("aircraft", 0),
                "ships": nation.get("ships", 0),
                "missiles": nation.get("missiles", 0),
                "nukes": nation.get("nukes", 0),
            }
            row.update(summary)
            targets.append(row)

        attacker_payload = None
        if attacker_for_calc:
            nation_policy = str(attacker.get("warpolicy") or "")
            nation_gs = bool(attacker.get("guiding_satellite"))
            effective_policy = str(attacker_for_calc.get("warpolicy") or "")
            effective_gs = bool(attacker_for_calc.get("guiding_satellite"))
            attacker_payload = {
                "id": attacker.get("id"),
                "nation_name": attacker.get("nation_name"),
                "leader_name": attacker.get("leader_name"),
                "score": float(attacker.get("score", 0) or 0),
                "warpolicy": nation_policy,
                "guidingSatellite": nation_gs,
                "effectiveWarPolicy": effective_policy,
                "effectiveGuidingSatellite": effective_gs,
                "attrition": effective_policy == "Attrition",
            }

        response = {
            "attacker": attacker_payload,
            "targets": targets,
            "generatedAt": (
                datetime.fromtimestamp(last_fetched, tz=timezone.utc).isoformat()
                if last_fetched
                else datetime.now(timezone.utc).isoformat()
            ),
            "discordAuthenticated": user_id is not None,
            "discordLinked": discord_linked,
            "assumptions": {
                "warType": "ATTRITION",
                "warRole": "attacker",
                "resistanceModel": "expected_value_intercepts",
                "resistanceOnHit": {"nuke": NUKE_RESISTANCE_ON_HIT, "missile": MISSILE_RESISTANCE_ON_HIT},
                "interceptChance": {"vds": VDS_INTERCEPT_CHANCE, "ironDome": IRON_DOME_INTERCEPT_CHANCE},
                "dollarDamage": "infra_rebuild_cost",
                "attackerAttrition": (
                    attacker_for_calc.get("warpolicy") == "Attrition" if attacker_for_calc else None
                ),
                "attackerGuidingSatellite": (
                    bool(attacker_for_calc.get("guiding_satellite")) if attacker_for_calc else None
                ),
            },
            "warning": nation_warning,
        }

        duration = time.perf_counter() - req_start
        logger.info(
            "[nuke-targets] served targets=%d attacker=%s duration=%.3fs",
            len(targets),
            attacker.get("id") if attacker else None,
            duration,
        )
        return jsonify(response), 200

    except Exception as exc:
        logger.error("[nuke-targets] error: %s", exc, exc_info=True)
        return (
            jsonify(
                {
                    "error": "Internal server error",
                    "message": "An unexpected error occurred.",
                    "code": "INTERNAL_ERROR",
                }
            ),
            500,
        )
