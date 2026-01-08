"""
Raids API Routes

This module provides API endpoints for the raids feature, including
target listings and beige reminder functionality.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import motor.motor_asyncio
from flask import Blueprint, current_app, jsonify, request
from pymongo import MongoClient

import queries
from api.security import require_token
from logic import api_client, merge_utils
from logic.military import calculate_win_chance_raw
from logic.revenue import pre_revenue_calc, revenue_calc
from utils.db_utils import get_all_nations

logger = logging.getLogger(__name__)

raids_bp = Blueprint('raids', __name__, url_prefix='/api/raids')

# MongoDB connection (lazy initialization)
async_client = None
async_mongo = None
sync_client: Optional[MongoClient] = None
sync_db = None

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
        token_payload = getattr(request, 'token_payload', {}) or {}
        user_id = token_payload.get('user_id')

        # Parse filters
        min_cities = request.args.get('minCities', type=int)
        max_cities = request.args.get('maxCities', type=int)
        alliance_filter = request.args.get('alliance')
        beige_only = request.args.get('beige', default=None)
        max_wars = request.args.get('maxWars', type=int)
        inactive_min_days = request.args.get('inactiveMinDays', type=int)
        scope = request.args.get('scope')  # all | apps_or_none | no_alliance
        min_beige_loot = request.args.get('minBeigeLoot', type=int)
        performance_filter = request.args.get('performance', default=None)
        min_score = request.args.get('minScore', type=float)
        max_score = request.args.get('maxScore', type=float)
        if isinstance(beige_only, str):
            beige_only = beige_only.lower() in ('true', '1', 'yes')
        if isinstance(performance_filter, str):
            performance_filter = performance_filter.lower() in ('true', '1', 'yes')

        # Load nations from SQLite cache
        data_path = Path(current_app.root_path).parent / 'data' / 'nations.db'
        nations_data = get_all_nations(data_path)
        nations = nations_data['nations']
        last_fetched = nations_data.get('last_fetched')

        # Fetch user profile from Mongo (sync) to resolve attacker and reminders
        mongo_db = get_sync_mongo()
        user_profile = None
        if mongo_db is not None and user_id:
            try:
                user_profile = mongo_db.global_users.find_one({'user': int(user_id)})
            except Exception:
                user_profile = None

        attacker = None
        if user_profile:
            attacker_id = str(user_profile.get('id', ''))
            attacker = next((n for n in nations if str(n.get('id')) == attacker_id), None)
        if attacker is None and nations:
            attacker = nations[0]

        beige_alerts = user_profile.get('beige_alerts', []) if user_profile else []

        # Attempt to prepare revenue context (prices, treasures, radiation)
        revenue_context: Optional[tuple[Any, dict[str, float], dict[str, float], list[dict[str, Any]], dict[str, float], dict[str, float]]] = None
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
            except Exception as e:
                logger.warning(f"Revenue context unavailable: {e}")
                revenue_context = None

        targets = []
        for nation in nations:
            # Filters
            if scope == 'apps_or_none':
                if nation.get('alliance_position') not in ['NOALLIANCE', 'APPLICANT']:
                    continue
            if scope == 'no_alliance':
                if str(nation.get('alliance_id', '')) != '0':
                    continue
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
            if alliance_filter:
                name = (nation.get('alliance', {}) or {}).get('name', '')
                if alliance_filter.lower() not in name.lower():
                    continue
            if beige_only is True and nation.get('color') != 'beige':
                continue
            if beige_only is False and nation.get('color') == 'beige':
                continue

            # Defensive slots and war recency
            wars = nation.get('wars') or []
            def_slots = 0
            time_since_war: Any = "14+"
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
                        time_since_war = (datetime.now(timezone.utc) - dt).days
                    except Exception:
                        time_since_war = "Ongoing" if def_slots else "Unknown"
                else:
                    time_since_war = "Ongoing" if def_slots else "14+"

            # Inactivity
            days_inactive = _calculate_days_inactive(nation.get('last_active'))
            if inactive_min_days is not None and days_inactive < inactive_min_days:
                continue

            # Win chances
            if attacker:
                ground_attack = attacker.get('soldiers', 0) * 1.75 + attacker.get('tanks', 0) * 40
                ground_def = nation.get('soldiers', 0) * 1.75 + nation.get('tanks', 0) * 40 + nation.get('population', 0) * 0.0025
                air_attack = attacker.get('aircraft', 0) * 3
                air_def = nation.get('aircraft', 0) * 3
                naval_attack = attacker.get('ships', 0) * 4
                naval_def = nation.get('ships', 0) * 4
                ground_win = calculate_win_chance_raw(ground_attack, ground_def)
                air_win = calculate_win_chance_raw(air_attack, air_def)
                naval_win = calculate_win_chance_raw(naval_attack, naval_def)
                total_win = (ground_win + air_win + naval_win) / 3
            else:
                ground_win = air_win = naval_win = total_win = 0.5

            monetary_net_income = nation.get('monetary_net_num', 0)
            net_cash_income = nation.get('net_cash_num', 0)

            # Compute revenue if context is available
            if revenue_context:
                try:
                    _, colors, prices, treasures, radiation, seasonal_mod = revenue_context

                    async def _compute():
                        await revenue_calc(
                            message=None,
                            nation=nation,
                            radiation=radiation,
                            treasures=treasures,
                            prices=prices,
                            colors=colors,
                            seasonal_mod=seasonal_mod,
                            include_spies=False,
                        )

                    asyncio.run(_compute())
                    monetary_net_income = nation.get('monetary_net_num', monetary_net_income)
                    net_cash_income = nation.get('net_cash_num', net_cash_income)
                except Exception as e:
                    logger.debug(f"Revenue calc failed for nation {nation.get('id')}: {e}")
            nation_loot_value = 0
            try:
                nation_loot_value = int(nation.get('nation_loot_value', 0) or 0)
            except (TypeError, ValueError):
                nation_loot_value = 0

            if min_beige_loot is not None and nation_loot_value < min_beige_loot:
                continue

            if max_wars is not None and def_slots > max_wars:
                continue

            if performance_filter:
                if ground_win < 0.4 or nation_loot_value == 0 or net_cash_income < 10000:
                    continue

            targets.append({
                'id': int(nation.get('id', 0)),
                'nationName': nation.get('nation_name', 'Unknown'),
                'leaderName': nation.get('leader_name', 'Unknown'),
                'allianceId': str(nation.get('alliance_id', '0')),
                'allianceName': (nation.get('alliance', {}) or {}).get('name', 'None'),
                'alliancePosition': (nation.get('alliance_position') or 'Unknown'),
                'numCities': nation.get('num_cities', 0),
                'color': nation.get('color', ''),
                'beigeTurns': nation.get('beige_turns', 0),
                'nationLoot': str(nation_loot_value),
                'daysInactive': days_inactive,
                'monetaryNetIncome': monetary_net_income,
                'netCashIncome': net_cash_income,
                'taxable': bool(nation.get('color') == (nation.get('alliance', {}) or {}).get('color')),
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
            },
            'targets': targets,
            'beigeAlerts': [str(x) for x in beige_alerts],
            'showBeige': bool(beige_only),
            'generatedAt': datetime.fromtimestamp(last_fetched, tz=timezone.utc).isoformat() if last_fetched else datetime.now(timezone.utc).isoformat(),
        }

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
        Queries P&W API directly for real-time alliance data.
    """
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify([]), 200
        
        limit = int(request.args.get('limit', 10))
        limit = min(limit, 50)  # Cap at 50 results
        
        # Get API key from environment
        api_key = os.getenv('api_key')
        if not api_key:
            logger.error("P&W API key not configured")
            return jsonify({
                'error': 'Configuration error',
                'message': 'API key not configured.',
                'code': 'CONFIG_ERROR'
            }), 500
        
        # Query the P&W API for alliances
        # Per pnwSchema.graphql: alliances query supports filtering by name
        gql_query = """
        query {
          alliances(first: 100, orderBy: {column: SCORE, order: DESC}) {
            data {
              id
              name
              acronym
              score
            }
          }
        }
        """
        
        response = api_client.query_sync(gql_query, api_key)
        
        if not response or 'data' not in response or 'alliances' not in response['data']:
            logger.warning(f"No alliance data in API response: {response}")
            return jsonify([]), 200
        
        alliances = response['data']['alliances']['data']
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
        
    except ConnectionError as e:
        logger.error(f"API authentication error: {e}")
        return jsonify({
            'error': 'Authentication error',
            'message': 'Invalid API key.',
            'code': 'AUTH_ERROR'
        }), 500
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
