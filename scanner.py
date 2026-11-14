import asyncio
import contextlib
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from enum import Enum
from functools import partial
from typing import Any, Callable, Optional

from dotenv import load_dotenv

from logic import queries
from core.logging_config import setup_logging
from database.sqlite_cache import (ensure_metadata_table, ensure_table_and_columns,
                                   get_alliances_db_path, get_nations_db_path,
                                   prune_missing_ids, set_metadata, upsert)
from infra.pnw_payloads import coerce_payload
from infra.pnw_subscriptions import PnwSubscription
from logic.api_client import call
from logic.common import _war_field, compute_beige_loot, normalize_alliance_position, parse_war_date
from logic.merge_utils import get_query
from logic.raids import derive_def_slots_and_time_since_war
from logic.revenue import get_cached_game_context, revenue_calc_sync

load_dotenv()
api_key = os.getenv("API_KEY")
if not api_key:
    raise RuntimeError("API_KEY is required for scanner")
call_api = partial(call, api_key=api_key)

setup_logging(process_name="scanner", level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Scanner retry/backoff constants (kept in-file by request).
SCAN_FETCH_MAX_ATTEMPTS = 5
SCAN_RETRY_BASE_SECONDS = 5
SCAN_RETRY_MAX_SECONDS = 120
# Minimum spacing between GraphQL page fetches: if a request already took >= this many
# seconds, do not add an extra delay; otherwise sleep only the remainder.
SCAN_PAGE_REQUEST_DELAY_SECONDS = 2


async def _sleep_remaining_page_delay(fetch_started_monotonic: float) -> None:
    elapsed = time.monotonic() - fetch_started_monotonic
    remainder = SCAN_PAGE_REQUEST_DELAY_SECONDS - elapsed
    if remainder > 0:
        await asyncio.sleep(remainder)
SCAN_NATION_FAILURE_BACKOFF_SECONDS = 30
# After per-page retries exhaust, skip to next page: backoff grows with consecutive skips; then abort.
SCAN_SKIP_BACKOFF_BASE_SECONDS = 30
SCAN_SKIP_BACKOFF_MAX_SECONDS = 600
SCAN_SKIP_MAX_CONSECUTIVE_PAGES = 15

# Serialize SQLite writes to nations.db when incremental + full scans overlap.
_nation_scan_write_lock = asyncio.Lock()

SUBSCRIPTION_BOOTSTRAP_BACKOFF_BASE_SECONDS = 2
SUBSCRIPTION_BOOTSTRAP_BACKOFF_MAX_SECONDS = 300
SUBSCRIPTION_HEARTBEAT_SECONDS = 60
SUBSCRIPTION_LOCK_RETRY_BACKOFF_SECONDS = (0.1, 0.25, 0.5)
SUBSCRIPTION_WRITE_FAILURE_THRESHOLD = 10
SUBSCRIPTION_WRITE_FAILURE_RATE_THRESHOLD = 0.2
SUBSCRIPTION_P95_PERSIST_WARN_MS = 500
SUBSCRIPTION_STALE_EVENT_WARN_SECONDS = 300
SUBSCRIPTION_MAX_RECONNECT_ATTEMPTS = 10
# A connection that lasted this long counts as healthy: the next failure starts the
# backoff over. Shorter ones keep growing it, so accept-then-close loops slow down.
SUBSCRIPTION_HEALTHY_SECONDS = 60
# Nation updates arrive constantly; this long without one means the stream is stuck
# (pings can keep a socket alive that no longer delivers events), so reconnect.
SUBSCRIPTION_IDLE_RECONNECT_SECONDS = 600
# Pusher close codes 4000-4099 mean "don't reconnect" (bad app key, over quota).
# The worker can't give up for good, so it retries at the longest backoff.
PUSHER_FATAL_CLOSE_CODES = range(4000, 4100)

MILITARY_RESEARCH_KEYS = (
    "ground_cost",
    "ground_capacity",
    "air_cost",
    "air_capacity",
    "naval_cost",
    "naval_capacity",
)
MILITARY_RESEARCH_DEFAULT = {key: 0 for key in MILITARY_RESEARCH_KEYS}


def _skip_backoff_seconds(consecutive_page_failures: int) -> float:
    return min(
        SCAN_SKIP_BACKOFF_BASE_SECONDS * consecutive_page_failures,
        SCAN_SKIP_BACKOFF_MAX_SECONDS,
    )


def _utc_ts() -> int:
    # time.time() is UTC epoch seconds; naive utcnow().timestamp() is read as local time.
    return round(time.time())


def _normalize_military_research(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, int] = {}
    for key in MILITARY_RESEARCH_KEYS:
        raw = value.get(key)
        if raw is None:
            normalized[key] = 0
            continue
        try:
            normalized[key] = int(raw)
        except (TypeError, ValueError):
            return None
    return normalized


def _row_nation_id(row: dict[str, Any]) -> int | None:
    try:
        return int(row["id"]) if row.get("id") is not None else None
    except (TypeError, ValueError):
        return None


def _merge_military_research(conn: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(row)
    incoming = _normalize_military_research(merged.get("military_research"))
    if incoming is not None:
        merged["military_research"] = incoming
        return merged

    existing = _normalize_military_research(
        _get_existing_json_column(conn, _row_nation_id(merged), "military_research")
    )
    merged["military_research"] = existing if existing is not None else dict(MILITARY_RESEARCH_DEFAULT)
    return merged


def _get_existing_json_column(
    conn: sqlite3.Connection,
    nation_id: int | None,
    column: str,
) -> Any | None:
    if nation_id is None:
        return None
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT {column} FROM nations WHERE id = ?", (nation_id,))
        row = cur.fetchone()
        if not row:
            return None
        current = row[0]
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except (json.JSONDecodeError, TypeError):
                return None
        return current
    except sqlite3.OperationalError:
        return None


def _wars_loot_signal(wars: Any) -> int:
    """Rough score for how useful a wars payload is for beige-loot computation."""
    if not isinstance(wars, list) or not wars:
        return 0
    score = len(wars)
    for war in wars:
        if not isinstance(war, dict):
            continue
        attacks = war.get("attacks") or []
        if not isinstance(attacks, list):
            continue
        for attack in attacks:
            if not isinstance(attack, dict):
                continue
            if attack.get("money_looted") is not None or attack.get("food_looted") is not None:
                score += 5
            if attack.get("type") is not None:
                score += 1
            if attack.get("loot_info"):
                score += 2
        if war.get("att_money_looted") is not None:
            score += 2
    return score


# Current GraphQL war field -> the deprecated name the scan query stores and readers
# (def slots, beige loot, nuke targets) look up first.
_WAR_FIELD_ALIASES = (
    ("att_id", "attid"),
    ("def_id", "defid"),
    ("turns_left", "turnsleft"),
    ("winner_id", "winner"),
)


def _with_scan_war_names(war: Any) -> Any:
    """Copy current-name war fields onto the deprecated names readers check first."""
    if not isinstance(war, dict):
        return war
    out = dict(war)
    for current, legacy in _WAR_FIELD_ALIASES:
        if out.get(current) is not None:
            out[legacy] = out[current]
    return out


def _war_keys(war: Any) -> list[tuple[Any, ...]]:
    """Keys that identify a war across payloads: its id, and attacker + defender + date.

    Either one matches, since wars cached before ids were queried have only the second.
    """
    if not isinstance(war, dict):
        return []
    keys: list[tuple[Any, ...]] = []
    if war.get("id") is not None:
        keys.append(("id", str(war["id"])))
    att_id = _war_field(war, "attid", "att_id")
    def_id = _war_field(war, "defid", "def_id")
    if att_id is not None and def_id is not None and war.get("date"):
        keys.append(("sides", str(att_id), str(def_id), parse_war_date(war["date"]).timestamp()))
    return keys


def _merge_attacks(existing: Any, incoming: Any) -> Any:
    """Attacks of one war: union by attack id, else the list with more loot data."""
    if not isinstance(incoming, list) or not incoming:
        return existing if isinstance(existing, list) and existing else incoming
    if not isinstance(existing, list) or not existing:
        return incoming
    if all(isinstance(a, dict) and a.get("id") is not None for a in existing + incoming):
        by_id = {str(a["id"]): a for a in existing}
        for attack in incoming:
            key = str(attack["id"])
            by_id[key] = {**by_id[key], **{k: v for k, v in attack.items() if v is not None}} if key in by_id else attack
        return sorted(by_id.values(), key=lambda a: _int_or_zero(a.get("id")))
    # Attacks without ids (rows scanned before ids were queried) can't be matched.
    return existing if _wars_loot_signal([{"attacks": existing}]) > _wars_loot_signal([{"attacks": incoming}]) else incoming


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _merge_war(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "attacks" or value is None:
            continue
        merged[key] = value
    if "attacks" in incoming or "attacks" in existing:
        merged["attacks"] = _merge_attacks(existing.get("attacks"), incoming.get("attacks"))
    return merged


def _merge_war_lists(existing: list[Any], incoming: list[Any]) -> list[Any]:
    """Incoming wars update the cached ones they match and add the new ones.

    Cached wars missing from the update are kept (an update may list active wars
    only); the next scan replaces the list with the current 14 days.
    """
    merged = list(existing)
    index: dict[tuple[Any, ...], int] = {}
    for i, war in enumerate(merged):
        for key in _war_keys(war):
            index.setdefault(key, i)
    for war in incoming:
        keys = _war_keys(war)
        match = next((index[key] for key in keys if key in index), None)
        if match is None:
            merged.append(war)
            match = len(merged) - 1
        else:
            merged[match] = _merge_war(merged[match], war)
        for key in keys:
            index.setdefault(key, match)
    return merged


def _merge_subscription_wars(conn: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
    """Merge a live update's ``wars`` into the cached ones instead of replacing them.

    Updates may carry no wars, an empty or null list, only active wars, or attacks
    without loot fields. Merging by war keeps the cached history (beige loot needs
    the last lost war) while new wars and fresh ``turnsleft`` values still land, so
    defensive slots stay right.
    """
    if "wars" not in row:
        return row

    merged = dict(row)
    incoming = merged.get("wars")
    existing = _get_existing_json_column(conn, _row_nation_id(merged), "wars")
    has_existing = isinstance(existing, list) and bool(existing)

    if isinstance(incoming, list) and incoming:
        incoming = [_with_scan_war_names(war) for war in incoming]
        if not has_existing:
            merged["wars"] = incoming
        elif all(_war_keys(war) for war in existing + incoming):
            merged["wars"] = _merge_war_lists(existing, incoming)
        else:
            # Wars that can't be matched: keep the list with more loot data, as before.
            merged["wars"] = existing if _wars_loot_signal(existing) > _wars_loot_signal(incoming) else incoming
        return merged

    if has_existing:
        merged["wars"] = existing
        return merged

    # Avoid overwriting stored wars with null/empty subscription snapshots.
    merged.pop("wars", None)
    return merged


def _drop_incomplete_relations(row: dict[str, Any]) -> dict[str, Any]:
    """Leave out nested data a live update carries only partly, so the cache keeps it.

    Every nation has at least one city, so an empty or short ``cities`` list is a
    partial snapshot; ``alliance: null`` for a nation that is in an alliance is too.
    """
    cleaned = dict(row)
    cities = cleaned.get("cities")
    if "cities" in cleaned:
        num_cities = _int_or_zero(cleaned.get("num_cities"))
        if not isinstance(cities, list) or not cities or len(cities) < num_cities:
            cleaned.pop("cities")
    if "alliance" in cleaned and cleaned["alliance"] is None and _int_or_zero(cleaned.get("alliance_id")):
        cleaned.pop("alliance")
    return cleaned


# Current GraphQL nation field -> deprecated name the scan stores and readers use,
# with how to convert the value. Keeps both columns current whichever path wrote last.
_NATION_FIELD_ALIASES: tuple[tuple[str, str, Callable[[Any], Any]], ...] = (
    # war_policy is the enum name ("TURTLE"); the scan's warpolicy is "Turtle".
    ("war_policy", "warpolicy", lambda value: str(value).capitalize()),
    ("vital_defense_system", "vds", bool),
    ("iron_dome", "irond", bool),
)


def _mirror_nation_field_names(row: dict[str, Any]) -> dict[str, Any]:
    mirrored = dict(row)
    for current, legacy, convert in _NATION_FIELD_ALIASES:
        value = mirrored.get(current)
        if value is not None and value != "" and current in row and legacy not in row:
            mirrored[legacy] = convert(value)
    return mirrored


PersistContext = tuple[dict[str, Any], tuple[Any, ...]]

# Matches get_cached_game_context's own cache TTL.
SUBSCRIPTION_PERSIST_CONTEXT_TTL_SECONDS = 600
SUBSCRIPTION_PERSIST_CONTEXT_RETRY_SECONDS = 60

_subscription_persist_context: PersistContext | None = None
_subscription_persist_context_at = float("-inf")  # monotonic time of the last good fetch
_subscription_persist_context_failed_at = float("-inf")
_subscription_persist_context_refresh: asyncio.Task | None = None


async def _fetch_persist_context() -> PersistContext:
    """``(prices, revenue_context)`` for precomputing loot and income; one price snapshot.

    ``revenue_context`` is ``(colors, prices, treasures, radiation, seasonal_mod)``.
    """
    colors, prices, treasures, radiation, seasonal_mod = await get_cached_game_context(
        call_api, get_query, queries
    )
    return prices, (colors, prices, treasures, radiation, seasonal_mod)


async def _refresh_subscription_persist_context() -> None:
    global _subscription_persist_context, _subscription_persist_context_at
    global _subscription_persist_context_failed_at
    try:
        context = await _fetch_persist_context()
    except Exception as exc:
        # Not cached: the next attempt comes after the retry delay.
        _subscription_persist_context_failed_at = time.monotonic()
        logger.warning("[nation-subscription] prices/revenue context unavailable: %s", exc)
        return
    _subscription_persist_context = context
    _subscription_persist_context_at = time.monotonic()


async def _get_subscription_persist_context() -> tuple[dict[str, Any] | None, tuple[Any, ...] | None]:
    """Prices and revenue context for subscription rows, without stalling the socket.

    Only the very first call waits for the fetch (the worker makes it before it
    connects). Later refreshes run in the background while the last good context
    keeps being used, so frames and pings are read while the API is slow; a failed
    fetch is retried after SUBSCRIPTION_PERSIST_CONTEXT_RETRY_SECONDS.
    """
    global _subscription_persist_context_refresh
    refresh = _subscription_persist_context_refresh
    running = (
        refresh is not None
        and not refresh.done()
        and refresh.get_loop() is asyncio.get_running_loop()
    )
    now = time.monotonic()
    stale = now - _subscription_persist_context_at >= SUBSCRIPTION_PERSIST_CONTEXT_TTL_SECONDS
    backing_off = now - _subscription_persist_context_failed_at < SUBSCRIPTION_PERSIST_CONTEXT_RETRY_SECONDS
    if stale and not running and not backing_off:
        if _subscription_persist_context is None and _subscription_persist_context_failed_at == float("-inf"):
            await _refresh_subscription_persist_context()
        else:
            _subscription_persist_context_refresh = asyncio.create_task(
                _refresh_subscription_persist_context()
            )
    if _subscription_persist_context is None:
        return None, None
    return _subscription_persist_context


def _to_json_safe(value: Any) -> Any:
    """Recursively coerce objects to JSON-serializable primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        # Prefer enum names for GraphQL enums (e.g. AttackType.VICTORY -> "VICTORY").
        # Using .value turns VICTORY into 14 and broke beige-loot detection.
        name = getattr(value, "name", None)
        if isinstance(name, str) and name and not name.startswith("_"):
            return name
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe(v) for v in value]

    for attr in ("model_dump", "dict", "to_dict"):
        fn = getattr(value, attr, None)
        if callable(fn):
            candidate = fn()
            if isinstance(candidate, dict):
                return _to_json_safe(candidate)

    if hasattr(value, "__dict__"):
        return {
            str(k): _to_json_safe(v)
            for k, v in vars(value).items()
            if not str(k).startswith("_")
        }
    return str(value)


async def persist_nation_row(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    source: str,
    prices: dict[str, Any] | None = None,
    revenue_context: tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    """Persist a nation row and precompute raids-table scalars when possible.

    ``revenue_context`` is ``(colors, prices, treasures, radiation, seasonal_mod)``
    from :func:`get_cached_game_context`. When set, stores ``monetary_net_num`` /
    ``net_cash_num`` so ``GET /api/raids`` never recomputes revenue on request.
    """
    nation_id = row.get("id")
    backoffs = (0.0,) if source != "subscription" else (0.0, *SUBSCRIPTION_LOCK_RETRY_BACKOFF_SECONDS)
    for attempt_idx, backoff in enumerate(backoffs, start=1):
        if backoff > 0:
            await asyncio.sleep(backoff)
        started = time.monotonic()
        try:
            async with _nation_scan_write_lock:
                working_row = _to_json_safe(_merge_military_research(conn, row))
                if source == "subscription":
                    working_row = _drop_incomplete_relations(working_row)
                    working_row = _merge_subscription_wars(conn, working_row)
                    working_row = _mirror_nation_field_names(working_row)
                if "alliance_position" in working_row:
                    working_row["alliance_position"] = normalize_alliance_position(
                        working_row["alliance_position"]
                    )

                # Raids API scalars — avoid parsing wars/cities/treasures on each request.
                # Each is derived only from data the row carries: the upsert leaves
                # columns it doesn't mention alone, so a partial update keeps them.
                if "wars" in working_row:
                    try:
                        def_slots, time_since_war = derive_def_slots_and_time_since_war(
                            working_row, datetime.now(timezone.utc)
                        )
                        working_row["def_slots"] = int(def_slots)
                        working_row["time_since_war"] = time_since_war
                    except Exception as exc:
                        logger.debug(
                            "[nation-%s] def_slots derivation failed nation_id=%s error=%s",
                            source,
                            nation_id,
                            exc,
                        )
                if "treasures" in working_row:
                    treasures = working_row.get("treasures") or []
                    working_row["treasure_count"] = len(treasures) if isinstance(treasures, list) else 0

                loot_computed = False
                income_computed = False
                effective_prices = prices
                cities = working_row.get("cities")
                if revenue_context and isinstance(cities, list) and cities:
                    colors, ctx_prices, treasures_ctx, radiation, seasonal_mod = revenue_context[:5]
                    if effective_prices is None:
                        effective_prices = ctx_prices
                    try:
                        # revenue_calc_sync writes pollution/commerce/... into each city;
                        # give it copies so they aren't stored in the cities blob.
                        revenue_result = revenue_calc_sync(
                            nation={**working_row, "cities": [dict(city) for city in cities]},
                            radiation=radiation or {},
                            treasures=treasures_ctx or [],
                            prices=ctx_prices or {},
                            colors=colors or {},
                            seasonal_mod=seasonal_mod or {},
                            include_spies=False,
                        ) or {}
                        if revenue_result.get("monetary_net_num") is not None:
                            working_row["monetary_net_num"] = int(
                                round(float(revenue_result["monetary_net_num"]))
                            )
                            income_computed = True
                        if revenue_result.get("net_cash_num") is not None:
                            working_row["net_cash_num"] = int(
                                round(float(revenue_result["net_cash_num"]))
                            )
                    except Exception as exc:
                        logger.debug(
                            "[nation-%s] revenue precompute failed nation_id=%s error=%s",
                            source,
                            nation_id,
                            exc,
                        )

                if effective_prices:
                    try:
                        loot = compute_beige_loot(working_row, effective_prices)
                        # The latest lost war decides the value, so a genuine $0 is
                        # stored too. None means that war has no loot data (an
                        # incomplete or null-padded snapshot) and keeps the old value.
                        if loot is not None:
                            working_row["nation_loot_value"] = loot
                            loot_computed = True
                    except Exception as exc:
                        logger.warning(
                            "[nation-%s] beige loot computation failed nation_id=%s error=%s",
                            source,
                            nation_id,
                            exc,
                        )
                # After all precomputed keys (incl. nation_loot_value) are attached —
                # ensure_table_and_columns only ALTERs for keys present on the row.
                ensure_table_and_columns(conn, "nations", working_row)
                upsert(conn, "nations", working_row)
            persist_ms = round((time.monotonic() - started) * 1000, 2)
            return {
                "success": True,
                "persist_ms": persist_ms,
                "fields_count": len(working_row),
                "loot_computed": loot_computed,
                "income_computed": income_computed,
                "attempt": attempt_idx,
            }
        except Exception as exc:
            # A failed statement or COMMIT leaves the transaction (and its lock) open;
            # without a rollback, other connections block on it and this row would be
            # committed later by the next write despite being reported as failed.
            _rollback(conn)
            locked = isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower()
            if locked and attempt_idx < len(backoffs):
                logger.warning(
                    "event=%s_event_persist_retry nation_id=%s attempt=%s backoff_s=%.2f error=%s",
                    source,
                    nation_id,
                    attempt_idx,
                    backoffs[attempt_idx],
                    exc,
                )
                continue
            logger.error(
                "event=%s_event_persist_failed nation_id=%s error_type=%s error=%s",
                source,
                nation_id,
                type(exc).__name__,
                exc,
            )
            return {"success": False, "error": exc, "attempt": attempt_idx}
    return {"success": False, "attempt": len(backoffs)}


def _rollback(conn: sqlite3.Connection) -> None:
    with contextlib.suppress(sqlite3.Error):
        conn.rollback()


async def _fetch_with_retry(
    query: str,
    *,
    scan_type: str,
    page: int,
    max_attempts: int = SCAN_FETCH_MAX_ATTEMPTS,
) -> dict[str, Any]:
    """Fetch a GraphQL payload with bounded retries and structured logging."""
    for attempt in range(1, max_attempts + 1):
        try:
            resp = await call_api(query)
            if not isinstance(resp, dict):
                raise TypeError(f"Unexpected response type: {type(resp)!r}")
            if resp.get("errors"):
                raise ValueError(f"GraphQL returned errors: {resp['errors']}")
            return resp
        # Everything call() raises is worth retrying: aiohttp/timeout errors, but also
        # PnWServerError (5xx, rate-limit waits used up) and its bare Exception for
        # error-only replies. CancelledError is a BaseException and still stops it.
        except Exception as exc:
            if attempt == max_attempts:
                logger.error(
                    "[%s-scan] giving up page=%s after attempts=%s error=%s",
                    scan_type,
                    page,
                    attempt,
                    exc,
                    exc_info=True,
                )
                raise
            wait_s = min(SCAN_RETRY_BASE_SECONDS * attempt, SCAN_RETRY_MAX_SECONDS)
            logger.warning(
                "[%s-scan] retrying page=%s attempt=%s/%s backoff_s=%s error=%s",
                scan_type,
                page,
                attempt,
                max_attempts,
                wait_s,
                exc,
            )
            await asyncio.sleep(wait_s)


def _build_nation_query(page: int, min_score: int | None, vmode: bool | None) -> str:
    params = [f"page:{page}", "first:70", "orderBy:{column:DATE order:ASC}"]
    if vmode is not None:
        params.append(f"vmode:{str(vmode).lower()}")
    if min_score is not None:
        params.append(f"min_score:{min_score}")
    param_str = " ".join(params)
    return f"{{nations({param_str}){{paginatorInfo{{hasMorePages}} data{get_query(queries.BACKGROUND_SCANNER)}}}}}"


async def _run_nation_scan(min_score: int | None, vmode: bool | None, prune: bool, metadata_key: str) -> None:
    series_start = time.time()
    logger.info(
        "[nation-scan] start min_score=%s vmode=%s prune=%s metadata_key=%s",
        min_score,
        vmode,
        prune,
        metadata_key,
    )
    conn = sqlite3.connect(get_nations_db_path())
    try:
        prices = None
        revenue_context = None
        try:
            # One snapshot for both beige loot and income.
            prices, revenue_context = await _fetch_persist_context()
            logger.info("[nation-scan] prices and revenue context ready for loot/income precompute")
        except Exception as exc:
            logger.warning("[nation-scan] prices/revenue context unavailable: %s", exc)

        fetched_ids: list[int] = []
        loot_computed = 0
        income_computed = 0
        rows_written = 0
        table_ready = False
        more_pages = True
        n = 1
        consecutive_page_failures = 0
        skipped_pages = 0
        while more_pages:
            iter_start = time.time()
            query = _build_nation_query(n, min_score=min_score, vmode=vmode)
            fetch_started = time.monotonic()
            try:
                resp = await _fetch_with_retry(query, scan_type="nation", page=n)
            except Exception:
                await _sleep_remaining_page_delay(fetch_started)
                logger.error("[nation-scan] page fetch failed page=%s", n, exc_info=True)
                consecutive_page_failures += 1
                skipped_pages += 1
                if consecutive_page_failures >= SCAN_SKIP_MAX_CONSECUTIVE_PAGES:
                    logger.error(
                        "[nation-scan] giving up after consecutive_page_failures=%s (max=%s)",
                        consecutive_page_failures,
                        SCAN_SKIP_MAX_CONSECUTIVE_PAGES,
                    )
                    raise
                skip_wait = _skip_backoff_seconds(consecutive_page_failures)
                logger.warning(
                    "[nation-scan] skipping to next page after failure page=%s "
                    "consecutive_failures=%s/%s skip_backoff_s=%s",
                    n,
                    consecutive_page_failures,
                    SCAN_SKIP_MAX_CONSECUTIVE_PAGES,
                    skip_wait,
                )
                await asyncio.sleep(skip_wait)
                n += 1
                continue

            await _sleep_remaining_page_delay(fetch_started)
            consecutive_page_failures = 0
            page_data = resp['data']['nations']['data']

            if page_data and not table_ready:
                async with _nation_scan_write_lock:
                    ensure_table_and_columns(conn, "nations", page_data[0])
                table_ready = True

            for row in page_data:
                result = await persist_nation_row(
                    conn,
                    row,
                    source="scan",
                    prices=prices,
                    revenue_context=revenue_context,
                )
                if result.get("success"):
                    rows_written += 1
                    if result.get("loot_computed"):
                        loot_computed += 1
                    if result.get("income_computed"):
                        income_computed += 1

            fetched_ids += [
                int(row.get('id')) for row in page_data if row.get('id') is not None
            ]

            more_pages = resp['data']['nations']['paginatorInfo']['hasMorePages']
            logger.debug(
                "[nation-scan] fetched and persisted page=%s rows_on_page=%s duration_s=%.2f",
                n,
                len(page_data),
                time.time() - iter_start,
            )
            n += 1

        async with _nation_scan_write_lock:
            if prune and skipped_pages:
                # Nations on skipped pages are missing from fetched_ids but still exist.
                logger.warning(
                    "[nation-scan] skipping prune because skipped_pages=%s", skipped_pages
                )
            elif prune and fetched_ids:
                # Offset pages shift when nations are deleted mid-scan, so a live nation
                # can be missed; keep anything another writer (incremental scan,
                # subscription) refreshed while this scan ran.
                prune_missing_ids(conn, 'nations', fetched_ids, written_before=int(series_start))
            elif prune:
                logger.warning("[nation-scan] skipping prune because no fetched nation ids were collected")

            ensure_metadata_table(conn)
            last_ts = round(time.time())
            set_metadata(conn, metadata_key, last_ts)
        logger.info(
            "[nation-scan] completed pages=%s rows_saved=%s loot_precomputed=%s income_precomputed=%s "
            "min_score=%s vmode=%s duration_min=%.2f",
            n - 1,
            rows_written,
            loot_computed,
            income_computed,
            min_score,
            vmode,
            (time.time() - series_start) / 60,
        )
    finally:
        conn.close()


async def periodic_full_nation_scan(interval_hours: int = 6) -> None:
    logger.info("[nation-full-scan] scheduler started interval_hours=%s", interval_hours)
    while True:
        try:
            await _run_nation_scan(min_score=None, vmode=None, prune=True, metadata_key='last_fetched_full')
        except Exception as exc:
            logger.error("[nation-full-scan] iteration failed: %s", exc, exc_info=True)
        await asyncio.sleep(interval_hours * 3600)

async def nation_scanner():
    logger.info("[nation-scan] scheduler started")
    while True:
        try:
            await _run_nation_scan(min_score=15, vmode=False, prune=False, metadata_key='last_fetched')
        except Exception as e:
            logger.error("[nation-scan] iteration failed: %s", e, exc_info=True)
            logger.warning(
                "[nation-scan] backing off after failure backoff_s=%s",
                SCAN_NATION_FAILURE_BACKOFF_SECONDS,
            )
            await asyncio.sleep(SCAN_NATION_FAILURE_BACKOFF_SECONDS)


def _record_metadata(conn: sqlite3.Connection, key: str) -> None:
    """Store a worker timestamp; a busy or broken database must not end the worker."""
    try:
        set_metadata(conn, key, _utc_ts())
    except sqlite3.Error as exc:
        _rollback(conn)
        logger.warning("event=subscription_metadata_write_failed key=%s error=%s", key, exc)


def _open_subscription_db() -> sqlite3.Connection:
    conn = sqlite3.connect(get_nations_db_path())
    try:
        ensure_metadata_table(conn)
    except sqlite3.Error as exc:
        _rollback(conn)
        logger.warning("event=subscription_metadata_table_failed error=%s", exc)
    return conn


class SubscriptionIdle(RuntimeError):
    """The socket stayed open but delivered no events for too long."""


async def _items_until_idle(subscription: PnwSubscription) -> Any:
    """Yield subscription items; raise SubscriptionIdle after a long silence."""
    items = subscription.items()
    try:
        while True:
            try:
                async with asyncio.timeout(SUBSCRIPTION_IDLE_RECONNECT_SECONDS):
                    item = await anext(items)
            except TimeoutError:
                raise SubscriptionIdle(
                    f"no subscription events for {SUBSCRIPTION_IDLE_RECONNECT_SECONDS}s"
                ) from None
            yield item
    finally:
        await items.aclose()


def _subscription_backoff_seconds(reconnect_attempt: int, close_code: Optional[int]) -> float:
    if close_code in PUSHER_FATAL_CLOSE_CODES:
        return SUBSCRIPTION_BOOTSTRAP_BACKOFF_MAX_SECONDS
    return min(
        SUBSCRIPTION_BOOTSTRAP_BACKOFF_BASE_SECONDS * (2 ** (reconnect_attempt - 1)),
        SUBSCRIPTION_BOOTSTRAP_BACKOFF_MAX_SECONDS,
    )


async def nation_subscription_worker() -> None:
    worker = "nation_subscription"
    model = "nation"
    subscribed_event = "update"
    worker_boot = time.monotonic()
    bootstrap_attempt = 0
    reconnect_attempt = 0
    p95_warn_streak = 0
    reconnects_1m = 0
    logger.info(
        "event=subscription_worker_start worker=%s model=%s events=%s pid=%s scanner_version=legacy",
        worker,
        model,
        subscribed_event,
        os.getpid(),
    )
    while True:
        bootstrap_attempt += 1
        window_started = time.monotonic()
        events_1m = 0
        writes_ok_1m = 0
        writes_failed_1m = 0
        persist_latencies_1m: list[float] = []
        last_event_monotonic = time.monotonic()
        events_processed = 0
        connected_at: Optional[float] = None
        backoff_s = 0.0
        conn: Optional[sqlite3.Connection] = None
        subscription = PnwSubscription(api_key, model, subscribed_event)
        try:
            conn = _open_subscription_db()
            # Load prices/revenue context before the socket opens, so the first events
            # don't wait on the API while frames go unread.
            await _get_subscription_persist_context()
            subscribe_started = time.monotonic()
            await subscription.connect()
            connected_at = time.monotonic()
            subscribe_latency_ms = round((connected_at - subscribe_started) * 1000)
            async with _nation_scan_write_lock:
                _record_metadata(conn, "last_subscription_reconnect_ts")
            logger.info(
                "event=subscription_worker_ready worker=%s model=%s event_type=%s channel=%s subscribe_latency_ms=%s",
                worker,
                model,
                subscribed_event,
                getattr(subscription, "channel", "unknown"),
                subscribe_latency_ms,
            )

            async for payload in _items_until_idle(subscription):
                now = time.monotonic()
                if now - window_started >= SUBSCRIPTION_HEARTBEAT_SECONDS:
                    last_event_age_s = round(now - last_event_monotonic, 2)
                    avg_persist = round(sum(persist_latencies_1m) / len(persist_latencies_1m), 2) if persist_latencies_1m else 0.0
                    p95_persist = 0.0
                    if persist_latencies_1m:
                        sorted_lat = sorted(persist_latencies_1m)
                        idx = min(len(sorted_lat) - 1, max(0, int(0.95 * len(sorted_lat)) - 1))
                        p95_persist = round(sorted_lat[idx], 2)
                    failure_rate = writes_failed_1m / max(1, events_1m)
                    logger.info(
                        "event=subscription_heartbeat worker=%s events_1m=%s writes_ok_1m=%s writes_failed_1m=%s reconnects_1m=%s last_event_age_s=%s avg_persist_ms_1m=%s p95_persist_ms_1m=%s scanner_lock_wait_ms_p95=0",
                        worker,
                        events_1m,
                        writes_ok_1m,
                        writes_failed_1m,
                        reconnects_1m,
                        last_event_age_s,
                        avg_persist,
                        p95_persist,
                    )
                    if last_event_age_s > SUBSCRIPTION_STALE_EVENT_WARN_SECONDS:
                        logger.warning(
                            "event=subscription_stream_stale worker=%s last_event_age_s=%s",
                            worker,
                            last_event_age_s,
                        )
                    if writes_failed_1m >= SUBSCRIPTION_WRITE_FAILURE_THRESHOLD or failure_rate > SUBSCRIPTION_WRITE_FAILURE_RATE_THRESHOLD:
                        logger.error(
                            "event=subscription_write_health_degraded worker=%s writes_failed_1m=%s failure_rate_1m=%.2f",
                            worker,
                            writes_failed_1m,
                            failure_rate,
                        )
                    if p95_persist > SUBSCRIPTION_P95_PERSIST_WARN_MS:
                        p95_warn_streak += 1
                        if p95_warn_streak >= 5:
                            logger.warning(
                                "event=subscription_latency_drift worker=%s p95_persist_ms_1m=%s consecutive_minutes=%s",
                                worker,
                                p95_persist,
                                p95_warn_streak,
                            )
                    else:
                        p95_warn_streak = 0
                    window_started = now
                    events_1m = writes_ok_1m = writes_failed_1m = reconnects_1m = 0
                    persist_latencies_1m.clear()

                try:
                    nation_row = coerce_payload(model, payload)
                except Exception as exc:
                    logger.warning(
                        "event=subscription_event_invalid worker=%s nation_id=unknown error_type=%s error=%s",
                        worker,
                        type(exc).__name__,
                        exc,
                    )
                    writes_failed_1m += 1
                    continue
                nation_id = nation_row.get("id")
                events_1m += 1
                events_processed += 1
                last_event_monotonic = now
                logger.debug(
                    "event=subscription_event_received worker=%s model=%s event=%s nation_id=%s received_ts=%s queue_depth=0",
                    worker,
                    model,
                    subscribed_event,
                    nation_id,
                    _utc_ts(),
                )
                async with _nation_scan_write_lock:
                    _record_metadata(conn, "last_subscription_event_ts")
                sub_prices, sub_revenue_context = await _get_subscription_persist_context()
                result = await persist_nation_row(
                    conn,
                    nation_row,
                    source="subscription",
                    prices=sub_prices,
                    revenue_context=sub_revenue_context,
                )
                if result.get("success"):
                    writes_ok_1m += 1
                    persist_ms = result.get("persist_ms", 0)
                    persist_latencies_1m.append(float(persist_ms))
                    logger.info(
                        "event=subscription_event_persisted worker=%s nation_id=%s persist_ms=%s fields_count=%s source=subscription",
                        worker,
                        nation_id,
                        persist_ms,
                        result.get("fields_count", 0),
                    )
                else:
                    writes_failed_1m += 1
        except Exception as exc:
            # A connection that ran for a while was healthy: start the backoff over.
            # One that failed or closed quickly keeps growing it.
            if connected_at is not None and time.monotonic() - connected_at >= SUBSCRIPTION_HEALTHY_SECONDS:
                reconnect_attempt = 0
            reconnect_attempt += 1
            reconnects_1m += 1
            close_code = getattr(exc, "close_code", None)
            backoff_s = _subscription_backoff_seconds(reconnect_attempt, close_code)
            if conn is not None:
                async with _nation_scan_write_lock:
                    _record_metadata(conn, "last_subscription_error_ts")
            if connected_at is None:
                event, level = "subscription_connect_failed", logging.ERROR
            elif reconnect_attempt == 1:
                # The usual end of a long-lived stream (server close, deploy, idle).
                event, level = "subscription_stream_closed", logging.WARNING
            else:
                event, level = "subscription_reconnect_failed", logging.ERROR
            logger.log(
                level,
                "event=%s worker=%s attempt=%s backoff_s=%s close_code=%s error_type=%s error=%s last_event_age_s=%s",
                event,
                worker,
                reconnect_attempt,
                backoff_s,
                close_code,
                type(exc).__name__,
                exc,
                round(time.monotonic() - last_event_monotonic, 2),
            )
            if reconnect_attempt == SUBSCRIPTION_MAX_RECONNECT_ATTEMPTS:
                logger.error(
                    "event=subscription_reconnects_failing worker=%s attempts=%s",
                    worker,
                    reconnect_attempt,
                )
        finally:
            # Release the socket, session and connection before any backoff.
            await subscription.close()
            if conn is not None:
                conn.close()
            logger.info(
                "event=subscription_worker_stop worker=%s reason=restart uptime_s=%s events_processed=%s",
                worker,
                round(time.monotonic() - worker_boot, 2),
                events_processed,
            )
        await asyncio.sleep(backoff_s)


async def alliance_scanner():
    logger.info("[alliance-scan] scheduler started interval_hours=1")
    while True:
        try:
            series_start = time.time()
            logger.info("[alliance-scan] start")
            conn = sqlite3.connect(get_alliances_db_path())
            try:
                more_pages = True
                n = 1
                fetched_ids = []
                rows_written = 0
                table_ready = False
                consecutive_page_failures = 0
                skipped_pages = 0
                while more_pages:
                    iter_start = time.time()
                    fetch_started = time.monotonic()
                    try:
                        resp = await _fetch_with_retry(
                            f"{{alliances(page:{n} first:100 orderBy:{{column:ID order:ASC}})"
                            f"{{paginatorInfo{{hasMorePages}} data{get_query(queries.ALLIANCE_SCANNER)}}}}}",
                            scan_type="alliance",
                            page=n,
                        )
                    except Exception:
                        await _sleep_remaining_page_delay(fetch_started)
                        logger.error("[alliance-scan] page fetch failed page=%s", n, exc_info=True)
                        consecutive_page_failures += 1
                        skipped_pages += 1
                        if consecutive_page_failures >= SCAN_SKIP_MAX_CONSECUTIVE_PAGES:
                            logger.error(
                                "[alliance-scan] giving up after consecutive_page_failures=%s (max=%s)",
                                consecutive_page_failures,
                                SCAN_SKIP_MAX_CONSECUTIVE_PAGES,
                            )
                            raise
                        skip_wait = _skip_backoff_seconds(consecutive_page_failures)
                        logger.warning(
                            "[alliance-scan] skipping to next page after failure page=%s "
                            "consecutive_failures=%s/%s skip_backoff_s=%s",
                            n,
                            consecutive_page_failures,
                            SCAN_SKIP_MAX_CONSECUTIVE_PAGES,
                            skip_wait,
                        )
                        await asyncio.sleep(skip_wait)
                        n += 1
                        continue

                    await _sleep_remaining_page_delay(fetch_started)
                    consecutive_page_failures = 0
                    page_data = resp['data']['alliances']['data']

                    if page_data and not table_ready:
                        ensure_table_and_columns(conn, 'alliances', page_data[0])
                        table_ready = True

                    for row in page_data:
                        ensure_table_and_columns(conn, 'alliances', row)
                        upsert(conn, 'alliances', row)
                        rows_written += 1

                    fetched_ids += [
                        int(a.get('id')) for a in page_data if a.get('id') is not None
                    ]
                    more_pages = resp['data']['alliances']['paginatorInfo']['hasMorePages']
                    logger.debug(
                        "[alliance-scan] fetched and persisted page=%s rows_on_page=%s duration_s=%.2f",
                        n,
                        len(page_data),
                        time.time() - iter_start,
                    )
                    n += 1

                if skipped_pages:
                    # Alliances on skipped pages are missing from fetched_ids but still exist.
                    logger.warning(
                        "[alliance-scan] skipping prune because skipped_pages=%s", skipped_pages
                    )
                elif fetched_ids:
                    prune_missing_ids(conn, 'alliances', fetched_ids)
                else:
                    logger.warning("[alliance-scan] skipping prune because no fetched alliance ids were collected")

                ensure_metadata_table(conn)
                last_ts = round(time.time())
                set_metadata(conn, 'last_fetched', last_ts)
                logger.info(
                    "[alliance-scan] completed pages=%s rows_saved=%s duration_min=%.2f",
                    n - 1,
                    rows_written,
                    (time.time() - series_start) / 60,
                )
            finally:
                conn.close()
        except Exception as e:  # pragma: no cover - defensive
            logger.error("[alliance-scan] iteration failed: %s", e, exc_info=True)
        await asyncio.sleep(3600)  # Run every hour

async def main():
    logger.info("[scanner] starting workers")
    try:
        await asyncio.gather(
            nation_scanner(),
            alliance_scanner(),
            periodic_full_nation_scan(),
            nation_subscription_worker(),
        )
    except Exception as e:
        logger.critical("[scanner] fatal unhandled error: %s", e, exc_info=True)

if __name__ == "__main__":
    # asyncio.run: get_event_loop() outside a running loop raises on Python 3.14.
    asyncio.run(main())
