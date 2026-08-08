import os
import redis
from typing import Optional
from rq import Queue
from rq.job import Job

redis_client: Optional[redis.Redis] = None
job_queue: Optional[Queue] = None

# Try to connect to Redis
try:
    REDIS_URL = os.getenv("REDIS_URL")
    if REDIS_URL:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        job_queue = Queue(connection=redis_client)
        print("✅ Background Job Queue initialized with Redis")
    else:
        print("⚠️  REDIS_URL not found. Background jobs will run synchronously.")
except Exception as e:
    print(f"⚠️  Redis connection failed: {e}. Background jobs will run synchronously.")
    redis_client = None
    job_queue = None

def get_job_queue() -> Optional[Queue]:
    return job_queue

def enqueue_job(func, *args, **kwargs):
    """
    Enqueues a job if Redis is available. 
    If not, runs the function immediately (synchronous fallback).
    """
    if job_queue:
        return job_queue.enqueue(func, *args, **kwargs)
    else:
        # Fallback: Run immediately
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Error running synchronous job: {e}")
            return None
