from motor.motor_asyncio import AsyncIOMotorClient

import config

client = AsyncIOMotorClient(config.MONGO_URL)
db = client[config.DB_NAME]
