"""
MongoDB connection setup using Motor (async driver).
We use a single shared client and expose collection accessors.
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME   = os.getenv("DB_NAME", "hrone_attendance")

# Created once at startup, reused for the entire app lifetime.
_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URL)
    return _client


def get_db():
    return get_client()[DB_NAME]


# Collection helpers – keeps collection names in one place
def attendance_col():
    return get_db()["attendance_logs"]


def employees_col():
    return get_db()["employees"]


async def close_client():
    global _client
    if _client:
        _client.close()
        _client = None
