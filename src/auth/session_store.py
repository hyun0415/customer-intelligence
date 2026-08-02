import os
import secrets
from datetime import UTC, datetime

import redis
from src.cache.redis_client import get_redis_client

SESSION_KEY_PREFIX = "ci:session"


class RedisSessionStore:
    def __init__(
        self,
        client: redis.Redis | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self.client = client or get_redis_client()
        self.ttl_seconds = ttl_seconds or int(
            os.getenv(
                "SESSION_TTL_SECONDS",
                "28800",
            )
        )

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{SESSION_KEY_PREFIX}:{session_id}"

    def create_session(
        self,
        user_id: int,
    ) -> str:
        session_id = secrets.token_urlsafe(32)
        key = self._key(session_id)

        self.client.hset(
            key,
            mapping={
                "user_id": str(user_id),
                "created_at": datetime.now(
                    UTC
                ).isoformat(),
            },
        )
        self.client.expire(
            key,
            self.ttl_seconds,
        )

        return session_id

    def get_session(
        self,
        session_id: str,
        refresh_ttl: bool = True,
    ) -> dict[str, str] | None:
        key = self._key(session_id)
        session = self.client.hgetall(key)

        if not session:
            return None

        if refresh_ttl:
            self.client.expire(
                key,
                self.ttl_seconds,
            )

        return session

    def delete_session(
        self,
        session_id: str,
    ) -> bool:
        deleted = self.client.delete(
            self._key(session_id)
        )

        return bool(deleted)