import asyncio
import time

import pytest

from backend.app.execution import (
    AgentRequestTimeoutError,
    AgentUnavailableError,
    invoke_with_timeout,
)
from backend.app.health import dependency_status


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
