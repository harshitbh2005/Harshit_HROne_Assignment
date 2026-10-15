"""
database.py

Setting up the MongoDB connection using Motor (async pymongo wrapper).
Keeping the client as a module-level singleton - no point creating a new
connection for every request, that would be wasteful.

Motor docs: https://motor.readthedocs.io/en/stable/
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME   = os.getenv("DB_NAME", "hrone_attendance")

# single client for the whole app lifetime
_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URL)
    return _client


def get_db():
    return get_client()[DB_NAME]


# just shortcuts so I don't have to type get_db()["attendance_logs"] everywhere
def attendance_col():
    return get_db()["attendance_logs"]


def employees_col():
    return get_db()["employees"]


async def close_client():
    global _client
    if _client:
        _client.close()
        _client = None
