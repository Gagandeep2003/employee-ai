import os
import logging
from typing import Optional, Any, Dict
from datetime import datetime

# Try to import Redis and RQ, but fail gracefully if not installed/configured
try:
    import redis
    from rq import Queue, Worker, Job
    from rq.connections import Connection
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    Queue = None
    Worker = None
    Job = None
    Connection = None

logger = logging.getLogger("roviq-ai.jobs")

class SimpleJobQueue:
    """
    Fallback job queue that runs jobs synchronously if Redis is not available.
    """
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL")
        self._queue: Optional[Queue] = None
        self._redis_client: Optional[redis.Redis] = None
        
        if REDIS_AVAILABLE and self.redis_url:
            try:
                self._redis_client = redis.from_url(self.redis_url)
                self._queue = Queue(connection=self._redis_client)
                logger.info("Redis connected. Background jobs enabled.")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Running jobs synchronously.")
                self._queue = None
        else:
            if not REDIS_AVAILABLE:
                logger.warning("RQ library not installed. Running jobs synchronously.")
            else:
                logger.warning("REDIS_URL not found. Running jobs synchronously.")

    def enqueue(self, func: callable, *args, **kwargs) -> Optional[Any]:
        """
        Enqueue a job. If Redis is available, adds to queue. Otherwise, runs immediately.
        """
        if self._queue:
            try:
                return self._queue.enqueue(func, *args, **kwargs)
            except Exception as e:
                logger.error(f"Error enqueueing job: {e}. Running synchronously.")
                return func(*args, **kwargs)
        else:
            # Run synchronously
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error running synchronous job: {e}")
                raise

    def get_queue(self) -> Optional[Queue]:
        return self._queue

# Global instance
job_queue = SimpleJobQueue()

def get_job_queue() -> SimpleJobQueue:
    return job_queue

# --- Job Functions ---

def send_email_job(to_email: str, subject: str, body: str, html: bool = False):
    """
    Background job to send emails.
    Note: In a real app, this would call your email service directly.
    For now, it just logs the action to avoid circular imports with email_service.
    """
    logger.info(f"[Background Job] Sending email to {to_email}: {subject}")
    # Import here to avoid circular dependency if needed
    # from services.email_service import send_email
    # await send_email(...) 
    return {"status": "sent", "to": to_email}

def send_notification_job(notification_data: Dict[str, Any]):
    """
    Background job to send in-app notifications.
    If Redis is not configured, this runs synchronously or logs a warning.
    
    Args:
        notification_data: Dictionary containing recipient_id, title, message, type, etc.
    """
    logger.info(f"[Background Job] Processing notification for user: {notification_data.get('recipient_id')}")
    
    # In a full implementation, you would:
    # 1. Connect to DB
    # 2. Insert notification record
    # 3. Trigger websocket update if user is online
    
    # Placeholder logic for now to prevent crashes
    return {"status": "processed", "data": notification_data}

def cleanup_old_sessions_job():
    """
    Background job to clean up expired sessions or temporary data.
    """
    logger.info("[Background Job] Running session cleanup...")
    # Add cleanup logic here
    return {"status": "cleaned"}

def process_analytics_job(event_data: Dict[str, Any]):
    """
    Background job to process analytics events.
    """
    logger.info(f"[Background Job] Processing analytics event: {event_data.get('event_type')}")
    return {"status": "processed"}
