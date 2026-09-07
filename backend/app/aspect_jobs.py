import json
import logging
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

from redis import Redis

from src.analysis.schemas import ReviewPatternResult
from src.cache.redis_client import get_redis_client
from src.tools import get_review_patterns_tool

logger = logging.getLogger("customer_intelligence.aspect_jobs")
JOB_PREFIX = "ci:aspect-job"


class AspectJobStore:
    def __init__(self, client: Redis | None = None) -> None:
        self.client = client or get_redis_client()
        self.ttl_seconds = int(os.getenv("ASPECT_JOB_TTL_SECONDS", "3600"))

    def create(self, *, user_id: int, parent_asin: str) -> dict:
        job_id = uuid4()
        value = {
            "job_id": str(job_id),
            "user_id": str(user_id),
            "parent_asin": parent_asin,
            "status": "queued",
            "created_at": datetime.now(UTC).isoformat(),
        }
        key = f"{JOB_PREFIX}:{job_id}"
        self.client.hset(key, mapping=value)
        self.client.expire(key, self.ttl_seconds)
        return value

    def get(self, job_id: UUID | str) -> dict | None:
        value = self.client.hgetall(f"{JOB_PREFIX}:{job_id}")
        if not value:
            return None
        if value.get("result"):
            value["result"] = json.loads(value["result"])
        value["user_id"] = int(value["user_id"])
        return value

    def update(self, job_id: UUID | str, **values) -> None:
        serialized = {
            key: json.dumps(value, ensure_ascii=False)
            if key == "result"
            else str(value)
            for key, value in values.items()
        }
        key = f"{JOB_PREFIX}:{job_id}"
        self.client.hset(key, mapping=serialized)
        self.client.expire(key, self.ttl_seconds)


def run_aspect_job(job_id: UUID | str, parent_asin: str) -> None:
    """HTTP 요청과 분리해 콜드 캐시 Aspect 추출을 완료한다."""
    store = AspectJobStore()
    store.update(job_id, status="running")
    try:
        raw = get_review_patterns_tool.invoke(
            {"parent_asin": parent_asin, "limit": 20}
        )
        result = ReviewPatternResult.model_validate(raw)
        store.update(
            job_id,
            status="succeeded",
            result=result.model_dump(mode="json"),
            completed_at=datetime.now(UTC).isoformat(),
        )
    except Exception:
        logger.exception(
            "dashboard_aspect_job_failed job_id=%s parent_asin=%s",
            job_id,
            parent_asin,
        )
        store.update(
            job_id,
            status="failed",
            error="Aspect 분석을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            completed_at=datetime.now(UTC).isoformat(),
        )
