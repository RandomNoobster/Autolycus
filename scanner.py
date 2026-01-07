from datetime import datetime, timedelta
import pathlib
from utils import pw_utils as utils
import aiohttp
import time
import asyncio
import json
import queries
from dotenv import load_dotenv
import os
import logging
import motor.motor_asyncio
import pnwkit
import sqlite3
from utils.db_utils import (
    ensure_table_and_columns,
    row_to_db_values,
    upsert,
    ensure_metadata_table,
    set_metadata,
    get_nations_db_path,
)

load_dotenv()
version = os.getenv("version")
async_client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("pymongolink"), serverSelectionTimeoutMS=5000)
async_mongo = async_client[str(version)]
api_key = os.getenv("api_key")

kit = pnwkit.QueryKit(api_key)

logging.basicConfig(filename="logs.log", filemode='a', format='%(levelname)s %(asctime)s.%(msecs)d %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)
logger = logging.getLogger()

async def nation_scanner():
    while True:
        try:
            series_start = time.time()
            more_pages = True
            n = 1
            new_nations = {"last_fetched": None, "nations": []}
            while more_pages:
                start = time.time()
                try:
                    await asyncio.sleep(2)
                    resp = await utils.call(f"{{nations(page:{n} first:100 vmode:false min_score:15 orderBy:{{column:DATE order:ASC}}){{paginatorInfo{{hasMorePages}} data{utils.get_query(queries.BACKGROUND_SCANNER)}}}}}", api_key)
                    new_nations['nations'] += resp['data']['nations']['data']
                    more_pages = resp['data']['nations']['paginatorInfo']['hasMorePages']
                except (aiohttp.client_exceptions.ContentTypeError, TypeError):
                    logger.info("Retrying fetch")
                    await asyncio.sleep(5)
                    continue
                n += 1
                logger.debug(f"Fetched page {n}, took {time.time() - start:.2f} seconds")
            # Persist to SQLite database with dynamic schema
            conn = sqlite3.connect(get_nations_db_path())
            try:
                nations = new_nations['nations']
                if nations:
                    # Ensure nations table and columns based on first row; then broaden for all rows
                    ensure_table_and_columns(conn, 'nations', nations[0])
                    for row in nations:
                        # Add any newly encountered columns per row
                        ensure_table_and_columns(conn, 'nations', row)
                        upsert(conn, 'nations', row)

                # Store last_fetched in metadata table
                ensure_metadata_table(conn)
                last_ts = round(datetime.utcnow().timestamp())
                set_metadata(conn, 'last_fetched', last_ts)
                logger.info(f"Done fetching nation data. {n} pages, saved {len(nations)} rows to SQLite. Took {(time.time() - series_start) / 60 :.2f} minutes")
            finally:
                conn.close()
        except Exception as e:
            logger.error(e, exc_info=True)

async def main():
    while True:
        try:
            f1 = asyncio.ensure_future(nation_scanner())
            await asyncio.gather(f1)
        except Exception as e:
            logger.critical(f"SCAWY ERROR in scanner.py: {e}", exc_info=True)
        await asyncio.sleep(3600)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())