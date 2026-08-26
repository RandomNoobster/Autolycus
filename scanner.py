import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from enum import Enum
from functools import partial
from typing import Any

import aiohttp
import pnwkit
from dotenv import load_dotenv

from logic import queries
from core.logging_config import setup_logging
from database.mongo import get_db
from database.sqlite_cache import (ensure_metadata_table, ensure_table_and_columns,
                                   get_alliances_db_path, get_nations_db_path,
                                   prune_missing_ids, set_metadata, upsert)
from logic.api_client import call
from logic.common import compute_beige_loot, normalize_alliance_position
from logic.merge_utils import get_query
from logic.raids import derive_def_slots_and_time_since_war
from logic.revenue import get_cached_game_context, revenue_calc_sync

load_dotenv()
api_key = os.getenv("API_KEY")
if not api_key:
    raise RuntimeError("API_KEY is required for scanner")
call_api = partial(call, api_key=api_key)

kit = pnwkit.QueryKit(api_key)

setup_logging(process_name="scanner", level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Shared DB layer handle (kept for consistency with app architecture).
# Scanner currently persists into SQLite cache and does not write Mongo directly.
db = get_db()

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
    return round(datetime.utcnow().timestamp())


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


def _get_existing_military_research(conn: sqlite3.Connection, nation_id: int | None) -> dict[str, int] | None:
    if nation_id is None:
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT military_research FROM nations WHERE id = ?", (nation_id,))
        row = cur.fetchone()
        if not row:
            return None
        current = row[0]
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except (json.JSONDecodeError, TypeError):
                return None
        return _normalize_military_research(current)
    except sqlite3.OperationalError:
        return None


def _merge_military_research(conn: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(row)
    nation_id = merged.get("id")
    try:
        nation_id_int = int(nation_id) if nation_id is not None else None
    except (TypeError, ValueError):
        nation_id_int = None

    incoming = _normalize_military_research(merged.get("military_research"))
    if incoming is not None:
        merged["military_research"] = incoming
        return merged

    existing = _get_existing_military_research(conn, nation_id_int)
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


def _merge_subscription_wars(conn: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
    """Keep cached war history when live subscription payloads omit or clear wars.

    Subscription snapshots sometimes include a non-empty but incomplete ``wars``
    list (active wars only, or attacks without loot fields). Prefer the richer
    cached payload so beige-loot history is not wiped on every nation update.
    """
    if "wars" not in row:
        return row

    merged = dict(row)
    incoming = merged.get("wars")

    try:
        nation_id_int = int(merged.get("id")) if merged.get("id") is not None else None
    except (TypeError, ValueError):
        nation_id_int = None

    existing = _get_existing_json_column(conn, nation_id_int, "wars")
    incoming_score = _wars_loot_signal(incoming)
    existing_score = _wars_loot_signal(existing)

    if isinstance(incoming, list) and incoming:
        if existing_score > incoming_score:
            merged["wars"] = existing
        return merged

    if isinstance(existing, list) and existing:
        merged["wars"] = existing
        return merged

    # Avoid overwriting stored wars with null/empty subscription snapshots.
    merged.pop("wars", None)
    return merged


_subscription_persist_context: tuple[Any, ...] | None = None
_subscription_persist_context_monotonic: float = 0.0
SUBSCRIPTION_PERSIST_CONTEXT_TTL_SECONDS = 3600


async def _get_subscription_persist_context() -> tuple[dict[str, Any] | None, tuple[Any, ...] | None]:
    """Cached prices + revenue context for subscription row precomputation."""
    global _subscription_persist_context, _subscription_persist_context_monotonic

    now = time.monotonic()
    if (
        _subscription_persist_context is not None
        and now - _subscription_persist_context_monotonic < SUBSCRIPTION_PERSIST_CONTEXT_TTL_SECONDS
    ):
        prices, revenue_context = _subscription_persist_context
        return prices, revenue_context

    prices: dict[str, Any] | None = None
    revenue_context: tuple[Any, ...] | None = None
    try:
        prices_query = get_query(queries.PRICES)
        prices_resp = await call_api(f"{{tradeprices(first:1){{data{prices_query}}}}}")
        prices = prices_resp["data"]["tradeprices"]["data"][0]
        prices["money"] = 1
    except Exception as exc:
        logger.debug("[nation-subscription] failed to fetch prices: %s", exc)

    try:
        colors, ctx_prices, treasures, radiation, seasonal_mod = await get_cached_game_context(
            call_api, get_query, queries
        )
        revenue_context = (colors, ctx_prices, treasures, radiation, seasonal_mod)
        if prices is None and isinstance(ctx_prices, dict):
            prices = ctx_prices
    except Exception as exc:
        logger.debug("[nation-subscription] revenue game context unavailable: %s", exc)

    _subscription_persist_context = (prices, revenue_context)
    _subscription_persist_context_monotonic = now
    return prices, revenue_context


def _to_plain_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    for attr in ("model_dump", "dict", "to_dict"):
        fn = getattr(payload, attr, None)
        if callable(fn):
            candidate = fn()
            if isinstance(candidate, dict):
                return candidate
    if hasattr(payload, "__dict__"):
        return {
            key: value
            for key, value in vars(payload).items()
            if not key.startswith("_")
        }
    raise TypeError(f"Unsupported subscription payload type: {type(payload)!r}")


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
                    working_row = _merge_subscription_wars(conn, working_row)
                if "alliance_position" in working_row:
                    working_row["alliance_position"] = normalize_alliance_position(
                        working_row["alliance_position"]
                    )

                # Raids API scalars — avoid parsing wars/cities/treasures on each request.
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
                treasures = working_row.get("treasures") or []
                working_row["treasure_count"] = len(treasures) if isinstance(treasures, list) else 0

                loot_computed = False
                income_computed = False
                effective_prices = prices
                if revenue_context and len(revenue_context) >= 5:
                    colors, ctx_prices, treasures_ctx, radiation, seasonal_mod = revenue_context[:5]
                    if effective_prices is None:
                        effective_prices = ctx_prices
                    try:
                        revenue_result = revenue_calc_sync(
                            nation=working_row,
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

                ensure_table_and_columns(conn, "nations", working_row)
                if effective_prices:
                    try:
                        loot = compute_beige_loot(working_row, effective_prices)
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
        except sqlite3.OperationalError as exc:
            locked = "locked" in str(exc).lower()
            if source == "subscription" and locked and attempt_idx < len(backoffs):
                logger.warning(
                    "event=subscription_event_persist_retry worker=nation_subscription nation_id=%s attempt=%s backoff_s=%.2f error=%s",
                    nation_id,
                    attempt_idx,
                    backoff,
                    exc,
                )
                continue
            logger.error(
                "event=subscription_event_persist_failed worker=nation_subscription nation_id=%s error_type=%s error=%s retry_in_s=0",
                nation_id,
                type(exc).__name__,
                exc,
            )
            return {"success": False, "error": exc, "attempt": attempt_idx}
        except Exception as exc:
            logger.error(
                "event=subscription_event_persist_failed worker=nation_subscription nation_id=%s error_type=%s error=%s retry_in_s=0",
                nation_id,
                type(exc).__name__,
                exc,
            )
            return {"success": False, "error": exc, "attempt": attempt_idx}


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
        except (
            aiohttp.ClientError,
            aiohttp.client_exceptions.ContentTypeError,
            asyncio.TimeoutError,
            TypeError,
            ValueError,
            KeyError,
        ) as exc:
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
            prices_query = get_query(queries.PRICES)
            prices_resp = await call_api(
                f"{{tradeprices(first:1){{data{prices_query}}}}}"
            )
            prices = prices_resp['data']['tradeprices']['data'][0]
            prices['money'] = 1
            logger.info("[nation-scan] fetched market prices for beige loot pre-computation")
        except Exception as exc:
            logger.warning("[nation-scan] failed to fetch prices for beige loot: %s", exc)

        try:
            colors, ctx_prices, treasures, radiation, seasonal_mod = await get_cached_game_context(
                call_api, get_query, queries
            )
            revenue_context = (colors, ctx_prices, treasures, radiation, seasonal_mod)
            if prices is None and isinstance(ctx_prices, dict):
                prices = ctx_prices
            logger.info("[nation-scan] revenue game context ready for income precompute")
        except Exception as exc:
            logger.warning("[nation-scan] revenue game context unavailable: %s", exc)

        fetched_ids: list[int] = []
        loot_computed = 0
        income_computed = 0
        rows_written = 0
        table_ready = False
        more_pages = True
        n = 1
        consecutive_page_failures = 0
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
            if prune and fetched_ids:
                prune_missing_ids(conn, 'nations', fetched_ids)
            elif prune:
                logger.warning("[nation-scan] skipping prune because no fetched nation ids were collected")

            ensure_metadata_table(conn)
            last_ts = round(datetime.utcnow().timestamp())
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


async def nation_subscription_worker() -> None:
    worker = "nation_subscription"
    model = "nation"
    subscribed_event = "update"
    worker_boot = time.monotonic()
    bootstrap_attempt = 0
    reconnect_attempt = 0
    p95_warn_streak = 0
    logger.info(
        "event=subscription_worker_start worker=%s model=%s events=%s pid=%s scanner_version=legacy",
        worker,
        model,
        subscribed_event,
        os.getpid(),
    )
    while True:
        bootstrap_attempt += 1
        conn = sqlite3.connect(get_nations_db_path())
        ensure_metadata_table(conn)
        window_started = time.monotonic()
        events_1m = 0
        writes_ok_1m = 0
        writes_failed_1m = 0
        reconnects_1m = 0
        persist_latencies_1m: list[float] = []
        last_event_monotonic = time.monotonic()
        events_processed = 0
        try:
            sub_kit = pnwkit.QueryKit(api_key)
            subscribe_started = time.monotonic()
            subscription = await sub_kit.subscribe(model, subscribed_event, {})
            subscribe_latency_ms = round((time.monotonic() - subscribe_started) * 1000)
            reconnect_attempt = 0
            async with _nation_scan_write_lock:
                set_metadata(conn, "last_subscription_reconnect_ts", _utc_ts())
            logger.info(
                "event=subscription_worker_ready worker=%s model=%s event_type=%s channel=%s subscribe_latency_ms=%s",
                worker,
                model,
                subscribed_event,
                getattr(subscription, "channel", "unknown"),
                subscribe_latency_ms,
            )

            async for payload in subscription:
                now = time.monotonic()
                if now - window_started >= SUBSCRIPTION_HEARTBEAT_SECONDS:
                    elapsed = max(1.0, now - window_started)
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
                    nation_row = _to_plain_dict(payload)
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
                    set_metadata(conn, "last_subscription_event_ts", _utc_ts())
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
            reconnect_attempt += 1
            reconnects_1m += 1
            async with _nation_scan_write_lock:
                set_metadata(conn, "last_subscription_error_ts", _utc_ts())
            backoff_s = min(
                SUBSCRIPTION_BOOTSTRAP_BACKOFF_BASE_SECONDS * (2 ** max(0, reconnect_attempt - 1)),
                SUBSCRIPTION_BOOTSTRAP_BACKOFF_MAX_SECONDS,
            )
            if reconnect_attempt == 1:
                logger.error(
                    "event=subscription_worker_start_failed worker=%s attempt=%s backoff_s=%s error_type=%s error=%s",
                    worker,
                    bootstrap_attempt,
                    backoff_s,
                    type(exc).__name__,
                    exc,
                )
            else:
                logger.error(
                    "event=subscription_reconnect_failed worker=%s attempt=%s backoff_s=%s error_type=%s error=%s",
                    worker,
                    reconnect_attempt,
                    backoff_s,
                    type(exc).__name__,
                    exc,
                )
            if reconnect_attempt > 0:
                logger.warning(
                    "event=subscription_reconnect_attempt worker=%s attempt=%s backoff_s=%s reason=%s last_event_age_s=%s",
                    worker,
                    reconnect_attempt,
                    backoff_s,
                    type(exc).__name__,
                    round(time.monotonic() - last_event_monotonic, 2),
                )
            if reconnect_attempt > SUBSCRIPTION_MAX_RECONNECT_ATTEMPTS:
                logger.error(
                    "event=subscription_worker_crashed worker=%s attempt=%s error_type=%s error=%s",
                    worker,
                    reconnect_attempt,
                    type(exc).__name__,
                    exc,
                )
            await asyncio.sleep(backoff_s)
            continue
        finally:
            conn.close()
            logger.info(
                "event=subscription_worker_stop worker=%s reason=restart uptime_s=%s events_processed=%s",
                worker,
                round(time.monotonic() - worker_boot, 2),
                events_processed,
            )


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

                if fetched_ids:
                    prune_missing_ids(conn, 'alliances', fetched_ids)
                else:
                    logger.warning("[alliance-scan] skipping prune because no fetched alliance ids were collected")

                ensure_metadata_table(conn)
                last_ts = round(datetime.utcnow().timestamp())
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
        f1 = asyncio.ensure_future(nation_scanner())
        f2 = asyncio.ensure_future(alliance_scanner())
        f3 = asyncio.ensure_future(periodic_full_nation_scan())
        f4 = asyncio.ensure_future(nation_subscription_worker())
        await asyncio.gather(f1, f2, f3, f4)
    except Exception as e:
        logger.critical("[scanner] fatal unhandled error: %s", e, exc_info=True)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())