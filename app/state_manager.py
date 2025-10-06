# app/state_manager.py
"""Redis State Manager für WhatsApp Orchestrator."""
import os
import json
import redis
from typing import Optional, Dict, Any
from datetime import datetime
import logging

log = logging.getLogger("uvicorn")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SESSION_TTL = int(os.getenv("SESSION_TTL_HOURS", "24")) * 3600

# Redis Connection
try:
    redis_client = redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5,
        retry_on_timeout=True,
        health_check_interval=30
    )
    redis_client.ping()
    log.info("✅ Redis connected successfully")
except Exception as e:
    log.error(f"❌ Redis connection failed: {e}")
    redis_client = None


class StateManager:
    def __init__(self):
        self.redis = redis_client
        self.fallback = {}  # In-Memory Fallback
    
    def _key(self, user: str) -> str:
        return f"session:{user}"
    
    def get(self, user: str) -> Optional[Dict[str, Any]]:
        """Lädt State aus Redis (oder None)."""
        key = self._key(user)
        try:
            if self.redis:
                data = self.redis.get(key)
                if data:
                    return json.loads(data)
            return self.fallback.get(user)
        except Exception as e:
            log.error(f"State load error: {e}")
            return self.fallback.get(user)
    
    def set(self, user: str, state: Dict[str, Any]) -> bool:
        """Speichert State in Redis mit TTL."""
        key = self._key(user)
        try:
            if self.redis:
                state["_updated"] = datetime.utcnow().isoformat()
                data = json.dumps(state)
                self.redis.setex(key, SESSION_TTL, data)
                return True
            else:
                self.fallback[user] = state
                return True
        except Exception as e:
            log.error(f"State save error: {e}")
            self.fallback[user] = state
            return False
    
    def delete(self, user: str) -> bool:
        """Löscht State."""
        key = self._key(user)
        try:
            if self.redis:
                self.redis.delete(key)
            self.fallback.pop(user, None)
            return True
        except Exception as e:
            log.error(f"State delete error: {e}")
            return False
    
    def extend_ttl(self, user: str, hours: int = 24):
        """Verlängert TTL."""
        key = self._key(user)
        try:
            if self.redis:
                self.redis.expire(key, hours * 3600)
        except Exception as e:
            log.error(f"TTL extend error: {e}")
    
    def health(self) -> Dict[str, Any]:
        """Health Check."""
        try:
            if self.redis:
                self.redis.ping()
                info = self.redis.info('stats')
                return {
                    "status": "healthy",
                    "connected": True,
                    "commands": info.get('total_commands_processed', 0)
                }
            else:
                return {
                    "status": "degraded",
                    "connected": False,
                    "fallback_sessions": len(self.fallback)
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Global Instance
state_manager = StateManager()
