import os
from functools import lru_cache

from dotenv import load_dotenv
from redis import Redis
from redis.exceptions import RedisError


load_dotenv()


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    """애플리케이션에서 공유할 Redis 클라이언트를 반환한다."""
    return Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD"),
        db=int(os.getenv("REDIS_DB", "0")),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def check_redis_connection() -> bool:
    """Redis 연결 상태를 확인한다."""
    try:
        return bool(get_redis_client().ping())
    except RedisError as exc:
        raise RuntimeError(
            "Redis 연결에 실패했습니다."
        ) from exc