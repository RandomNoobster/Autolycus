from datetime import datetime
import pathlib
import utils
import aiohttp
import time
import asyncio
import json
import queries
from dotenv import load_dotenv
import os
import logging

load_dotenv()
api_key = os.getenv("api_key")

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
                    await asyncio.sleep(1.2)
                    resp = await utils.call(f"{{nations(page:{n} first:100 vmode:false min_score:15 orderBy:{{column:DATE order:ASC}}){{paginatorInfo{{hasMorePages}} data{queries.BACKGROUND_SCANNER}}}}}", api_key)
                    new_nations['nations'] += resp['data']['nations']['data']
                    more_pages = resp['data']['nations']['paginatorInfo']['hasMorePages']
                except (aiohttp.client_exceptions.ContentTypeError, TypeError):
                    logger.info("Retrying fetch")
                    continue
                n += 1
                logger.debug(f"Fetched page {n}, took {time.time() - start:.2f} seconds")
            new_nations['last_fetched'] = round(datetime.utcnow().timestamp())
            with open(pathlib.Path.cwd() / 'nations.json', 'w') as json_file:
                json.dump(new_nations, json_file)
            logger.info(f"Done fetching nation data. {n} pages, took {(time.time() - series_start) / 60 :.2f} minutes")
        except Exception as e:
            logger.error(e, exc_info=True)

asyncio.run(nation_scanner())
