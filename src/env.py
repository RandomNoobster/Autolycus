from __future__ import annotations
import os
import pymongo
import motor.motor_asyncio


__all__ = (
    "ASYNC_MONGO",
    "SYNC_MONGO",
    "BOT_KEY",
    "API_KEY",
    "BOT_TOKEN",
    "IP",
    "DEBUG_CHANNEL",
)

print("env.py was run (maybe bad)")

pymongolink = os.environ["pymongolink"]
sync_client = pymongo.MongoClient(pymongolink)
version = os.environ["version"]
async_client = motor.motor_asyncio.AsyncIOMotorClient(pymongolink, serverSelectionTimeoutMS=5000)

ASYNC_MONGO = async_client[version]
SYNC_MONGO = sync_client[version]
BOT_KEY = os.environ["bot_key"]
API_KEY = os.environ["api_key"]
BOT_TOKEN = os.environ["bot_token"]
IP = os.environ["ip"]
DEBUG_CHANNEL = os.environ["debug_channel"]