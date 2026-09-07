import asyncio
import time

import pytest

from backend.app.agent_jobs import AgentJobStore
from backend.app.aspect_jobs import AspectJobStore
from backend.app.execution import (
    AgentRequestTimeoutError,
    AgentUnavailableError,
    invoke_with_timeout,
)
from backend.app.health import dependency_status
from backend.app.titles import build_conversation_title


def test_first_question_builds_a_readable_conversation_title():
    assert build_conversation_title("  파손 상품의   환불 기준을 알려줘  ") == (
        "파손 상품의 환불 기준을 알려줘"
    )


def test_long_conversation_title_is_bounded():
    title = build_conversation_title("가" * 50)

    assert len(title) == 32
    assert title.endswith("…")


def test_aspect_job_state_survives_between_requests():
    class RedisClient:
        def __init__(self):
            self.values = {}

        def hset(self, key, mapping):
            self.values.setdefault(key, {}).update(mapping)

        def hgetall(self, key):
            return self.values.get(key, {})

        def expire(self, _key, _ttl):
            return True

    store = AspectJobStore(RedisClient())
    created = store.create(user_id=7, parent_asin="B00TEST123")
    store.update(
        created["job_id"],
        status="succeeded",
        result={"parent_asin": "B00TEST123", "patterns": []},
    )

    restored = store.get(created["job_id"])
    assert restored["user_id"] == 7
    assert restored["status"] == "succeeded"
    assert restored["result"] == {
        "parent_asin": "B00TEST123",
        "patterns": [],
    }


def test_agent_job_state_supports_async_polling():
    class RedisClient:
        def __init__(self):
            self.values = {}

        def hset(self, key, mapping):
            self.values.setdefault(key, {}).update(mapping)

        def hgetall(self, key):
            return self.values.get(key, {})

        def expire(self, _key, _ttl):
            return True

    store = AgentJobStore(RedisClient())
    created = store.create(user_id=7, conversation_id="conversation-1")
    store.update(
        created["job_id"],
        status="failed",
        http_status=504,
        error="답변 생성 시간이 초과되었습니다.",
    )

    restored = store.get(created["job_id"])
    assert restored["user_id"] == 7
    assert restored["conversation_id"] == "conversation-1"
    assert restored["status"] == "failed"
    assert restored["http_status"] == 504


def test_agent_request_has_an_overall_timeout():
    def slow_agent(_history):
        time.sleep(0.05)
        return {"messages": []}

    with pytest.raises(AgentRequestTimeoutError):
        asyncio.run(invoke_with_timeout(lambda: slow_agent([]), 0.01))


def test_agent_connection_failure_is_normalized():
    def unavailable_agent(_history):
        raise ConnectionError("provider unavailable")

    with pytest.raises(AgentUnavailableError):
        asyncio.run(invoke_with_timeout(lambda: unavailable_agent([]), 1))


def test_readiness_checks_postgres_and_redis():
    class Repository:
        def check_connection(self):
            return True

    class RedisClient:
        def ping(self):
            return True

    class SessionStore:
        client = RedisClient()

    assert dependency_status(Repository(), SessionStore()) == {
        "postgres": True,
        "redis": True,
    }


def test_readiness_reports_a_failed_dependency():
    class Repository:
        def check_connection(self):
            return False

    class RedisClient:
        def ping(self):
            return True

    class SessionStore:
        client = RedisClient()

    assert dependency_status(Repository(), SessionStore()) == {
        "postgres": False,
        "redis": True,
    }
