import hashlib
import json
import os

from pydantic import ValidationError
from redis.exceptions import RedisError

from src.analysis.schemas import ClassifiedReview
from src.cache.redis_client import get_redis_client


CACHE_NAMESPACE = "review-extractor:v1"


def build_review_cache_key(
    review_title: str,
    review_text: str,
    extractor_version: str,
) -> str:
    """리뷰 내용과 Extractor 버전을 기반으로 캐시 키를 생성한다."""
    payload = json.dumps(
        {
            "review_title": review_title,
            "review_text": review_text,
            "extractor_version": extractor_version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()

    return f"{CACHE_NAMESPACE}:{digest}"


def get_cached_review(
    cache_key: str,
) -> ClassifiedReview | None:
    """Redis에 저장된 리뷰 분석 결과를 반환한다."""
    try:
        cached_value = get_redis_client().get(cache_key)
    except RedisError:
        return None

    if cached_value is None:
        return None

    try:
        return ClassifiedReview.model_validate_json(
            cached_value
        )
    except ValidationError:
        try:
            get_redis_client().delete(cache_key)
        except RedisError:
            pass

        return None


def set_cached_review(
    cache_key: str,
    result: ClassifiedReview,
) -> None:
    """리뷰 분석 결과를 Redis에 저장한다."""
    ttl_seconds = int(
        os.getenv(
            "REVIEW_CACHE_TTL_SECONDS",
            "2592000",
        )
    )

    try:
        get_redis_client().setex(
            cache_key,
            ttl_seconds,
            result.model_dump_json(),
        )
    except RedisError:
        pass