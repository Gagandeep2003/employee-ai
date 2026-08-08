"""
Background Job Queue System
Handles emails, notifications, analytics, webhooks, retries, and cleanup tasks
"""
import os
import json
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from rq import Queue, Worker
from rq.job import Job
from rq.registry import FailedJobRegistry
import redis

from services.cache_service import get_redis_client

logger = logging.getLogger(__name__)


class JobQueue:
    """Background job queue manager using RQ (Redis Queue)"""
    
    _instance: Optional['JobQueue'] = None
    _queue: Optional[Queue] = None
    _redis_conn: Optional[redis.Redis] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._queue is None:
            self._initialize_queue()
    
    def _initialize_queue(self):
        """Initialize Redis connection and Queue"""
        redis_client = get_redis_client()
        if not redis_client.is_available():
            logger.warning("Redis not available, jobs will run synchronously")
            self._redis_conn = None
            self._queue = None
            return
        
        self._redis_conn = redis_client.client
        
        # Create different queues for different priorities
        self._queue_high = Queue('high', connection=self._redis_conn)
        self._queue_default = Queue('default', connection=self._redis_conn)
        self._queue_low = Queue('low', connection=self._redis_conn)
        
        logger.info("Job queue initialized successfully")
    
    def enqueue(self, func: Callable, *args, priority: str = 'default', **kwargs) -> Optional[Job]:
        """
        Enqueue a job
        
        Args:
            func: Function to execute
            *args: Arguments to pass to function
            priority: 'high', 'default', or 'low'
            **kwargs: Keyword arguments to pass to function
            
        Returns:
            Job object or None if queue unavailable
        """
        if not self._redis_conn:
            # Run synchronously if Redis unavailable
            try:
                func(*args, **kwargs)
                return None
            except Exception as e:
                logger.error(f"Error running job synchronously: {e}")
                return None
        
        queue_map = {
            'high': self._queue_high,
            'default': self._queue_default,
            'low': self._queue_low
        }
        
        queue = queue_map.get(priority, self._queue_default)
        
        try:
            job = queue.enqueue(func, *args, **kwargs)
            logger.info(f"Job enqueued: {job.id}")
            return job
        except Exception as e:
            logger.error(f"Error enqueueing job: {e}")
            return None
    
    def enqueue_in(self, func: Callable, delay: int, *args, **kwargs) -> Optional[Job]:
        """
        Enqueue a job to run after a delay
        
        Args:
            func: Function to execute
            delay: Delay in seconds
            *args: Arguments to pass to function
            **kwargs: Keyword arguments to pass to function
        """
        if not self._redis_conn:
            return None
        
        try:
            job = self._queue_default.enqueue_in(
                timedelta(seconds=delay),
                func,
                *args,
                **kwargs
            )
            logger.info(f"Job scheduled for {delay}s later: {job.id}")
            return job
        except Exception as e:
            logger.error(f"Error scheduling job: {e}")
            return None
    
    def enqueue_at(self, func: Callable, scheduled_time: datetime, *args, **kwargs) -> Optional[Job]:
        """
        Enqueue a job to run at a specific time
        
        Args:
            func: Function to execute
            scheduled_time: When to run the job
            *args: Arguments to pass to function
            **kwargs: Keyword arguments to pass to function
        """
        if not self._redis_conn:
            return None
        
        delay = int((scheduled_time - datetime.utcnow()).total_seconds())
        if delay < 0:
            delay = 0
        
        return self.enqueue_in(func, delay, *args, **kwargs)
    
    def get_job_status(self, job_id: str) -> Optional[str]:
        """Get job status"""
        if not self._redis_conn:
            return None
        
        try:
            job = Job.fetch(job_id, connection=self._redis_conn)
            return job.get_status()
        except Exception as e:
            logger.error(f"Error getting job status: {e}")
            return None
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        if not self._redis_conn:
            return False
        
        try:
            job = Job.fetch(job_id, connection=self._redis_conn)
            job.cancel()
            return True
        except Exception as e:
            logger.error(f"Error cancelling job: {e}")
            return False
    
    def get_failed_jobs(self) -> list:
        """Get list of failed jobs"""
        if not self._redis_conn:
            return []
        
        try:
            registry = FailedJobRegistry(connection=self._redis_conn)
            return registry.get_job_ids()
        except Exception as e:
            logger.error(f"Error getting failed jobs: {e}")
            return []
    
    def retry_failed_job(self, job_id: str) -> Optional[Job]:
        """Retry a failed job"""
        if not self._redis_conn:
            return None
        
        try:
            job = Job.fetch(job_id, connection=self._redis_conn)
            return job.requeue()
        except Exception as e:
            logger.error(f"Error retrying job: {e}")
            return None
    
    def clear_queue(self, queue_name: str = 'default') -> bool:
        """Clear all jobs from a queue"""
        if not self._redis_conn:
            return False
        
        try:
            queue = Queue(queue_name, connection=self._redis_conn)
            queue.empty()
            return True
        except Exception as e:
            logger.error(f"Error clearing queue: {e}")
            return False
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        if not self._redis_conn:
            return {'available': False}
        
        try:
            stats = {}
            for name in ['high', 'default', 'low']:
                queue = Queue(name, connection=self._redis_conn)
                stats[name] = {
                    'count': queue.count,
                    'is_empty': queue.is_empty
                }
            
            # Get worker count
            workers = Worker.all(connection=self._redis_conn)
            stats['workers'] = len(workers)
            stats['available'] = True
            
            return stats
        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")
            return {'available': False, 'error': str(e)}


# Global instance
job_queue = JobQueue()


def get_job_queue() -> JobQueue:
    """Get job queue instance"""
    return job_queue


# Example job functions
def send_email_job(to: str, subject: str, body: str, html: bool = False):
    """Background job to send email"""
    from email_service import EmailService
    
    try:
        email_service = EmailService()
        result = email_service.send_email(to, subject, body, is_html=html)
        logger.info(f"Email sent to {to}: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        raise


def send_notification_job(user_id: str, title: str, message: str, notification_type: str = 'info'):
    """Background job to send notification"""
    from models import Notification
    from db import get_db
    
    try:
        db = next(get_db())
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=notification_type
        )
        db.add(notification)
        db.commit()
        logger.info(f"Notification created for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")
        db.rollback()
        raise


def process_webhook_job(webhook_url: str, payload: Dict, headers: Dict = None):
    """Background job to process webhook"""
    import httpx
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                webhook_url,
                json=payload,
                headers=headers or {}
            )
            response.raise_for_status()
            logger.info(f"Webhook sent to {webhook_url}")
            return True
    except Exception as e:
        logger.error(f"Failed to send webhook to {webhook_url}: {e}")
        raise


def cleanup_old_sessions_job():
    """Background job to cleanup old sessions"""
    from sessions import cleanup_old_sessions
    
    try:
        cleaned = cleanup_old_sessions()
        logger.info(f"Cleaned up {cleaned} old sessions")
        return cleaned
    except Exception as e:
        logger.error(f"Failed to cleanup sessions: {e}")
        raise


def process_analytics_job(business_id: str, event_type: str, data: Dict):
    """Background job to process analytics"""
    # Implementation depends on your analytics system
    logger.info(f"Processing analytics for business {business_id}: {event_type}")
    return True


def retry_failed_webhooks_job():
    """Background job to retry failed webhooks"""
    # Implementation for retrying failed webhooks
    logger.info("Retrying failed webhooks")
    return True
