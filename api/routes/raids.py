"""
Raids API Routes

This module provides API endpoints for the raids feature, including
target listings and beige reminder functionality.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from flask import Blueprint, current_app, jsonify, request

from logic import queries
from api.security import optional_token, require_token
from database.mongo import get_sync_db
from database.sqlite_cache import (get_all_alliances, get_all_nations_filtered,
                                   get_nation_by_id)
from logic import api_client, merge_utils
from logic.common import compute_beige_loot
from logic.military import calculate_win_chance_raw
from logic.revenue import pre_revenue_calc, revenue_calc_sync
from services.raids_service import (calculate_days_inactive,
                                    derive_def_slots_and_time_since_war,
                                    is_in_vacation_mode)

logger = logging.getLogger(__name__)

raids_bp = Blueprint('raids', __name__, url_prefix='/api/raids')


@raids_bp.route('/', methods=['GET'])
@optional_token
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

        # Load nations from SQLite cache with SQL-level filtering
        data_path = Path(current_app.root_path).parent / 'data' / 'nations.db'
        # Push score and target-id filters down to SQLite for efficiency.
        # When specific target IDs are requested we filter by those;
        # otherwise apply the score floor (always >= 15).
        sql_min_score = None if target_nation_ids else min_score
        sql_max_score = None if target_nation_ids else max_score
        sql_nation_ids = target_nation_ids
        # Ensure the attacker (if known from URL param) is included in the
        # SQL filter so that the attacker data is always available for
        # win-chance calculations and the response header.
        if sql_nation_ids is not None and attacker_nation_id:
            sql_nation_ids = set(sql_nation_ids)  # copy to avoid mutating
            sql_nation_ids.add(str(attacker_nation_id))
        nations_data = get_all_nations_filtered(
            data_path,
            min_score=sql_min_score,
            max_score=sql_max_score,
            nation_ids=sql_nation_ids,
        )
        nations = nations_data['nations']
        last_fetched = nations_data.get('last_fetched')
        # Build O(1) lookup dict for attacker resolution
        nations_by_id: dict[str, dict[str, Any]] = {
            str(n.get('id')): n for n in nations
        }
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
        mongo_db = get_sync_db()
        user_profile = None
        discord_linked = False
        if mongo_db is not None and user_id is not None:
            try:
                uid = int(user_id)
                user_profile = mongo_db.global_users.find_one({'user': uid})
                discord_linked = user_profile is not None
            except (TypeError, ValueError):
                user_profile = None
                discord_linked = False

        if use_saved_targets and user_profile and not target_nation_ids:
            stored_ids = user_profile.get('raids_target_ids', [])
            if stored_ids:
                target_nation_ids = set([str(x) for x in stored_ids if str(x).isdigit()])

        attacker = None
        nation_warning = None
        # Priority: URL parameter > user profile > first nation
        if attacker_nation_id:
            attacker = nations_by_id.get(str(attacker_nation_id))
            if attacker:
                logger.info(f"Found attacker nation by URL parameter: {attacker_nation_id}")
            else:
                logger.warning(f"Nation {attacker_nation_id} not found in database")
                nation_warning = f"Nation ID {attacker_nation_id} not found in database. Using default nation for calculations."
        if attacker is None and user_profile:
            attacker_id = str(user_profile.get('id', ''))
            attacker = nations_by_id.get(attacker_id)
            # If the attacker isn't in the filtered set (e.g. target_nation_ids
            # was provided and didn't include the attacker), do a single lookup.
            if attacker is None and attacker_id:
                try:
                    attacker_data = get_nation_by_id(data_path, attacker_id)
                    attacker = attacker_data.get('nation')
                except Exception:
                    pass
        if attacker is None and nations:
            attacker = nations[0]
            logger.info(f"Falling back to first nation: {attacker.get('id')}")

        beige_alerts = user_profile.get('beige_alerts', []) if user_profile else []
        # Pre-compute set for O(1) membership checks in the loop
        beige_alert_set: set[str] = {str(x) for x in beige_alerts}

        targets: list[dict[str, Any]] = []
        backfill_attempts = 0
        backfill_successes = 0

        # Attempt to prepare revenue context (prices, treasures, radiation)
        revenue_context: Optional[tuple[Any, dict[str, float], dict[str, float], list[dict[str, Any]], dict[str, float], dict[str, float]]] = None
        prices: Optional[dict[str, float]] = None
        api_key = current_app.config.get("API_KEY") or None
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

        # Pre-compute attacker combat values (constant across all targets)
        if attacker:
            _att_ground = attacker.get('soldiers', 0) * 1.75 + attacker.get('tanks', 0) * 40
            _att_air = attacker.get('aircraft', 0) * 3
            _att_naval = attacker.get('ships', 0) * 4
        # Compute current time once for all inactivity calculations
        now_utc = datetime.now(timezone.utc)

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
                in_vm = is_in_vacation_mode(nation)
                if vmode_param is False and in_vm:
                    continue  # exclude VM nations by default
                if vmode_param is True and not in_vm:
                    continue  # include only VM nations when requested
                if min_cities is not None and nation.get('num_cities', 0) < min_cities:
                    continue
                if max_cities is not None and nation.get('num_cities', 0) > max_cities:
                    continue
                # NOTE: score filtering is now handled at the SQL level in
                # get_all_nations_filtered(), so no Python-side check needed.
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
            def_slots, time_since_war = derive_def_slots_and_time_since_war(nation, now_utc)

            # Inactivity
            days_inactive = calculate_days_inactive(nation.get('last_active'), now_utc)
            if apply_filters and inactive_min_days is not None and days_inactive < inactive_min_days:
                continue

            # Win chances (attacker values pre-computed above the loop)
            if attacker:
                ground_def = nation.get('soldiers', 0) * 1.75 + nation.get('tanks', 0) * 40 + nation.get('population', 0) * 0.0025
                air_def = nation.get('aircraft', 0) * 3
                naval_def = nation.get('ships', 0) * 4
                ground_win = round(calculate_win_chance_raw(_att_ground, ground_def) * 100, 1)
                air_win = round(calculate_win_chance_raw(_att_air, air_def) * 100, 1)
                naval_win = round(calculate_win_chance_raw(_att_naval, naval_def) * 100, 1)
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
            # (Scanner pre-computes this now, so backfill is a rare fallback)
            if nation_loot_value <= 0:
                backfill_attempts += 1
                computed_loot = compute_beige_loot(nation, prices)
                if computed_loot is not None:
                    nation_loot_value = computed_loot
                    backfill_successes += 1
            # Compute revenue if context is available (sync — no event loop overhead)
            if revenue_context:
                try:
                    _, colors, prices_ctx, treasures, radiation, seasonal_mod = revenue_context

                    revenue_result = revenue_calc_sync(
                        nation=nation,
                        radiation=radiation,
                        treasures=treasures,
                        prices=prices_ctx,
                        colors=colors,
                        seasonal_mod=seasonal_mod,
                        include_spies=False,
                    ) or {}
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

            updated_at = None
            try:
                updated_at = int(nation.get('_created_at')) if nation.get('_created_at') is not None else None
            except (TypeError, ValueError):
                updated_at = None
            if updated_at is None and last_fetched:
                try:
                    updated_at = int(last_fetched)
                except (TypeError, ValueError):
                    updated_at = None

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
                'hasReminderActive': str(nation.get('id')) in beige_alert_set,
                'updatedAt': updated_at,
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
            'discordLinked': discord_linked,
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

        mongo_db = get_sync_db()
        if mongo_db is None:
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

        mongo_db = get_sync_db()
        if mongo_db is None:
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
@optional_token
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
            name = str(alliance.get('name', ''))
            acronym = str(alliance.get('acronym', '') or '')
            
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
