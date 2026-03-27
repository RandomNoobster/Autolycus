import asyncio
import json
import logging
import os
import pathlib
import sqlite3
import time
from datetime import datetime
from functools import partial
from typing import Any

import aiohttp
import motor.motor_asyncio
import pnwkit
from dotenv import load_dotenv

import queries
from logic.api_client import call
from logic.common import compute_beige_loot
from logic.merge_utils import get_query
from utils.db_utils import (ensure_metadata_table, ensure_table_and_columns,
                            get_alliances_db_path, get_nations_db_path,
                            prune_missing_ids, row_to_db_values, set_metadata,
                            upsert)

load_dotenv()
version = os.getenv("version")
async_client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("pymongolink"), serverSelectionTimeoutMS=5000)
async_mongo = async_client[str(version)]
api_key = os.getenv("api_key")
call_api = partial(call, api_key=api_key)

kit = pnwkit.QueryKit(api_key)

logging.basicConfig(filename="logs.log", filemode='a', format='%(levelname)s %(asctime)s.%(msecs)d %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)
logger = logging.getLogger()


def _build_nation_query(page: int, min_score: int | None, vmode: bool | None) -> str:
    params = [f"page:{page}", "first:100", "orderBy:{column:DATE order:ASC}"]
    if vmode is not None:
        params.append(f"vmode:{str(vmode).lower()}")
    if min_score is not None:
        params.append(f"min_score:{min_score}")
    param_str = " ".join(params)
    return f"{{nations({param_str}){{paginatorInfo{{hasMorePages}} data{get_query(queries.BACKGROUND_SCANNER)}}}}}"


async def _run_nation_scan(min_score: int | None, vmode: bool | None, prune: bool, metadata_key: str) -> None:
    series_start = time.time()
    more_pages = True
    n = 1
    new_nations: dict[str, list[dict[str, Any]]] = {"nations": []}
    fetched_ids: list[int] = []
    while more_pages:
        start = time.time()
        try:
            await asyncio.sleep(2)
            query = _build_nation_query(n, min_score=min_score, vmode=vmode)
            resp = await call_api(query)
            page_data = resp['data']['nations']['data']
            new_nations['nations'] += page_data
            fetched_ids += [int(row.get('id')) for row in page_data if row.get('id') is not None]
            more_pages = resp['data']['nations']['paginatorInfo']['hasMorePages']
        except (aiohttp.client_exceptions.ContentTypeError, TypeError):
            logger.info("Retrying nation fetch")
            await asyncio.sleep(5)
            continue
        n += 1
        logger.debug(f"Fetched nation page {n}, took {time.time() - start:.2f} seconds")

    conn = sqlite3.connect(get_nations_db_path())
    try:
        nations = new_nations['nations']

        # Pre-compute beige loot values using current market prices.
        # Gracefully skip if prices are unavailable.
        prices = None
        try:
            prices_query = get_query(queries.PRICES)
            prices_resp = await call_api(
                f"{{tradeprices(first:1){{data{prices_query}}}}}"
            )
            prices = prices_resp['data']['tradeprices']['data'][0]
            prices['money'] = 1
            logger.info("Fetched prices for beige loot pre-computation")
        except Exception as exc:
            logger.warning(f"Failed to fetch prices for beige loot: {exc}")

        loot_computed = 0
        if nations:
            ensure_table_and_columns(conn, 'nations', nations[0])
            for row in nations:
                # Compute beige loot from war data before persisting
                if prices:
                    try:
                        loot = compute_beige_loot(row, prices)
                        if loot is not None:
                            row['nation_loot_value'] = loot
                            loot_computed += 1
                    except Exception:
                        pass  # Never let loot computation break the scan
                ensure_table_and_columns(conn, 'nations', row)
                upsert(conn, 'nations', row)

        if prune:
            prune_missing_ids(conn, 'nations', fetched_ids)

        ensure_metadata_table(conn)
        last_ts = round(datetime.utcnow().timestamp())
        set_metadata(conn, metadata_key, last_ts)
        logger.info(
            f"Done fetching nation data (vmode={vmode}, min_score={min_score}). {n} pages, "
            f"saved {len(nations)} rows to SQLite, pre-computed {loot_computed} beige loot values. "
            f"Took {(time.time() - series_start) / 60 :.2f} minutes"
        )
    finally:
        conn.close()


async def periodic_full_nation_scan(interval_hours: int = 6) -> None:
    while True:
        try:
            await _run_nation_scan(min_score=None, vmode=None, prune=True, metadata_key='last_fetched_full')
        except Exception as exc:
            logger.error(exc, exc_info=True)
        await asyncio.sleep(interval_hours * 3600)

async def nation_scanner():
    while True:
        try:
            await _run_nation_scan(min_score=15, vmode=False, prune=False, metadata_key='last_fetched')
        except Exception as e:
            logger.error(e, exc_info=True)


async def alliance_scanner():
    while True:
        try:
            series_start = time.time()
            more_pages = True
            n = 1
            new_alliances = {"alliances": []}
            fetched_ids = []
            while more_pages:
                start = time.time()
                try:
                    await asyncio.sleep(2)
                    resp = await call_api(
                        f"{{alliances(page:{n} first:100 orderBy:{{column:ID order:ASC}})"
                        f"{{paginatorInfo{{hasMorePages}} data{get_query(queries.ALLIANCE_SCANNER)}}}}}"
                    )
                    new_alliances['alliances'] += resp['data']['alliances']['data']
                    fetched_ids += [int(a.get('id')) for a in resp['data']['alliances']['data'] if a.get('id') is not None]
                    more_pages = resp['data']['alliances']['paginatorInfo']['hasMorePages']
                except (aiohttp.client_exceptions.ContentTypeError, TypeError):
                    logger.info("Retrying alliance fetch")
                    await asyncio.sleep(5)
                    continue
                n += 1
                logger.debug(f"Fetched alliance page {n}, took {time.time() - start:.2f} seconds")

            conn = sqlite3.connect(get_alliances_db_path())
            try:
                alliances = new_alliances['alliances']
                if alliances:
                    ensure_table_and_columns(conn, 'alliances', alliances[0])
                    for row in alliances:
                        ensure_table_and_columns(conn, 'alliances', row)
                        upsert(conn, 'alliances', row)

                # Prune stale alliances if we successfully fetched ids
                prune_missing_ids(conn, 'alliances', fetched_ids)

                ensure_metadata_table(conn)
                last_ts = round(datetime.utcnow().timestamp())
                set_metadata(conn, 'last_fetched', last_ts)
                logger.info(
                    f"Done fetching alliance data. {n} pages, saved {len(alliances)} rows to SQLite. "
                    f"Took {(time.time() - series_start) / 60 :.2f} minutes"
                )
            finally:
                conn.close()
        except Exception as e:  # pragma: no cover - defensive
            logger.error(e, exc_info=True)
        await asyncio.sleep(3600)  # Run every hour

async def main():
    try:
        f1 = asyncio.ensure_future(nation_scanner())
        f2 = asyncio.ensure_future(alliance_scanner())
        f3 = asyncio.ensure_future(periodic_full_nation_scan())
        await asyncio.gather(f1, f2, f3)
    except Exception as e:
        logger.critical(f"SCAWY ERROR in scanner.py: {e}", exc_info=True)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())