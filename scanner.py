from datetime import datetime, timedelta
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
import motor.motor_asyncio
import pnwkit

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
            new_nations['last_fetched'] = round(datetime.utcnow().timestamp())
            with open(pathlib.Path.cwd() / 'data' / 'nations.json', 'w') as json_file:
                json.dump(new_nations, json_file)
            logger.info(f"Done fetching nation data. {n} pages, took {(time.time() - series_start) / 60 :.2f} minutes")
        except Exception as e:
            logger.error(e, exc_info=True)

async def transaction_scanner() -> None:
    """
    Scans for transactions and updates the total balance of each nation. Is not applicable to alliance to alliance transactions.
    """

    guilds = await utils.listify(async_mongo.guild_configs.find({"transactions_api_keys": {"$exists": True, "$not": {"$size": 0}}}))

    async def update_guilds() -> None:
        nonlocal guilds
        while True:
            try:
                new_guilds = await utils.listify(async_mongo.guild_configs.find({"transactions_api_keys": {"$exists": True, "$not": {"$size": 0}}}))
                for new_guild in new_guilds:
                    found = False
                    exists = False
                    for old_guild in guilds:
                        if old_guild['guild_id'] == new_guild['guild_id']:
                            exists = True
                            if old_guild == new_guild: # if the guild is not in an equal state, we want to update it
                                found = True
                                break
                    if not found:
                        if exists:
                            guilds.remove(old_guild)
                        guilds.append(await update_keys(new_guild))
            except Exception as e:
                logger.error(e, exc_info=True)
            await asyncio.sleep(600)
    
    async def update_keys(guild) -> dict:
        for i, key_data in enumerate(guild['transactions_api_keys'].copy()):
            if isinstance(key_data, tuple):
                key = key_data[0]
            else:
                key = key_data
            await asyncio.sleep(10)
            # similar check in /config transactions
            try:
                res = (await utils.call(f"{{me{{nation{{alliance_id alliance_position_info{{withdraw_bank view_bank}}}}}}}}", key))['data']['me']['nation']
                alliance_id = res['alliance_id']
                if not res['alliance_position_info']['withdraw_bank'] or not res['alliance_position_info']['view_bank']:
                    logger.debug(f"Locally removing (0) key {key} from guild {guild['guild_id']} due to insufficient permissions")
                    guild['transactions_api_keys'].remove(key_data)
                else:
                    guild['transactions_api_keys'][i] = (key, alliance_id)
            except Exception as e:
                logger.debug(f"Locally removing (1) invalid key {key} from guild {guild['guild_id']}. Error: ", exc_info=True)
                guild['transactions_api_keys'].remove(key_data)
        return guild

    async def record(tx: dict, guild: dict) -> None:
        if await async_mongo.transactions.find_one({"id": str(tx['id']), "guild_id": guild['guild_id']}):
            return
        else:
            rss_tx = {}

            for note in guild['transactions_exempt_notes']:
                if note.strip() == "":
                    continue
                if note.lower() == tx['note'].lower():
                    return

            if str(tx['sender_type']) == "2": # if sender is alliance
                multiplier = -1
                if guild['transactions_subtract_beige_loot'] and "of the alliance bank inventory." in tx['note']:
                    nation_id = tx['banker_id']
                else:
                    nation_id = tx['receiver_id']
            elif str(tx['receiver_type']) == "2": # if receiver is alliance
                multiplier = 1
                nation_id = tx['sender_id']
            else:
                raise ValueError(f"no alliance in transaction {tx['id']}")
            
            for k,v in tx.items():
                if k in utils.RSS:
                    rss_tx[k] = float(v) * multiplier

            await async_mongo.balance.find_one_and_update({"nation_id": str(nation_id), "guild_id": guild['guild_id']}, {"$inc": rss_tx}, upsert=True)
            await async_mongo.transactions.insert_one({"id": str(tx['id']), "guild_id": guild['guild_id']})        

    async def subscriber(subscription: pnwkit.Subscription):
        nonlocal guilds
        while True:
            try:
                async for x in subscription:
                    x = vars(x)
                    for guild in guilds:
                        for key_data in guild['transactions_api_keys']:
                            if not isinstance(key_data, tuple):
                                logger.error(f"Key data is not a tuple (1): {key_data}")
                                continue
                            if str(x['receiver_id']) == key_data[1] and str(x['receiver_type']) == "2":
                                await record(x, guild)
                            elif str(x['sender_id']) == key_data[1] and str(x['sender_type']) == "2":
                                await record(x, guild)
            except Exception as e:
                logger.error(e, exc_info=True)
                await asyncio.sleep(60)

    asyncio.ensure_future(update_guilds())

    try:
        subscription = await kit.subscribe("bankrec", "create")
        asyncio.ensure_future(subscriber(subscription))
    except Exception as e:
        logger.error(e, exc_info=True)

    while True:
        try:
            done_alliances = []

            for i, guild in enumerate(guilds.copy()):
                try:
                    guild = await update_keys(guild)
                    guilds[i] = guild
                except IndexError as e:
                    continue

                for key_data in guild['transactions_api_keys']:
                    if not isinstance(key_data, tuple):
                        logger.error(f"Key data is not a tuple (2): {key_data}")
                        continue

                    if key_data[1] in done_alliances:
                        continue

                    api_query = f"{{alliances(id:{key_data[1]}){{data{utils.get_query(queries.TRANSACTIONS)}}}}}"
                    
                    try:
                        res = await utils.call(api_query, key_data[0])
                    except Exception as e:
                        if "Invalid API key" in str(e):
                            logger.debug(f"Locally removing (2) invalid key {key_data[0]} from guild {guild['guild_id']}")
                            guild['transactions_api_keys'].remove(key_data)
                        else:
                            logger.error(e, exc_info=True)
                            continue

                    if not (bankrecs := res['data']['alliances']['data'][0]['bankrecs']):
                        logger.warning(f"no bankrecs for alliance {key_data[1]}, {key_data[0]}")
                        bankrecs = []

                    if not (taxrecs := res['data']['alliances']['data'][0]['taxrecs']):
                        logger.warning(f"no taxrecs for alliance {key_data[1]}, {key_data[0]}")
                        taxrecs = []

                    if guild['transactions_track_taxes']:
                        all_recs = bankrecs + taxrecs
                    else:
                        all_recs = bankrecs
                    for tx in all_recs:
                        if tx["sender_type"] == 2 and tx["receiver_type"] == 2:
                            continue
                        if not guild['transactions_retroactive']:
                            if datetime.strptime(tx['date'], "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None) < guild['transactions_retroactive_date']:
                                continue
                        await record(tx, guild)

                    done_alliances.append(key_data[1])
                    await asyncio.sleep(10)
                   
            await asyncio.sleep(3600)

        except Exception as e:
            logger.error(e, exc_info=True)

async def main():
    while True:
        try:
            f1 = asyncio.ensure_future(nation_scanner())
            f2 = asyncio.ensure_future(transaction_scanner())
            await asyncio.gather(*[f1, f2])
        except Exception as e:
            logger.critical(f"SCAWY ERROR in scanner.py: {e}", exc_info=True)
        await asyncio.sleep(3600)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())