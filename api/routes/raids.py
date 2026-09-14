"""
Raids API Routes

Endpoints for raid target listings (SQLite cache), beige/VM reminders (Mongo),
and alliance search. Table-style filters (alliance, beige, wars, etc.) are handled
on the web client; GET / only applies score bounds and vacation-mode exclusion.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from flask import Blueprint, current_app, jsonify, request

from api.rate_limit import try_acquire_rate_limit
from api.security import optional_discord_session, require_discord_session, require_same_origin
from database.mongo import get_sync_db
from database.sqlite_cache import (get_all_alliances, get_all_nations_filtered,
                                   get_nation_by_id)
from logic import api_client
from logic.common import normalize_alliance_position
from logic.military import calculate_win_chance_raw
from logic.raids import (calculate_days_inactive,
                         is_in_vacation_mode)
from api.routes.reminder_views import delivery_view, test_dm_view, upcoming_by_nation
from database import reminders as reminder_db
from infra.webpush import get_push_sender
from logic import reminders as reminder_rules
from services import reminders as reminder_service

logger = logging.getLogger(__name__)

raids_bp = Blueprint('raids', __name__, url_prefix='/api/raids')

DEFAULT_REMINDER_MINUTES = list(reminder_rules.DEFAULT_REMINDER_OFFSETS)
MAX_REMINDER_OFFSETS = reminder_rules.MAX_REMINDER_OFFSETS
MAX_REMINDER_OFFSET_MINUTES = reminder_rules.MAX_REMINDER_OFFSET_MINUTES

# Scalar only — never pull cities/wars blobs on the request path.
# Income / def_slots / treasure_count are precomputed by the nation scanner (and a one-time backfill).
_RAIDS_SELECT_COLUMNS = [
    'id',
    'nation_name',
    'leader_name',
    'alliance_id',
    'alliance_position',
    'num_cities',
    'score',
    'color',
    'beige_turns',
    'nation_loot_value',
    'last_active',
    'soldiers',
    'tanks',
    'aircraft',
    'ships',
    'missiles',
    'nukes',
    'population',
    'vacation_mode_turns',
    '_created_at',
    'monetary_net_num',
    'net_cash_num',
    'def_slots',
    'time_since_war',
    'treasure_count',
]


def _error_response(error: str, message: str, code: str, status: int) -> tuple[Any, int]:
    return jsonify({'error': error, 'message': message, 'code': code}), status


def _parse_session_user_id() -> tuple[Optional[int], Optional[tuple[Any, int]]]:
    user_id = getattr(request, 'session_user_id', None)
    if not user_id:
        return None, _error_response(
            'Authentication required',
            'Missing user_id in token payload.',
            'TOKEN_MISSING',
            401,
        )
    try:
        return int(user_id), None
    except (TypeError, ValueError):
        return None, _error_response(
            'Invalid user id',
            'user_id must be numeric for reminders.',
            'INVALID_USER',
            400,
        )


def _normalize_nation_id(value: Any) -> Optional[str]:
    return reminder_rules.normalize_nation_id(value)


def _sanitize_reminder_offsets(raw_offsets: Any) -> Optional[list[int]]:
    return reminder_rules.sanitize_offsets(raw_offsets)


def _db_unavailable() -> tuple[Any, int]:
    return _error_response(
        'Database unavailable',
        'MongoDB is not configured.',
        'DB_UNAVAILABLE',
        503,
    )


def _reminder_state(mongo_db: Any, uid: int) -> dict[str, Any]:
    """Watch list, timings and delivery status for reminder responses (read-only)."""
    profile = reminder_db.get_profile_sync(mongo_db, uid) or {}
    return {
        'beigeAlerts': reminder_db.watched_nation_ids(profile),
        'beigeAlertConfig': reminder_rules.effective_offsets(profile.get('beige_alerts_config')),
        'delivery': delivery_view(mongo_db, uid, profile),
    }


@raids_bp.route('/', methods=['GET'])
@optional_discord_session
def get_raids() -> tuple[Any, int]:
    """
    List raid targets from the nations cache.

    Query parameters:
        attackerNationId: Attacker for win-chance calculations (optional)
        minScore, maxScore: Score window; min is clamped to >= 15
        vmode: false (default) excludes vacation-mode nations; true includes only VM

    Alliance, beige, scope, wars, inactivity, loot, and performance filters are
    not supported here — the raids page applies those in the browser.

    Income, defensive slots, and treasure counts are read from scanner-precomputed
    SQLite columns so this endpoint never re-parses cities/wars or runs revenue
    calculation on the request path.
    """
    try:
        req_start = time.perf_counter()
        user_id = getattr(request, 'session_user_id', None)

        attacker_nation_id = request.args.get('attackerNationId', type=int)
        req_min_score = request.args.get('minScore', type=float)
        min_score = 15 if req_min_score is None else max(15, float(req_min_score))
        max_score = request.args.get('maxScore', type=float)
        vmode_param = request.args.get('vmode', default='false')
        if isinstance(vmode_param, str):
            vmode_param = vmode_param.lower() in ('true', '1', 'yes')

        logger.info(
            "[raids] request start user=%s params: attackerNationId=%s minScore=%s maxScore=%s vmode=%s",
            user_id,
            attacker_nation_id,
            min_score,
            max_score,
            vmode_param,
        )

        data_path = Path(current_app.root_path).parent / 'data' / 'nations.db'
        load_t0 = time.perf_counter()
        nations_data = get_all_nations_filtered(
            data_path,
            min_score=min_score,
            max_score=max_score,
            columns=_RAIDS_SELECT_COLUMNS,
            # Only parse wars/treasures when precomputed columns are absent (handled per row).
            json_fields=set(),
        )
        nations = nations_data['nations']
        last_fetched = nations_data.get('last_fetched')
        load_ms = (time.perf_counter() - load_t0) * 1000

        # Build O(1) lookup dict for attacker resolution
        nations_by_id: dict[str, dict[str, Any]] = {
            str(n.get('id')): n for n in nations
        }
        logger.info(
            "[raids] loaded nations count=%d lastFetched=%s load_ms=%.0f",
            len(nations),
            last_fetched,
            load_ms,
        )

        # Load alliances (for alliance colors/name — avoids parsing nation.alliance JSON)
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
                # Match /api/auth/linked-nation: reminder-only stubs have no PnW nation id.
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
        # Priority: URL parameter > user profile > first nation in the filtered set
        if attacker_nation_id:
            attacker = nations_by_id.get(str(attacker_nation_id))
            if attacker is None:
                # Score-filtered nation slices omit attackers outside the war range —
                # look up by id before treating as missing.
                try:
                    attacker_data = get_nation_by_id(data_path, attacker_nation_id)
                    attacker = attacker_data.get('nation')
                except Exception:
                    attacker = None
            if attacker:
                logger.info(f"Found attacker nation by URL parameter: {attacker_nation_id}")
            else:
                requested_attacker_missing = True
                logger.warning(f"Nation {attacker_nation_id} not found in database")
        if attacker is None and user_profile:
            attacker_id = str(user_profile.get('id', ''))
            attacker = nations_by_id.get(attacker_id)
            if attacker is None and attacker_id:
                try:
                    attacker_data = get_nation_by_id(data_path, attacker_id)
                    attacker = attacker_data.get('nation')
                except Exception:
                    pass
        if attacker is None and nations:
            attacker = nations[0]
            logger.info(f"Falling back to first nation: {attacker.get('id')}")

        nation_warning = None
        if requested_attacker_missing:
            if attacker:
                fallback_id = attacker.get('id')
                fallback_name = attacker.get('nation_name') or f"Nation {fallback_id}"
                nation_warning = (
                    f"Nation ID {attacker_nation_id} not found in database. "
                    f"Using {fallback_name} (ID {fallback_id}) for calculations."
                )
            else:
                nation_warning = (
                    f"Nation ID {attacker_nation_id} not found in database. "
                    "No fallback nation available for calculations."
                )

        beige_alerts = user_profile.get('beige_alerts', []) if user_profile else []
        # Pre-compute set for O(1) membership checks in the loop
        beige_alert_set: set[str] = {str(x) for x in beige_alerts}

        targets: list[dict[str, Any]] = []

        # Pre-compute attacker combat values (constant across all targets)
        if attacker:
            _att_ground = attacker.get('soldiers', 0) * 1.75 + attacker.get('tanks', 0) * 40
            _att_air = attacker.get('aircraft', 0) * 3
            _att_naval = attacker.get('ships', 0) * 4
        # Compute current time once for all inactivity calculations
        now_utc = datetime.now(timezone.utc)

        loop_t0 = time.perf_counter()
        for nation in nations:
            alliance_position = normalize_alliance_position(nation.get('alliance_position'))
            in_vm = is_in_vacation_mode(nation)
            if vmode_param is False and in_vm:
                continue
            if vmode_param is True and not in_vm:
                continue

            alliance_id = str(nation.get('alliance_id', '') or '0')
            alliance_meta = alliances_by_id.get(alliance_id, {}) or {}

            # Prefer scanner-precomputed war fields; default when mid-scan / old rows.
            def_slots = nation.get('def_slots')
            time_since_war = nation.get('time_since_war')
            if def_slots is None:
                def_slots = 0
            if time_since_war is None:
                time_since_war = '14+'
            try:
                def_slots = int(def_slots)
            except (TypeError, ValueError):
                def_slots = 0

            days_inactive = calculate_days_inactive(nation.get('last_active'), now_utc)

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

            monetary_net_income = nation.get('monetary_net_num') or 0
            net_cash_income = nation.get('net_cash_num') or 0
            try:
                monetary_net_income = int(round(float(monetary_net_income)))
            except (TypeError, ValueError):
                monetary_net_income = 0
            try:
                net_cash_income = int(round(float(net_cash_income)))
            except (TypeError, ValueError):
                net_cash_income = 0

            nation_loot_value = 0
            try:
                nation_loot_value = int(nation.get('nation_loot_value', 0) or 0)
            except (TypeError, ValueError):
                nation_loot_value = 0

            treasure_count = nation.get('treasure_count')
            if treasure_count is None:
                treasure_count = 0
            try:
                treasure_count = int(treasure_count)
            except (TypeError, ValueError):
                treasure_count = 0

            alliance_color = alliance_meta.get('color')
            raw_alliance_name = alliance_meta.get('name')
            alliance_name = (
                str(raw_alliance_name).strip() if raw_alliance_name not in (None, '') else 'None'
            )
            nation_color = nation.get('color', '')
            taxable = bool(
                nation_color
                and alliance_color
                and str(nation_color).lower() == str(alliance_color).lower()
            )

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
                'alliancePosition': (alliance_position or 'Unknown'),
                'numCities': nation.get('num_cities', 0),
                'score': float(nation.get('score', 0) or 0),
                'color': nation_color,
                'beigeTurns': nation.get('beige_turns', 0),
                'nationLoot': f"${nation_loot_value:,}",
                'daysInactive': days_inactive,
                'monetaryNetIncome': monetary_net_income,
                'netCashIncome': net_cash_income,
                'taxable': taxable,
                'treasures': treasure_count,
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
        loop_ms = (time.perf_counter() - loop_t0) * 1000

        response = {
            'attacker': {
                'id': attacker.get('id') if attacker else None,
                'nation_name': attacker.get('nation_name') if attacker else None,
                'leader_name': attacker.get('leader_name') if attacker else None,
                'score': float(attacker.get('score', 0)) if attacker else None,
            },
            'targets': targets,
            'beigeAlerts': [str(x) for x in beige_alerts],
            'generatedAt': datetime.fromtimestamp(last_fetched, tz=timezone.utc).isoformat() if last_fetched else datetime.now(timezone.utc).isoformat(),
            'discordAuthenticated': user_id is not None,
            'discordLinked': discord_linked,
            'warning': nation_warning,
        }

        duration = time.perf_counter() - req_start
        logger.info(
            "[raids] request done nations=%d targets=%d load_ms=%.0f loop_ms=%.0f duration=%.2fs",
            len(nations),
            len(targets),
            load_ms,
            loop_ms,
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
@require_discord_session
@require_same_origin
def add_reminder() -> tuple[Any, int]:
    """
    Add a beige/VM exit reminder for a nation.

    Requires Discord session auth. Body: { "nationId": <number> }. A user's first
    reminder also queues a test DM when their DM delivery hasn't been confirmed.
    """
    try:
        uid, auth_error = _parse_session_user_id()
        if auth_error:
            return auth_error

        data = request.get_json(silent=True) or {}
        nation_id = _normalize_nation_id(data.get('nationId'))
        if nation_id is None:
            return _error_response(
                'Validation error',
                'nationId must be a numeric nation ID.',
                'VALIDATION_ERROR',
                400,
            )

        mongo_db = get_sync_db()
        if mongo_db is None:
            return _db_unavailable()

        result = reminder_service.add_reminder_sync(mongo_db, uid, nation_id)
        return jsonify({
            'success': True,
            'message': (
                'Reminder added successfully.'
                if result.added
                else 'You already have a reminder for this nation.'
            ),
            'nationId': int(nation_id),
            **_reminder_state(mongo_db, uid),
            'testDm': test_dm_view(result.test_dm),
        }), 200

    except Exception as e:
        logger.error(f"Error adding reminder: {e}", exc_info=True)
        return _error_response(
            'Internal server error',
            'Failed to set reminder.',
            'INTERNAL_ERROR',
            500,
        )


@raids_bp.route('/reminders/<nation_id>', methods=['DELETE'])
@require_discord_session
@require_same_origin
def remove_reminder(nation_id: str) -> tuple[Any, int]:
    """Remove a beige/VM exit reminder and cancel its scheduled messages."""
    try:
        uid, auth_error = _parse_session_user_id()
        if auth_error:
            return auth_error
        normalized_nation_id = _normalize_nation_id(nation_id)
        if normalized_nation_id is None:
            return _error_response(
                'Validation error',
                'nation_id must be numeric.',
                'VALIDATION_ERROR',
                400,
            )

        mongo_db = get_sync_db()
        if mongo_db is None:
            return _db_unavailable()

        reminder_service.remove_reminder_sync(mongo_db, uid, normalized_nation_id)
        return jsonify({
            'success': True,
            'message': 'Reminder removed successfully.',
            'nationId': int(normalized_nation_id),
            **_reminder_state(mongo_db, uid),
        }), 200

    except Exception as e:
        logger.error(f"Error removing reminder: {e}", exc_info=True)
        return _error_response(
            'Internal server error',
            'Failed to remove reminder.',
            'INTERNAL_ERROR',
            500,
        )


@raids_bp.route('/reminders', methods=['GET'])
@require_discord_session
def get_reminders() -> tuple[Any, int]:
    """List reminders with their exit and next reminder times, plus delivery status."""
    try:
        uid, auth_error = _parse_session_user_id()
        if auth_error:
            return auth_error

        mongo_db = get_sync_db()
        if mongo_db is None:
            return _db_unavailable()

        profile = reminder_db.get_profile_sync(mongo_db, uid) or {}
        reminder_ids = reminder_db.watched_nation_ids(profile)
        schedule = upcoming_by_nation(
            reminder_db.upcoming_jobs_for_user_sync(mongo_db, uid, reminder_rules.utcnow())
        )
        reminders: list[dict[str, Any]] = []
        data_path = Path(current_app.root_path).parent / 'data' / 'nations.db'

        for nation_id in reminder_ids:
            nation_data = get_nation_by_id(data_path, nation_id)
            nation = (nation_data.get('nation') if nation_data else None) or {}
            timing = schedule.get(nation_id, {})
            reminders.append({
                'nationId': int(nation_id),
                'nationName': nation.get('nation_name', f'Nation {nation_id}'),
                'leaderName': nation.get('leader_name', 'Unknown'),
                'beigeTurns': int(nation.get('beige_turns') or 0),
                'vacationModeTurns': int(nation.get('vacation_mode_turns') or 0),
                'exitAt': timing.get('exitAt'),
                'nextReminderAt': timing.get('nextReminderAt'),
            })

        reminders.sort(key=lambda x: x['nationId'])
        return jsonify({
            'success': True,
            'reminders': reminders,
            'beigeAlerts': reminder_ids,
            'beigeAlertConfig': reminder_rules.effective_offsets(profile.get('beige_alerts_config')),
            'delivery': delivery_view(mongo_db, uid, profile),
        }), 200
    except Exception as e:
        logger.error(f"Error fetching reminders: {e}", exc_info=True)
        return _error_response(
            'Internal server error',
            'Failed to fetch reminders.',
            'INTERNAL_ERROR',
            500,
        )


@raids_bp.route('/reminders/config', methods=['PUT'])
@require_discord_session
@require_same_origin
def update_reminder_config() -> tuple[Any, int]:
    try:
        uid, auth_error = _parse_session_user_id()
        if auth_error:
            return auth_error

        mongo_db = get_sync_db()
        if mongo_db is None:
            return _db_unavailable()

        data = request.get_json(silent=True) or {}
        offsets = _sanitize_reminder_offsets(data.get('beigeAlertConfig'))
        if offsets is None:
            return _error_response(
                'Validation error',
                (
                    f'beigeAlertConfig must be a list of 1-{MAX_REMINDER_OFFSETS} whole numbers '
                    f'between 1 and {MAX_REMINDER_OFFSET_MINUTES} (minutes).'
                ),
                'VALIDATION_ERROR',
                400,
            )

        reminder_db.set_offsets_sync(mongo_db, uid, offsets, reminder_rules.utcnow())
        profile = reminder_db.get_profile_sync(mongo_db, uid) or {}
        return jsonify({
            'success': True,
            'message': 'Reminder timing updated successfully.',
            'beigeAlertConfig': reminder_rules.effective_offsets(profile.get('beige_alerts_config')),
            'beigeAlerts': reminder_db.watched_nation_ids(profile),
        }), 200
    except Exception as e:
        logger.error(f"Error updating reminder config: {e}", exc_info=True)
        return _error_response(
            'Internal server error',
            'Failed to update reminder timing.',
            'INTERNAL_ERROR',
            500,
        )


@raids_bp.route('/reminders/channels', methods=['PUT'])
@require_discord_session
@require_same_origin
def update_reminder_channels() -> tuple[Any, int]:
    """Switch Discord DM and browser push delivery on or off. Body: {discordDm, webPush}."""
    try:
        uid, auth_error = _parse_session_user_id()
        if auth_error:
            return auth_error

        mongo_db = get_sync_db()
        if mongo_db is None:
            return _db_unavailable()

        data = request.get_json(silent=True) or {}
        discord_dm = data.get('discordDm')
        web_push = data.get('webPush')
        if not isinstance(discord_dm, bool) or not isinstance(web_push, bool):
            return _error_response(
                'Validation error',
                'discordDm and webPush must be true or false.',
                'VALIDATION_ERROR',
                400,
            )

        error = reminder_service.update_channels_sync(
            mongo_db,
            uid,
            discord_dm=discord_dm,
            web_push=web_push,
            push_configured=get_push_sender() is not None,
        )
        if error == reminder_rules.CHANNEL_REQUIRED:
            return _error_response(
                'Validation error',
                'Keep at least one delivery channel on.',
                error,
                400,
            )
        if error == reminder_rules.NO_PUSH_DEVICES:
            return _error_response(
                'No devices',
                'Turn on browser notifications on at least one device first.',
                error,
                409,
            )
        if error == reminder_rules.PUSH_NOT_CONFIGURED:
            return _error_response(
                'Push unavailable',
                'Browser notifications are not set up on this server.',
                error,
                503,
            )

        profile = reminder_db.get_profile_sync(mongo_db, uid) or {}
        return jsonify({
            'success': True,
            'message': 'Delivery settings updated.',
            'delivery': delivery_view(mongo_db, uid, profile),
        }), 200
    except Exception as e:
        logger.error(f"Error updating reminder channels: {e}", exc_info=True)
        return _error_response(
            'Internal server error',
            'Failed to update delivery settings.',
            'INTERNAL_ERROR',
            500,
        )


@raids_bp.route('/reminders/delivery', methods=['GET'])
@require_discord_session
def get_reminder_delivery() -> tuple[Any, int]:
    """Delivery status only (cheap enough for polling and the sidebar)."""
    try:
        uid, auth_error = _parse_session_user_id()
        if auth_error:
            return auth_error

        mongo_db = get_sync_db()
        if mongo_db is None:
            return _db_unavailable()

        profile = reminder_db.get_profile_sync(mongo_db, uid) or {}
        return jsonify({
            'success': True,
            'delivery': delivery_view(mongo_db, uid, profile),
        }), 200
    except Exception as e:
        logger.error(f"Error fetching reminder delivery: {e}", exc_info=True)
        return _error_response(
            'Internal server error',
            'Failed to fetch delivery status.',
            'INTERNAL_ERROR',
            500,
        )


@raids_bp.route('/reminders/test-dm', methods=['POST'])
@require_discord_session
@require_same_origin
def request_test_dm() -> tuple[Any, int]:
    """Queue a test DM so the user can check that reminders reach them."""
    try:
        uid, auth_error = _parse_session_user_id()
        if auth_error:
            return auth_error

        mongo_db = get_sync_db()
        if mongo_db is None:
            return _db_unavailable()

        now = reminder_rules.utcnow()
        latest = reminder_db.latest_test_dm_sync(mongo_db, uid)
        if latest and latest.get('state') in reminder_rules.TEST_DM_ACTIVE_STATES:
            test_dm = latest
        else:
            retry_after = reminder_service.test_dm_retry_after_sync(mongo_db, uid, now)
            if retry_after is not None:
                response = jsonify({
                    'error': 'Too many requests',
                    'message': f'You can send another test DM in {retry_after} seconds.',
                    'code': 'RATE_LIMITED',
                    'retryAfter': retry_after,
                })
                response.status_code = 429
                response.headers['Retry-After'] = str(retry_after)
                return response
            reminder_db.ensure_profile_sync(mongo_db, uid)
            test_dm, _ = reminder_db.create_test_dm_sync(
                mongo_db, uid, reminder_service.TEST_DM_SOURCE_WEBSITE, now
            )

        profile = reminder_db.get_profile_sync(mongo_db, uid) or {}
        return jsonify({
            'success': True,
            'message': 'Test DM on its way. It should arrive within a few seconds.',
            'testDm': test_dm_view(test_dm),
            'delivery': delivery_view(mongo_db, uid, profile),
        }), 202
    except Exception as e:
        logger.error(f"Error requesting test DM: {e}", exc_info=True)
        return _error_response(
            'Internal server error',
            'Failed to send a test DM.',
            'INTERNAL_ERROR',
            500,
        )


def _nation_score_from_sqlite(nation_id: int) -> tuple[Any, int] | None:
    """Return (response, status) from nations.db, or None if the nation is missing."""
    data_path = Path(current_app.root_path).parent / 'data' / 'nations.db'
    cached = get_nation_by_id(data_path, nation_id)
    nation = cached.get('nation')
    if not nation:
        return None

    last_fetched = cached.get('last_fetched')
    fetched_at = (
        datetime.fromtimestamp(last_fetched, tz=timezone.utc).isoformat()
        if last_fetched
        else datetime.now(timezone.utc).isoformat()
    )
    return jsonify({
        'id': int(nation.get('id')),
        'nationName': nation.get('nation_name'),
        'leaderName': nation.get('leader_name'),
        'score': float(nation.get('score') or 0),
        'source': 'cache',
        'fetchedAt': fetched_at,
    }), 200


@raids_bp.route('/nation/<int:nation_id>/live', methods=['GET'])
@optional_discord_session
def get_live_nation_score(nation_id: int) -> tuple[Any, int]:
    """
    Fetch a nation's current score, preferring the live Politics & War API.

    Any live-path problem (rate limit, missing key, network/API error, empty
    payload, response parse error) falls back to the SQLite nations cache.
    """
    nid = int(nation_id)

    api_key = current_app.config.get("API_KEY") or None
    try:
        live_allowed = bool(api_key) and try_acquire_rate_limit(
            10, 60, scope='raids-nation-live'
        )
    except Exception as exc:
        logger.warning(
            "[raids] live nation %s rate-limit check failed (%s); using sqlite",
            nid,
            exc,
        )
        live_allowed = False

    if live_allowed:
        try:
            query = (
                "{"
                f"nations(first:1 id:{nid})"
                "{data{id nation_name leader_name score}}"
                "}"
            )
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                response = loop.run_until_complete(api_client.call(query, api_key))
            finally:
                loop.close()
                asyncio.set_event_loop(None)

            nations = (
                (response or {}).get('data', {}).get('nations', {}).get('data', [])
                or []
            )
            if nations:
                nation = nations[0]
                return jsonify({
                    'id': int(nation.get('id')),
                    'nationName': nation.get('nation_name'),
                    'leaderName': nation.get('leader_name'),
                    'score': float(nation.get('score') or 0),
                    'source': 'live',
                    'fetchedAt': datetime.now(timezone.utc).isoformat(),
                }), 200
            logger.info(
                "[raids] live nation %s empty from PnW; falling back to sqlite",
                nid,
            )
        except Exception as exc:
            logger.warning(
                "[raids] live nation %s fetch failed (%s); falling back to sqlite",
                nid,
                exc,
            )
    elif api_key:
        logger.info(
            "[raids] live nation %s rate-limited; serving sqlite cache",
            nid,
        )

    try:
        cached = _nation_score_from_sqlite(nid)
        if cached is not None:
            return cached
        return _error_response(
            'Not found',
            f'Nation {nid} not found.',
            'NATION_NOT_FOUND',
            404,
        )
    except Exception as e:
        logger.error(f"Error in get_live_nation_score sqlite fallback: {e}", exc_info=True)
        return _error_response(
            'Internal server error',
            'An unexpected error occurred.',
            'INTERNAL_ERROR',
            500,
        )


@raids_bp.route('/alliances/search', methods=['GET'])
@optional_discord_session
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
