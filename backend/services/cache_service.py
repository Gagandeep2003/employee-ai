"""
Redis Configuration and Connection Pool
Handles business rules, conversation cache, and AI response cache
"""
import os
import json
import redis
from typing import Optional, Any, Dict, List
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class RedisClient:
    """Singleton Redis client with connection pooling"""
    
    _instance: Optional['RedisClient'] = None
    _client: Optional[redis.Redis] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Redis connection with pool"""
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        
        try:
            self._client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            # Test connection
            self._client.ping()
            logger.info("Redis connection established successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._client = None
    
    @property
    def client(self) -> Optional[redis.Redis]:
        return self._client
    
    def is_available(self) -> bool:
        """Check if Redis is available"""
        if self._client is None:
            return False
        try:
            self._client.ping()
            return True
        except:
            return False
    
    # Business Rules Cache
    def get_business_rules(self, business_id: str) -> Optional[Dict]:
        """Get business rules from cache"""
        if not self._client:
            return None
        try:
            data = self._client.get(f"business:{business_id}:rules")
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Error getting business rules: {e}")
            return None
    
    def set_business_rules(self, business_id: str, rules: Dict, ttl: int = 3600):
        """Cache business rules"""
        if not self._client:
            return
        try:
            self._client.setex(
                f"business:{business_id}:rules",
                ttl,
                json.dumps(rules)
            )
        except Exception as e:
            logger.error(f"Error setting business rules: {e}")
    
    def invalidate_business_rules(self, business_id: str):
        """Invalidate business rules cache"""
        if not self._client:
            return
        try:
            self._client.delete(f"business:{business_id}:rules")
        except Exception as e:
            logger.error(f"Error invalidating business rules: {e}")
    
    # Conversation Cache
    def get_conversation_history(self, session_id: str, limit: int = 20) -> List[Dict]:
        """Get recent conversation history from cache"""
        if not self._client:
            return []
        try:
            messages = self._client.lrange(f"session:{session_id}:messages", 0, limit - 1)
            return [json.loads(msg) for msg in messages]
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    def add_to_conversation(self, session_id: str, message: Dict, ttl: int = 1800):
        """Add message to conversation cache"""
        if not self._client:
            return
        try:
            self._client.lpush(f"session:{session_id}:messages", json.dumps(message))
            self._client.ltrim(f"session:{session_id}:messages", 0, 49)  # Keep last 50 messages
            self._client.expire(f"session:{session_id}:messages", ttl)
        except Exception as e:
            logger.error(f"Error adding to conversation: {e}")
    
    def clear_conversation(self, session_id: str):
        """Clear conversation cache"""
        if not self._client:
            return
        try:
            self._client.delete(f"session:{session_id}:messages")
        except Exception as e:
            logger.error(f"Error clearing conversation: {e}")
    
    # AI Response Cache
    def get_ai_response(self, business_id: str, question_hash: str) -> Optional[str]:
        """Get cached AI response"""
        if not self._client:
            return None
        try:
            return self._client.get(f"ai:{business_id}:{question_hash}")
        except Exception as e:
            logger.error(f"Error getting AI response: {e}")
            return None
    
    def set_ai_response(self, business_id: str, question_hash: str, response: str, ttl: int = 3600):
        """Cache AI response"""
        if not self._client:
            return
        try:
            self._client.setex(f"ai:{business_id}:{question_hash}", ttl, response)
        except Exception as e:
            logger.error(f"Error setting AI response: {e}")
    
    # Spam Detection Cache
    def get_spam_score(self, user_id: str, session_id: str) -> int:
        """Get spam score for user/session"""
        if not self._client:
            return 0
        try:
            score = self._client.get(f"spam:{user_id}:{session_id}")
            return int(score) if score else 0
        except Exception as e:
            logger.error(f"Error getting spam score: {e}")
            return 0
    
    def increment_spam_score(self, user_id: str, session_id: str, increment: int = 1, ttl: int = 3600) -> int:
        """Increment spam score"""
        if not self._client:
            return 0
        try:
            key = f"spam:{user_id}:{session_id}"
            new_score = self._client.incrby(key, increment)
            self._client.expire(key, ttl)
            return new_score
        except Exception as e:
            logger.error(f"Error incrementing spam score: {e}")
            return 0
    
    def reset_spam_score(self, user_id: str, session_id: str):
        """Reset spam score"""
        if not self._client:
            return
        try:
            self._client.delete(f"spam:{user_id}:{session_id}")
        except Exception as e:
            logger.error(f"Error resetting spam score: {e}")
    
    # Rate Limiting
    def check_rate_limit(self, key: str, max_requests: int, window: int) -> bool:
        """Check if rate limit exceeded. Returns True if allowed"""
        if not self._client:
            return True
        try:
            current = self._client.get(key)
            if current is None:
                self._client.setex(key, window, 1)
                return True
            if int(current) >= max_requests:
                return False
            self._client.incr(key)
            return True
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True
    
    # General Purpose
    def get(self, key: str) -> Optional[Any]:
        """Get value from Redis"""
        if not self._client:
            return None
        try:
            value = self._client.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.error(f"Error getting key {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in Redis"""
        if not self._client:
            return
        try:
            if ttl:
                self._client.setex(key, ttl, json.dumps(value))
            else:
                self._client.set(key, json.dumps(value))
        except Exception as e:
            logger.error(f"Error setting key {key}: {e}")
    
    def delete(self, key: str):
        """Delete key from Redis"""
        if not self._client:
            return
        try:
            self._client.delete(key)
        except Exception as e:
            logger.error(f"Error deleting key {key}: {e}")
    
    def publish(self, channel: str, message: Dict):
        """Publish message to Redis channel"""
        if not self._client:
            return
        try:
            self._client.publish(channel, json.dumps(message))
        except Exception as e:
            logger.error(f"Error publishing to {channel}: {e}")


# Global instance
redis_client = RedisClient()


def get_redis_client() -> RedisClient:
    """Get Redis client instance"""
    return redis_client
