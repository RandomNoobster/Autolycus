"""
Raids API Routes

This module provides API endpoints for the raids feature, including
target listings and beige reminder functionality.
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import motor.motor_asyncio
from flask import Blueprint, current_app, jsonify, request
from pymongo import MongoClient

import queries
from api.security import require_token
from logic import api_client, merge_utils
from logic.common import beige_loot_value
from logic.military import calculate_win_chance_raw
from logic.revenue import pre_revenue_calc, revenue_calc
from utils.db_utils import get_all_alliances, get_all_nations

logger = logging.getLogger(__name__)

raids_bp = Blueprint('raids', __name__, url_prefix='/api/raids')

# MongoDB connection (lazy initialization)
async_client = None
async_mongo = None
sync_client: Optional[MongoClient] = None
sync_db = None


def _parse_war_date(date_str: Optional[str]) -> datetime:
    """Best-effort parser for war dates to enable ordering."""
    if not date_str:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        if "T" in date_str:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _is_in_vacation_mode(nation: dict[str, Any]) -> bool:
    """Determine whether a nation is currently in Vacation Mode (VM).

    Supports multiple field shapes that can appear in cached nation rows:
    - 'vmode': may be bool or numeric (0/1 or turns)
    - 'vacation_mode_turns': numeric remaining turns in VM
    Returns True if VM is active, False otherwise.
    """
    vmode = nation.get('vmode')
    if isinstance(vmode, bool):
        if vmode:
            return True
    elif isinstance(vmode, (int, float)):
        if vmode > 0:
            return True

    vmt = nation.get('vacation_mode_turns')
    try:
        vmt_val = int(vmt) if vmt is not None else 0
    except (TypeError, ValueError):
        vmt_val = 0
    return vmt_val > 0


def _compute_beige_loot(nation: dict[str, Any], prices: Optional[dict[str, float]]) -> Optional[int]:
    """Compute last beige loot value from finished wars using cached war logs.

    Optimized to scan once without sorting (reduces per-request overhead when many wars exist).
    """
    t0 = time.perf_counter()
    if not prices:
        logger.debug("[beige] skip: prices unavailable nation=%s", nation.get('id'))
        return None

    wars = nation.get('wars') or []
    nation_id = str(nation.get('id', ''))
    if not nation_id or not wars:
        logger.debug("[beige] skip: no wars nation=%s", nation.get('id'))
        return None

    best_loot: Optional[int] = None
    best_date: Optional[datetime] = None
    best_war_id: Optional[str] = None
    scanned = 0

    for war in wars:
        try:
            scanned += 1
            turns_left = war.get('turnsleft', 1)
            try:
                turns_left_val = float(turns_left)
            except (TypeError, ValueError):
                turns_left_val = 1
            if turns_left_val > 0:
                logger.debug(
                    "[beige] skip: unfinished war nation=%s warId=%s turnsleft=%s",
                    nation.get('id'),
                    war.get('id'),
                    turns_left,
                )
                continue  # still active
            if str(war.get('defid')) != nation_id:
                logger.debug(
                    "[beige] skip: nation not defender nation=%s warId=%s defid=%s",
                    nation.get('id'),
                    war.get('id'),
                    war.get('defid'),
                )
                continue  # only care about wars where this nation was defender/lost beige

            war_dt = _parse_war_date(war.get('date'))
            attacks = war.get('attacks') or []

            for attack in reversed(attacks):  # reverse to favor latest attack within the war
                text = attack.get('loot_info')
                if not text or "won the war and looted" not in text:
                    continue
                victor = str(attack.get('victor', ''))
                if victor == nation_id:
                    continue  # they won, so no beige loot

                try:
                    loot_value = float(beige_loot_value(text, prices))
                except Exception as parse_exc:
                    logger.debug(
                        "[beige] parse error nation=%s warId=%s loot_info=%s err=%s",
                        nation.get('id'),
                        war.get('id'),
                        str(text)[:120],
                        parse_exc,
                    )
                    continue

                attacker_info = war.get('attacker') or {}
                policy = (attacker_info.get('war_policy') or '').upper()
                # Policy adjustments
                if policy == "ATTRITION":
                    loot_value = loot_value / 0.8
                elif policy == "PIRATE":
                    loot_value = loot_value / 1.4
                if attacker_info.get('advanced_pirate_economy'):
                    loot_value = loot_value / 1.1

                war_type = (war.get('war_type') or '').upper()
                # War-type multipliers
                if war_type == "ATTRITION":
                    loot_value *= 4
                elif war_type == "ORDINARY":
                    loot_value *= 2

                logger.debug(
                    "[beige] candidate nation=%s warId=%s date=%s value=%.2f type=%s policy=%s advPir=%s",
                    nation.get('id'),
                    war.get('id'),
                    war.get('date'),
                    loot_value,
                    war_type,
                    policy,
                    bool(attacker_info.get('advanced_pirate_economy')),
                )

                if best_date is None or war_dt > best_date:
                    best_date = war_dt
                    best_loot = int(round(loot_value))
                    best_war_id = str(war.get('id'))
                    break  # latest attack in this war found; move to next war
        except Exception as exc:  # pragma: no cover - defensive guard for malformed war data
            logger.debug(f"Failed to compute beige loot for nation {nation_id}: {exc}")
            continue

    return best_loot

def get_mongo():
    """Lazy initialize MongoDB connection."""
    global async_client, async_mongo
    if async_client is None:
        async_client = motor.motor_asyncio.AsyncIOMotorClient(
            os.getenv("pymongolink"), 
            serverSelectionTimeoutMS=5000
        )
        version = os.getenv("version")
        async_mongo = async_client[str(version)]
    return async_mongo


def get_sync_mongo():
    """Lazy initialize synchronous MongoDB connection for Flask routes."""
    global sync_client, sync_db
    if sync_client is None:
        mongo_uri = current_app.config.get('MONGO_URI') or os.getenv("pymongolink")
        if not mongo_uri:
            return None
        sync_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db_name = current_app.config.get('MONGO_DB', os.getenv("version", "autolycus"))
        sync_db = sync_client[db_name]
    return sync_db


@raids_bp.route('/', methods=['GET'])
@require_token
def get_raids() -> tuple[Any, int]:
    """
    Get raid targets for the authenticated user.
    
    Token payload must contain:
        - user_id: Discord user ID
        - timestamp: Data generation timestamp
    
    Query Parameters (for filtering):
        - minCities: Minimum city count
        - maxCities: Maximum city count
        - alliance: Filter by alliance name (partial match)
        - beige: Filter to only beige targets (true/false)
    
    Returns:
        JSON response with:
        - attacker: The attacking nation's info
        - targets: List of raid targets with all relevant metrics
        - beige_alerts: List of active beige reminders
        - generated_at: ISO timestamp of data generation
    """
    try:
        req_start = time.perf_counter()
        token_payload = getattr(request, 'token_payload', {}) or {}
        user_id = token_payload.get('user_id')

        # Parse filters and attacker nation ID override
        attacker_nation_id = request.args.get('attackerNationId', type=int)
        min_cities = request.args.get('minCities', type=int)
        max_cities = request.args.get('maxCities', type=int)
        alliance_filter = request.args.get('alliance')
        target_nation_ids_raw = request.args.get('targetNationIds')
        use_saved_targets = request.args.get('useSavedTargets', default=None)
        target_nation_ids: Optional[set[str]] = None
        if isinstance(use_saved_targets, str):
            use_saved_targets = use_saved_targets.lower() in ('true', '1', 'yes')

        if target_nation_ids_raw:
            parsed_ids = []
            for part in target_nation_ids_raw.split(','):
                part = part.strip()
                if part.isdigit():
                    parsed_ids.append(part)
            if parsed_ids:
                target_nation_ids = set(parsed_ids)
        beige_only = request.args.get('beige', default=None)
        max_wars = request.args.get('maxWars', type=int)
        inactive_min_days = request.args.get('inactiveMinDays', type=int)
        scope = request.args.get('scope')  # all | apps_or_none | no_alliance
        min_beige_loot = request.args.get('minBeigeLoot', type=int)
        performance_filter = request.args.get('performance', default=None)
        # Enforce minimum score threshold for efficiency; clamp to >= 15
        req_min_score = request.args.get('minScore', type=float)
        min_score = 15 if req_min_score is None else max(15, float(req_min_score))
        max_score = request.args.get('maxScore', type=float)
        # Allow explicit VM filtering via query param; default to excluding VM (vmode=false)
        vmode_param = request.args.get('vmode', default='false')
        if isinstance(vmode_param, str):
            vmode_param = vmode_param.lower() in ('true', '1', 'yes')
        # When vmode_param is False, we will exclude VM nations; when True, include only VM nations
        max_score = request.args.get('maxScore', type=float)
        if isinstance(beige_only, str):
            beige_only = beige_only.lower() in ('true', '1', 'yes')
        if isinstance(performance_filter, str):
            performance_filter = performance_filter.lower() in ('true', '1', 'yes')

        logger.info(
            "[raids] request start user=%s params: attackerNationId=%s alliance=%s beige=%s "
            "maxWars=%s inactiveMinDays=%s scope=%s minBeigeLoot=%s performance=%s "
            "minScore=%s maxScore=%s targetNationIds=%s useSavedTargets=%s",
            user_id,
            attacker_nation_id,
            alliance_filter,
            beige_only,
            max_wars,
            inactive_min_days,
            scope,
            min_beige_loot,
            performance_filter,
            min_score,
            max_score,
            len(target_nation_ids or []),
            use_saved_targets,
        )

        # Load nations from SQLite cache
        data_path = Path(current_app.root_path).parent / 'data' / 'nations.db'
        nations_data = get_all_nations(data_path)
        nations = nations_data['nations']
        last_fetched = nations_data.get('last_fetched')
        logger.info(
            "[raids] loaded nations count=%d lastFetched=%s",
            len(nations),
            last_fetched,
        )

        # Load alliances (for alliance colors/fallback name)
        alliances_by_id: dict[str, dict[str, Any]] = {}
        alliances_path = Path(current_app.root_path).parent / 'data' / 'alliances.db'
        if alliances_path.exists():
            try:
                alliances_data = get_all_alliances(alliances_path)
                alliances_by_id = {
                    str(a.get('id')): a
                    for a in alliances_data.get('alliances', [])
                    if a.get('id') is not None
                }
                logger.info(
                    "[raids] loaded alliances count=%d lastFetched=%s",
                    len(alliances_by_id),
                    alliances_data.get('last_fetched'),
                )
            except Exception as exc:
                logger.warning(f"[raids] failed to load alliances db: {exc}")

        # Fetch user profile from Mongo (sync) to resolve attacker and reminders
        mongo_db = get_sync_mongo()
        user_profile = None
        if mongo_db is not None and user_id:
            try:
                user_profile = mongo_db.global_users.find_one({'user': int(user_id)})
            except Exception:
                user_profile = None

        if use_saved_targets and user_profile and not target_nation_ids:
            stored_ids = user_profile.get('raids_target_ids', [])
            if stored_ids:
                target_nation_ids = set([str(x) for x in stored_ids if str(x).isdigit()])

        attacker = None
        nation_warning = None
        # Priority: URL parameter > user profile > first nation
        if attacker_nation_id:
            attacker = next((n for n in nations if int(n.get('id', 0)) == attacker_nation_id), None)
            if attacker:
                logger.info(f"Found attacker nation by URL parameter: {attacker_nation_id}")
            else:
                logger.warning(f"Nation {attacker_nation_id} not found in database")
                nation_warning = f"Nation ID {attacker_nation_id} not found in database. Using default nation for calculations."
        if attacker is None and user_profile:
            attacker_id = str(user_profile.get('id', ''))
            attacker = next((n for n in nations if str(n.get('id')) == attacker_id), None)
        if attacker is None and nations:
            attacker = nations[0]
            logger.info(f"Falling back to first nation: {attacker.get('id')}")

        beige_alerts = user_profile.get('beige_alerts', []) if user_profile else []

        targets: list[dict[str, Any]] = []
        backfill_attempts = 0
        backfill_successes = 0

        # Attempt to prepare revenue context (prices, treasures, radiation)
        revenue_context: Optional[tuple[Any, dict[str, float], dict[str, float], list[dict[str, Any]], dict[str, float], dict[str, float]]] = None
        prices: Optional[dict[str, float]] = None
        api_key = os.getenv('api_key')
        if api_key and attacker:
            try:
                # pre_revenue_calc returns (nation, colors, prices, treasures, radiation, seasonal_mod)
                revenue_context = asyncio.run(
                    pre_revenue_calc(
                        message=None,
                        query_for_nation=False,
                        parsed_nation=attacker,
                        call_func=lambda q: api_client.call(q, api_key),
                        get_query_func=merge_utils.get_query,
                        queries_module=queries,
                    )
                )
                # Keep prices handy for beige loot backfill
                _, _, prices, _, _, _ = revenue_context
                logger.info("[raids] revenue context prepared; prices loaded")
            except Exception as e:
                logger.warning(f"Revenue context unavailable: {e}")
                revenue_context = None

        apply_filters = target_nation_ids is None

        for nation in nations:
            if target_nation_ids and str(nation.get('id', '')) not in target_nation_ids:
                continue
            # Filters
            if apply_filters:
                if scope == 'apps_or_none':
                    if nation.get('alliance_position') not in ['NOALLIANCE', 'APPLICANT']:
                        continue
                if scope == 'no_alliance':
                    if str(nation.get('alliance_id', '')) != '0':
                        continue
                # Vacation mode filtering
                in_vm = _is_in_vacation_mode(nation)
                if vmode_param is False and in_vm:
                    continue  # exclude VM nations by default
                if vmode_param is True and not in_vm:
                    continue  # include only VM nations when requested
                if min_cities is not None and nation.get('num_cities', 0) < min_cities:
                    continue
                if max_cities is not None and nation.get('num_cities', 0) > max_cities:
                    continue
                score_val = None
                try:
                    score_val = float(nation.get('score', 0))
                except (TypeError, ValueError):
                    score_val = None
                if min_score is not None and score_val is not None and score_val < min_score:
                    continue
                if max_score is not None and score_val is not None and score_val > max_score:
                    continue
            alliance_id = str(nation.get('alliance_id', ''))
            alliance_obj = (nation.get('alliance', {}) or {})

            if apply_filters:
                if alliance_filter:
                    name = alliance_obj.get('name') or (alliances_by_id.get(alliance_id, {}) or {}).get('name', '')
                    if alliance_filter.lower() not in name.lower():
                        continue
                if beige_only is True and nation.get('color') != 'beige':
                    continue
                if beige_only is False and nation.get('color') == 'beige':
                    continue

            # Defensive slots and war recency
            wars = nation.get('wars') or []
            def_slots = 0
            time_since_war: int | str = "14+"
            if wars:
                sorted_wars = sorted(wars, key=lambda w: w.get('date', ''), reverse=True)
                for war in wars:
                    if war.get('turnsleft', 0) > 0 and str(war.get('defid')) == str(nation.get('id')):
                        def_slots += 1
                most_recent = sorted_wars[0]
                war_date = most_recent.get('date')
                if war_date and war_date != '-0001-11-30 00:00:00':
                    try:
                        if 'T' in war_date:
                            dt = datetime.fromisoformat(war_date.replace('Z', '+00:00'))
                        else:
                            dt = datetime.strptime(war_date, "%Y-%m-%d %H:%M:%S")
                            dt = dt.replace(tzinfo=timezone.utc)
                        days = (datetime.now(timezone.utc) - dt).days
                        time_since_war = 0 if def_slots > 0 else days 
                    except Exception:
                        time_since_war = "14+"
                else:
                    time_since_war = "14+"

            # Inactivity
            days_inactive = _calculate_days_inactive(nation.get('last_active'))
            if apply_filters and inactive_min_days is not None and days_inactive < inactive_min_days:
                continue

            # Win chances
            if attacker:
                ground_attack = attacker.get('soldiers', 0) * 1.75 + attacker.get('tanks', 0) * 40
                ground_def = nation.get('soldiers', 0) * 1.75 + nation.get('tanks', 0) * 40 + nation.get('population', 0) * 0.0025
                air_attack = attacker.get('aircraft', 0) * 3
                air_def = nation.get('aircraft', 0) * 3
                naval_attack = attacker.get('ships', 0) * 4
                naval_def = nation.get('ships', 0) * 4
                ground_win = round(calculate_win_chance_raw(ground_attack, ground_def) * 100, 1)
                air_win = round(calculate_win_chance_raw(air_attack, air_def) * 100, 1)
                naval_win = round(calculate_win_chance_raw(naval_attack, naval_def) * 100, 1)
                total_win = round((ground_win + air_win + naval_win) / 3, 1)
            else:
                ground_win = air_win = naval_win = total_win = 50.0

            monetary_net_income = nation.get('monetary_net_num', 0)
            net_cash_income = nation.get('net_cash_num', 0)

            nation_loot_value = 0
            try:
                nation_loot_value = int(nation.get('nation_loot_value', 0) or 0)
            except (TypeError, ValueError):
                nation_loot_value = 0

            # Backfill missing beige loot from cached war logs when possible
            if nation_loot_value <= 0:
                backfill_attempts += 1
                computed_loot = _compute_beige_loot(nation, prices)
                if computed_loot is not None:
                    nation_loot_value = computed_loot
                    backfill_successes += 1
            # Compute revenue if context is available
            if revenue_context:
                try:
                    _, colors, prices_ctx, treasures, radiation, seasonal_mod = revenue_context

                    async def _compute():
                        return await revenue_calc(
                            message=None,
                            nation=nation,
                            radiation=radiation,
                            treasures=treasures,
                            prices=prices_ctx,
                            colors=colors,
                            seasonal_mod=seasonal_mod,
                            include_spies=False,
                        )

                    revenue_result = asyncio.run(_compute()) or {}
                    monetary_net_income = revenue_result.get('monetary_net_num', monetary_net_income)
                    net_cash_income = revenue_result.get('net_cash_num', net_cash_income)
                except Exception as e:
                    logger.debug(f"Revenue calc failed for nation {nation.get('id')}: {e}")

            if apply_filters:
                if min_beige_loot is not None and nation_loot_value < min_beige_loot:
                    continue

                if max_wars is not None and def_slots > max_wars:
                    continue

                if performance_filter:
                    if ground_win < 0.4 or nation_loot_value == 0 or net_cash_income < 10000:
                        continue

            alliance_color = alliance_obj.get('color') or (alliances_by_id.get(alliance_id, {}) or {}).get('color')
            alliance_name = alliance_obj.get('name', 'None') or (alliances_by_id.get(alliance_id, {}) or {}).get('name', 'None')
            nation_color = nation.get('color', '')
            taxable = bool(nation_color and alliance_color and str(nation_color).lower() == str(alliance_color).lower())

            targets.append({
                'id': int(nation.get('id', 0)),
                'nationName': nation.get('nation_name', 'Unknown'),
                'leaderName': nation.get('leader_name', 'Unknown'),
                'allianceId': alliance_id or '0',
                'allianceName': alliance_name,
                'alliancePosition': (nation.get('alliance_position') or 'Unknown'),
                'numCities': nation.get('num_cities', 0),
                'color': nation_color,
                'beigeTurns': nation.get('beige_turns', 0),
                'nationLoot': f"${nation_loot_value:,}",
                'daysInactive': days_inactive,
                'monetaryNetIncome': monetary_net_income,
                'netCashIncome': net_cash_income,
                'taxable': taxable,
                'treasures': len(nation.get('treasures') or []),
                'defSlots': def_slots,
                'timeSinceWar': time_since_war,
                'soldiers': nation.get('soldiers', 0),
                'tanks': nation.get('tanks', 0),
                'aircraft': nation.get('aircraft', 0),
                'ships': nation.get('ships', 0),
                'missiles': nation.get('missiles', 0),
                'nukes': nation.get('nukes', 0),
                'groundWin': ground_win,
                'airWin': air_win,
                'navalWin': naval_win,
                'totalWin': total_win,
                'hasReminderActive': str(nation.get('id')) in [str(x) for x in beige_alerts],
            })

        response = {
            'attacker': {
                'id': attacker.get('id') if attacker else None,
                'nation_name': attacker.get('nation_name') if attacker else None,
                'leader_name': attacker.get('leader_name') if attacker else None,
                'score': float(attacker.get('score', 0)) if attacker else None,
            },
            'targets': targets,
            'beigeAlerts': [str(x) for x in beige_alerts],
            'showBeige': beige_only is not False,
            'generatedAt': datetime.fromtimestamp(last_fetched, tz=timezone.utc).isoformat() if last_fetched else datetime.now(timezone.utc).isoformat(),
            'discordLinked': bool(user_id),
                'warning': nation_warning if 'nation_warning' in locals() else None,
        }

        duration = time.perf_counter() - req_start
        logger.info(
            "[raids] request done nations=%d targets=%d backfill=%d/%d duration=%.2fs",
            len(nations),
            len(targets),
            backfill_successes,
            backfill_attempts,
            duration,
        )

        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error in get_raids: {e}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred.',
            'code': 'INTERNAL_ERROR'
        }), 500


@raids_bp.route('/reminders', methods=['POST'])
@require_token
def add_reminder() -> tuple[Any, int]:
    """
    Add a beige reminder for a nation.
    
    Token payload must contain:
        - user_id: Discord user ID (must match invoker)
    
    Request Body:
        - nationId: ID of the nation to set reminder for
        - beigeTurns: Number of turns until nation exits beige
    
    Returns:
        JSON response confirming the reminder was set.
    """
    try:
        token_payload = getattr(request, 'token_payload', {}) or {}
        user_id = token_payload.get('user_id')
        if not user_id:
            return jsonify({
                'error': 'Authentication required',
                'message': 'Missing user_id in token payload.',
                'code': 'TOKEN_MISSING'
            }), 401

        data = request.get_json() or {}
        nation_id = data.get('nationId')
        beige_turns = data.get('beigeTurns', 0)
        if nation_id is None:
            return jsonify({
                'error': 'Validation error',
                'message': 'nationId is required.',
                'code': 'VALIDATION_ERROR'
            }), 400

        mongo_db = get_sync_mongo()
        if not mongo_db:
            return jsonify({
                'error': 'Database unavailable',
                'message': 'MongoDB is not configured.',
                'code': 'DB_UNAVAILABLE'
            }), 503

        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return jsonify({
                'error': 'Invalid user id',
                'message': 'user_id must be numeric for reminders.',
                'code': 'INVALID_USER'
            }), 400

        mongo_db.global_users.update_one(
            {'user': uid},
            {'$setOnInsert': {'id': str(nation_id), 'beige_alerts': []}},
            upsert=True,
        )
        mongo_db.global_users.update_one(
            {'user': uid},
            {'$addToSet': {'beige_alerts': str(nation_id)}}
        )

        return jsonify({
            'success': True,
            'message': 'Reminder added successfully.',
            'nationId': nation_id,
            'beigeTurns': beige_turns,
        }), 200
        
    except Exception as e:
        logger.error(f"Error adding reminder: {e}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'message': 'Failed to set reminder.',
            'code': 'INTERNAL_ERROR'
        }), 500


@raids_bp.route('/reminders/<nation_id>', methods=['DELETE'])
@require_token
def remove_reminder(nation_id: str) -> tuple[Any, int]:
    """
    Remove a beige reminder for a nation.
    
    Args:
        nation_id: The nation ID to remove reminder for.
    
    Returns:
        JSON response confirming the reminder was removed.
    """
    try:
        token_payload = getattr(request, 'token_payload', {}) or {}
        user_id = token_payload.get('user_id')
        if not user_id:
            return jsonify({
                'error': 'Authentication required',
                'message': 'Missing user_id in token payload.',
                'code': 'TOKEN_MISSING'
            }), 401

        mongo_db = get_sync_mongo()
        if not mongo_db:
            return jsonify({
                'error': 'Database unavailable',
                'message': 'MongoDB is not configured.',
                'code': 'DB_UNAVAILABLE'
            }), 503

        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return jsonify({
                'error': 'Invalid user id',
                'message': 'user_id must be numeric for reminders.',
                'code': 'INVALID_USER'
            }), 400

        mongo_db.global_users.update_one(
            {'user': uid},
            {'$pull': {'beige_alerts': str(nation_id)}}
        )

        return jsonify({
            'success': True,
            'message': 'Reminder removed successfully.',
            'nationId': nation_id,
        }), 200
        
    except Exception as e:
        logger.error(f"Error removing reminder: {e}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'message': 'Failed to remove reminder.',
            'code': 'INTERNAL_ERROR'
        }), 500


@raids_bp.route('/alliances/search', methods=['GET'])
@require_token
def search_alliances():
    """
    Search for alliances by name, acronym, or ID (fuzzy matching).
    
    Query Parameters:
        - q: Search query string (required)
        - limit: Maximum results to return (default: 10)
    
    Returns:
        JSON response with matching alliances.
        
    Note:
        Uses cached alliance data from alliances.db (populated by scanner.py).
    """
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify([]), 200
        
        limit = int(request.args.get('limit', 10))
        limit = min(limit, 50)  # Cap at 50 results

        # Load cached alliances from SQLite
        alliances_path = Path(current_app.root_path).parent / 'data' / 'alliances.db'
        if not alliances_path.exists():
            logger.warning("[alliances/search] alliances.db not found")
            return jsonify([]), 200

        alliances_data = get_all_alliances(alliances_path)
        alliances = alliances_data.get('alliances', [])
        if not alliances:
            logger.info("[alliances/search] alliances.db loaded but empty")
            return jsonify([]), 200
        
        query_lower = query.lower()
        
        # Score and filter alliances for fuzzy matching
        results = []
        for alliance in alliances:
            alliance_id = str(alliance.get('id', ''))
            name = alliance.get('name', '')
            acronym = alliance.get('acronym', '')
            
            if not name:  # Skip alliances without names
                continue
            
            # Calculate relevance score
            score = 0
            name_lower = name.lower()
            acronym_lower = acronym.lower() if acronym else ''
            
            # Exact matches get highest priority
            if query_lower == name_lower or query_lower == acronym_lower or query == alliance_id:
                score = 1000
            # Starts with match
            elif name_lower.startswith(query_lower) or acronym_lower.startswith(query_lower):
                score = 100
            # Contains match
            elif query_lower in name_lower or query_lower in acronym_lower:
                score = 50
            # ID partial match
            elif query in alliance_id:
                score = 25
            else:
                continue  # Skip non-matching
            
            results.append({
                'value': name,  # Used as the filter value
                'label': f"{name} [{acronym}]" if acronym else name,  # Display in autocomplete
                'id': alliance_id,
                'acronym': acronym or '',
                'score': score,
            })
        
        # Sort by score (desc) then by name (asc)
        results.sort(key=lambda x: (-x['score'], x['value'].lower()))
        results = results[:limit]
        
        # Remove score from response (internal use only)
        for result in results:
            del result['score']
        
        return jsonify(results), 200
        
    except Exception as e:
        logger.error(f"Error searching alliances: {e}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'message': 'Failed to search alliances.',
            'code': 'INTERNAL_ERROR'
        }), 500


def _calculate_days_inactive(last_active: str) -> int:
    """Calculate days since last activity."""
    if not last_active or last_active == '-0001-11-30 00:00:00':
        return 0
    
    try:
        # Parse the ISO format timestamp
        if 'T' in last_active:
            last_active_dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
        else:
            last_active_dt = datetime.strptime(last_active, "%Y-%m-%d %H:%M:%S")
            last_active_dt = last_active_dt.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        return (now - last_active_dt).days
    except (ValueError, TypeError):
        return 0
