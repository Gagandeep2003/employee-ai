"""
Health Monitoring & Metrics System
Tracks API performance, database latency, Redis performance, AI response time,
cache hit rate, queue health, and system errors
"""
import os
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Singleton health monitoring service"""
    
    _instance: Optional['HealthMonitor'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.metrics = defaultdict(list)
            self.errors = []
            self.start_time = datetime.utcnow()
            self._initialized = True
    
    def record_metric(self, name: str, value: float, tags: Dict[str, str] = None):
        """Record a metric value"""
        self.metrics[name].append({
            'value': value,
            'timestamp': datetime.utcnow().isoformat(),
            'tags': tags or {}
        })
        # Keep only last 1000 values per metric
        if len(self.metrics[name]) > 1000:
            self.metrics[name] = self.metrics[name][-1000:]
    
    def record_error(self, error_type: str, message: str, context: Dict = None):
        """Record an error"""
        self.errors.append({
            'type': error_type,
            'message': message,
            'context': context or {},
            'timestamp': datetime.utcnow().isoformat()
        })
        # Keep only last 100 errors
        if len(self.errors) > 100:
            self.errors = self.errors[-100:]
        logger.error(f"{error_type}: {message}")
    
    def get_metric_avg(self, name: str, window_seconds: int = 300) -> Optional[float]:
        """Get average value for a metric within time window"""
        if name not in self.metrics:
            return None
        
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        values = [
            m['value'] for m in self.metrics[name]
            if datetime.fromisoformat(m['timestamp']) > cutoff
        ]
        
        return sum(values) / len(values) if values else None
    
    def get_metric_count(self, name: str, window_seconds: int = 300) -> int:
        """Get count of metric values within time window"""
        if name not in self.metrics:
            return 0
        
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        return sum(
            1 for m in self.metrics[name]
            if datetime.fromisoformat(m['timestamp']) > cutoff
        )
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        from services.cache_service import get_redis_client
        from db import db
        
        status = {
            'status': 'healthy',
            'uptime_seconds': (datetime.utcnow() - self.start_time).total_seconds(),
            'timestamp': datetime.utcnow().isoformat(),
            'components': {},
            'metrics': {},
            'recent_errors': self.errors[-10:]
        }
        
        # Check MongoDB
        try:
            start = time.time()
            asyncio.get_event_loop().run_until_complete(db.command('ping'))
            mongo_latency = (time.time() - start) * 1000
            status['components']['mongodb'] = {
                'status': 'healthy',
                'latency_ms': round(mongo_latency, 2)
            }
            self.record_metric('db.latency', mongo_latency, {'database': 'mongodb'})
        except Exception as e:
            status['components']['mongodb'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            status['status'] = 'degraded'
        
        # Check Redis
        redis_client = get_redis_client()
        if redis_client.is_available():
            try:
                start = time.time()
                redis_client.client.ping()
                redis_latency = (time.time() - start) * 1000
                status['components']['redis'] = {
                    'status': 'healthy',
                    'latency_ms': round(redis_latency, 2)
                }
                self.record_metric('redis.latency', redis_latency)
            except Exception as e:
                status['components']['redis'] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }
                status['status'] = 'degraded'
        else:
            status['components']['redis'] = {
                'status': 'unavailable'
            }
            status['status'] = 'degraded'
        
        # Calculate metrics
        avg_db_latency = self.get_metric_avg('db.latency')
        if avg_db_latency:
            status['metrics']['avg_db_latency_ms'] = round(avg_db_latency, 2)
        
        avg_redis_latency = self.get_metric_avg('redis.latency')
        if avg_redis_latency:
            status['metrics']['avg_redis_latency_ms'] = round(avg_redis_latency, 2)
        
        # Error rate
        error_count = self.get_metric_count('errors', window_seconds=60)
        status['metrics']['errors_per_minute'] = error_count
        
        if error_count > 10:
            status['status'] = 'unhealthy'
        
        return status
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Get detailed performance report"""
        return {
            'api_response_times': {
                'avg': self.get_metric_avg('api.response_time'),
                'p95': self._get_percentile('api.response_time', 95),
                'p99': self._get_percentile('api.response_time', 99),
            },
            'ai_response_times': {
                'avg': self.get_metric_avg('ai.response_time'),
                'p95': self._get_percentile('ai.response_time', 95),
            },
            'cache_hit_rate': self._calculate_cache_hit_rate(),
            'queue_stats': self._get_queue_stats(),
        }
    
    def _get_percentile(self, metric_name: str, percentile: int) -> Optional[float]:
        """Calculate percentile for a metric"""
        if metric_name not in self.metrics:
            return None
        
        values = sorted([m['value'] for m in self.metrics[metric_name]])
        if not values:
            return None
        
        index = int(len(values) * percentile / 100)
        return values[min(index, len(values) - 1)]
    
    def _calculate_cache_hit_rate(self) -> Optional[float]:
        """Calculate cache hit rate"""
        hits = self.get_metric_count('cache.hit')
        misses = self.get_metric_count('cache.miss')
        total = hits + misses
        
        if total == 0:
            return None
        
        return round(hits / total * 100, 2)
    
    def _get_queue_stats(self) -> Dict[str, Any]:
        """Get background job queue statistics"""
        from services.job_queue import get_job_queue
        
        try:
            queue = get_job_queue()
            return queue.get_queue_stats()
        except Exception as e:
            return {'error': str(e)}


# Global instance
health_monitor = HealthMonitor()


def get_health_monitor() -> HealthMonitor:
    """Get health monitor instance"""
    return health_monitor


# Context manager for timing operations
class TimingContext:
    """Context manager to record operation timing"""
    
    def __init__(self, metric_name: str, tags: Dict[str, str] = None):
        self.metric_name = metric_name
        self.tags = tags
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (time.time() - self.start_time) * 1000  # Convert to ms
        get_health_monitor().record_metric(self.metric_name, elapsed, self.tags)
        return False


def timed_operation(metric_name: str, tags: Dict[str, str] = None):
    """Decorator to time function execution"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            with TimingContext(metric_name, tags):
                return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            with TimingContext(metric_name, tags):
                return func(*args, **kwargs)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator
