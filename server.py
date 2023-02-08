from flask import Flask
from threading import Thread
from mako.template import Template
from flask import request
import pathlib
import aiofiles
from datetime import datetime
import motor.motor_asyncio
import os
import asyncio
from motor.core import AgnosticClient
import logging
import utils

# to avoid "RuntimeError: Event loop is closed" error
AgnosticClient.get_io_loop = asyncio.get_running_loop

version = os.getenv("version")
async_client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("pymongolink"), serverSelectionTimeoutMS=5000)
async_mongo = async_client[str(version)]

logging.basicConfig(filename="logs.log", filemode='a', format='%(levelname)s %(asctime)s.%(msecs)d %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)
logger = logging.getLogger()

app = Flask('')

@app.route('/')
async def main():
    return "It lives!!"

@app.route('/raids/<int:user_id>', methods=['GET', 'POST'])
async def raids(user_id):
    try:
        # if POST
        if request.method == 'POST':
            data = request.json
            reminder = str(data['id'])
            await async_mongo.global_users.find_one_and_update({"user": int(data['invoker'])}, {"$push": {"beige_alerts": reminder}})
            return "you good"
        
        # otherwise GET    
        else:
            user = await utils.read_web("raids", user_id)
            if not user:
                logger.info(f"User {user_id} not found in raids endpoint")
                return "Whoa whoa whoa, calm down there chief! Something went wrong! It seems... I don't recognize this URL endpoint! Please go yell at RandomNoobster#0093."

            atck_ntn = user['atck_ntn']
            best_targets = user['best_targets']
            beige = user['beige']
            beige_alerts = (await async_mongo.global_users.find_one({"user": user_id}))['beige_alerts']
        
            async with aiofiles.open(pathlib.Path.cwd() / "templates" / "raidspage.txt", "r") as file:
                template = await file.read()

            return Template(template).render(attacker=atck_ntn, targets=best_targets, endpoint=user_id, invoker=str(user_id), beige_alerts=beige_alerts, beige=beige, datetime=datetime)
    except Exception as e:
        logger.error(e, exc_info=True)
        raise e

@app.route('/damage/<int:user_id>', methods=['GET'])
async def damage(user_id):
    try:
        data = await utils.read_web("damage", user_id)
        if not data:
            logger.info(f"User {user_id} not found in damage endpoint")
            return "Whoa whoa whoa, calm down there chief! Something went wrong! It seems... I don't recognize this URL endpoint! Please go yell at RandomNoobster#0093."

        async with aiofiles.open(pathlib.Path.cwd() / "templates" / "damage.txt", "r") as file:
            template = await file.read()
        
        results = data['results']

        return Template(template).render(results=results, weird_division=utils.weird_division)
    except Exception as e:
        logger.error(e, exc_info=True)
        raise e

@app.route('/builds/<int:user_id>', methods=['GET'])
async def builds(user_id):
    try:
        data = await utils.read_web("builds", user_id)
        if not data:
            logger.info(f"User {user_id} not found in builds endpoint")
            return "Whoa whoa whoa, calm down there chief! Something went wrong! It seems... I don't recognize this URL endpoint! Please go yell at RandomNoobster#0093."
        
        builds = data['builds']
        rss = data['rss']
        land = data['land']
        top_unique_builds = data['top_unique_builds']
        
        async with aiofiles.open(pathlib.Path.cwd() / "templates" / "buildspage.txt", "r", encoding='UTF-8') as file:
            template = await file.read()

        result = Template(template).render(builds=builds, rss=rss, land=land, unique_builds=top_unique_builds, datetime=datetime)
        return str(result)
    except Exception as e:
        logger.error(e, exc_info=True)
        raise e

@app.route('/attacksheet/<int:user_id>', methods=['GET'])
async def attacksheet(user_id):
    try:
        data = await utils.read_web("attacksheet", user_id)
        if not data:
            logger.info(f"User {user_id} not found in attacksheet endpoint")
            return "Whoa whoa whoa, calm down there chief! Something went wrong! It seems... I don't recognize this URL endpoint! Please go yell at RandomNoobster#0093."
        
        allies = data['allies']
        enemies = data['enemies']
        
        async with aiofiles.open(pathlib.Path.cwd() / "templates" / "attacksheet.txt", "r") as file:
            template = await file.read()

        result = Template(template).render(allies=allies, enemies=enemies, datetime=datetime, weird_division=utils.weird_division)
        return str(result)
    except Exception as e:
        logger.error(e, exc_info=True)
        raise e

async def run():
    Thread(target=lambda: app.run(host="0.0.0.0", port=5000)).start()