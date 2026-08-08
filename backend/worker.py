"""
RQ Worker Entry Point
Run with: python worker.py
Or use: rq worker high default low --url redis://localhost:6379/0
"""
import os
import sys
import logging
from rq import Connection, Worker, Queue
import redis

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('worker')

def main():
    """Start RQ worker"""
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    try:
        redis_conn = redis.from_url(redis_url)
        redis_conn.ping()
        logger.info("Connected to Redis at %s", redis_url)
    except Exception as e:
        logger.error("Failed to connect to Redis: %s", e)
        logger.warning("Starting worker without Redis - jobs will run synchronously")
        return
    
    # Listen on all queues
    queues = ['high', 'default', 'low']
    
    logger.info("Starting worker, listening on queues: %s", ', '.join(queues))
    
    with Connection(redis_conn):
        workers = Worker(queues)
        workers.work(logging_level=logging.INFO)

if __name__ == '__main__':
    main()
