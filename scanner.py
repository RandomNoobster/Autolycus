import asyncio
import logging
import os
import sqlite3
import time
from datetime import datetime
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
from logic.common import compute_beige_loot
from logic.merge_utils import get_query

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
SCAN_PAGE_REQUEST_DELAY_SECONDS = 2
SCAN_NATION_FAILURE_BACKOFF_SECONDS = 30

# Serialize SQLite writes to nations.db when incremental + full scans overlap.
_nation_scan_write_lock = asyncio.Lock()


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

        fetched_ids: list[int] = []
        loot_computed = 0
        rows_written = 0
        table_ready = False
        more_pages = True
        n = 1
        while more_pages:
            start = time.time()
            try:
                await asyncio.sleep(SCAN_PAGE_REQUEST_DELAY_SECONDS)
                query = _build_nation_query(n, min_score=min_score, vmode=vmode)
                resp = await _fetch_with_retry(query, scan_type="nation", page=n)
                page_data = resp['data']['nations']['data']
            except Exception:
                logger.error("[nation-scan] page fetch failed page=%s", n, exc_info=True)
                raise

            async with _nation_scan_write_lock:
                if page_data and not table_ready:
                    ensure_table_and_columns(conn, 'nations', page_data[0])
                    table_ready = True

                for row in page_data:
                    if prices:
                        try:
                            loot = compute_beige_loot(row, prices)
                            if loot is not None:
                                row['nation_loot_value'] = loot
                                loot_computed += 1
                        except Exception as exc:
                            logger.warning(
                                "[nation-scan] beige loot computation failed nation_id=%s error=%s",
                                row.get("id"),
                                exc,
                            )
                    ensure_table_and_columns(conn, 'nations', row)
                    upsert(conn, 'nations', row)
                    rows_written += 1

                fetched_ids += [
                    int(row.get('id')) for row in page_data if row.get('id') is not None
                ]

            more_pages = resp['data']['nations']['paginatorInfo']['hasMorePages']
            logger.debug(
                "[nation-scan] fetched and persisted page=%s rows_on_page=%s duration_s=%.2f",
                n,
                len(page_data),
                time.time() - start,
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
            "[nation-scan] completed pages=%s rows_saved=%s loot_precomputed=%s min_score=%s "
            "vmode=%s duration_min=%.2f",
            n - 1,
            rows_written,
            loot_computed,
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
                while more_pages:
                    start = time.time()
                    try:
                        await asyncio.sleep(SCAN_PAGE_REQUEST_DELAY_SECONDS)
                        resp = await _fetch_with_retry(
                            f"{{alliances(page:{n} first:100 orderBy:{{column:ID order:ASC}})"
                            f"{{paginatorInfo{{hasMorePages}} data{get_query(queries.ALLIANCE_SCANNER)}}}}}",
                            scan_type="alliance",
                            page=n,
                        )
                        page_data = resp['data']['alliances']['data']
                    except Exception:
                        logger.error("[alliance-scan] page fetch failed page=%s", n, exc_info=True)
                        raise

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
                        time.time() - start,
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
        await asyncio.gather(f1, f2, f3)
    except Exception as e:
        logger.critical("[scanner] fatal unhandled error: %s", e, exc_info=True)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())