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

from flask import Blueprint, current_app, jsonify, request

from api.security import optional_discord_session
from database.mongo import get_sync_db
from database.sqlite_cache import get_all_alliances, get_all_nations_filtered, get_nation_by_id
from logic.common import normalize_alliance_position
from logic.nuke_targets import (
    IRON_DOME_INTERCEPT_CHANCE,
    MISSILE_RESISTANCE_ON_HIT,
    NUKE_RESISTANCE_ON_HIT,
    VDS_INTERCEPT_CHANCE,
    compute_nuke_missile_metrics,
    metrics_to_dict,
)
from logic.raids import (
    calculate_days_inactive,
    derive_def_slots_and_time_since_war,
    is_in_vacation_mode,
)

logger = logging.getLogger(__name__)

nuke_targets_bp = Blueprint("nuke_targets", __name__, url_prefix="/api/nuke-targets")


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
        min_score = 15 if req_min_score is None else max(15, float(req_min_score))
        max_score = request.args.get("maxScore", type=float)
        vmode_param = request.args.get("vmode", default="false")
        if isinstance(vmode_param, str):
            vmode_param = vmode_param.lower() in ("true", "1", "yes")

        data_path = Path(current_app.root_path).parent / "data" / "nations.db"
        nations_data = get_all_nations_filtered(
            data_path,
            min_score=min_score,
            max_score=max_score,
        )
        nations = nations_data["nations"]
        last_fetched = nations_data.get("last_fetched")
        nations_by_id: dict[str, dict[str, Any]] = {
            str(n.get("id")): n for n in nations
        }

        alliances_by_id: dict[str, dict[str, Any]] = {}
        alliances_path = Path(current_app.root_path).parent / "data" / "alliances.db"
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

        mongo_db = get_sync_db()
        user_profile = None
        discord_linked = False
        if mongo_db is not None and user_id is not None:
            try:
                uid = int(user_id)
                user_profile = mongo_db.global_users.find_one({"user": uid})
                nation_id_text = (
                    str(user_profile.get("id")).strip()
                    if user_profile and user_profile.get("id") is not None
                    else ""
                )
                discord_linked = bool(nation_id_text)
            except (TypeError, ValueError):
                user_profile = None
                discord_linked = False

        attacker = None
        requested_attacker_missing = False
        if attacker_nation_id:
            attacker = nations_by_id.get(str(attacker_nation_id))
            if attacker is None:
                try:
                    attacker_data = get_nation_by_id(data_path, str(attacker_nation_id))
                    attacker = attacker_data.get("nation")
                except Exception:
                    attacker = None
            if attacker is None:
                requested_attacker_missing = True
        if attacker is None and user_profile:
            attacker_id = str(user_profile.get("id", ""))
            attacker = nations_by_id.get(attacker_id)
            if attacker is None and attacker_id:
                try:
                    attacker_data = get_nation_by_id(data_path, attacker_id)
                    attacker = attacker_data.get("nation")
                except Exception:
                    pass

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

            in_vm = is_in_vacation_mode(nation)
            if vmode_param is False and in_vm:
                continue
            if vmode_param is True and not in_vm:
                continue

            alliance_position = normalize_alliance_position(nation.get("alliance_position"))
            alliance_id = str(nation.get("alliance_id", ""))
            alliance_obj = nation.get("alliance", {}) or {}
            alliance_name = alliance_obj.get("name", "None") or (
                alliances_by_id.get(alliance_id, {}) or {}
            ).get("name", "None")

            def_slots, time_since_war = derive_def_slots_and_time_since_war(nation, now_utc)
            days_inactive = calculate_days_inactive(nation.get("last_active"), now_utc)

            row: dict[str, Any] = {
                "id": int(nation.get("id", 0)),
                "nationName": nation.get("nation_name", "Unknown"),
                "leaderName": nation.get("leader_name", "Unknown"),
                "allianceId": alliance_id or "0",
                "allianceName": alliance_name,
                "alliancePosition": alliance_position or "Unknown",
                "numCities": nation.get("num_cities", 0),
                "score": float(nation.get("score", 0) or 0),
                "color": nation.get("color", ""),
                "beigeTurns": nation.get("beige_turns", 0),
                "daysInactive": days_inactive,
                "defSlots": def_slots,
                "timeSinceWar": time_since_war,
                "soldiers": nation.get("soldiers", 0),
                "tanks": nation.get("tanks", 0),
                "aircraft": nation.get("aircraft", 0),
                "ships": nation.get("ships", 0),
                "missiles": nation.get("missiles", 0),
                "nukes": nation.get("nukes", 0),
            }

            if attacker_for_calc:
                metrics = compute_nuke_missile_metrics(attacker_for_calc, nation)
                if metrics is None:
                    continue
                row.update(metrics_to_dict(metrics))
            else:
                cities = nation.get("cities") or []
                if not cities:
                    continue
                infra_values = [
                    float(c.get("infrastructure") or c.get("infra") or 0)
                    for c in cities
                    if isinstance(c, dict)
                ]
                if not infra_values:
                    continue
                row.update(
                    {
                        "maxInfra": max(infra_values),
                        "avgInfra": sum(infra_values) / len(infra_values),
                        "vds": bool(nation.get("vds")),
                        "ironDome": bool(nation.get("irond")),
                        "falloutShelter": bool(nation.get("fallout_shelter")),
                        "defenderWarPolicy": str(nation.get("warpolicy") or ""),
                    }
                )

            targets.append(row)

        attacker_payload = None
        if attacker and attacker_for_calc:
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
                    (attacker_for_calc or {}).get("warpolicy") == "Attrition"
                    if attacker_for_calc
                    else None
                ),
                "attackerGuidingSatellite": (
                    bool((attacker_for_calc or {}).get("guiding_satellite"))
                    if attacker_for_calc
                    else None
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
