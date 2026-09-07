import asyncio
from collections.abc import Callable
from typing import Any

from openai import OpenAIError


class AgentRequestTimeoutError(RuntimeError):
    pass


class AgentUnavailableError(RuntimeError):
    pass


async def invoke_with_timeout(
    operation: Callable[[], Any], timeout_seconds: float
) -> Any:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(operation),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise AgentRequestTimeoutError(
            "Agent 응답 제한 시간을 초과했습니다."
        ) from exc
    except (OpenAIError, ConnectionError) as exc:
        raise AgentUnavailableError(
            "Agent 모델에 연결할 수 없습니다."
        ) from exc
