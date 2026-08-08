import os
import redis
from typing import Optional

redis_client: Optional[redis.Redis] = None

try:
    REDIS_URL = os.getenv("REDIS_URL")
    if REDIS_URL:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        # Test connection
        redis_client.ping()
        print("✅ Redis connected successfully")
    else:
        print("⚠️  REDIS_URL not found. Caching disabled.")
except Exception as e:
    print(f"⚠️  Redis connection failed: {e}. Caching disabled.")
    redis_client = None

def get_redis_client() -> Optional[redis.Redis]:
    return redis_client
