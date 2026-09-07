from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from redis import Redis

from src.cache.redis_client import get_redis_client

from .audit import SecurityAuditEvent
from .execution import AgentRequestTimeoutError, AgentUnavailableError

if TYPE_CHECKING:
    from .models import CurrentUser
    from .repository import WebRepository

logger = logging.getLogger("customer_intelligence.agent_jobs")
JOB_PREFIX = "ci:agent-job"


class AgentJobStore:
    def __init__(self, client: Redis | None = None) -> None:
        self.client = client or get_redis_client()
        self.ttl_seconds = int(os.getenv("AGENT_JOB_TTL_SECONDS", "3600"))

    def create(self, *, user_id: int, conversation_id: UUID | str) -> dict:
        job_id = uuid4()
        value = {
            "job_id": str(job_id),
            "user_id": str(user_id),
            "conversation_id": str(conversation_id),
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
        if value.get("http_status"):
            value["http_status"] = int(value["http_status"])
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


async def run_agent_job(
    *,
    job_id: UUID | str,
    user: CurrentUser,
    conversation_id: UUID,
    content: str,
    repository: WebRepository,
    timeout_seconds: float,
    audit_context: dict,
) -> None:
    """프록시 요청 수명과 분리해 Agent 응답 생성과 저장을 완료한다."""
    from .agent_service import ConversationAgentService

    store = AgentJobStore()
    store.update(job_id, status="running")
    try:
        response = await ConversationAgentService(
            repository,
            timeout_seconds=timeout_seconds,
        ).respond(
            user=user,
            conversation_id=conversation_id,
            content=content,
        )
        store.update(
            job_id,
            status="succeeded",
            result=response.model_dump(mode="json"),
            completed_at=datetime.now(UTC).isoformat(),
        )
        return
    except AgentRequestTimeoutError:
        reason = "timeout"
        http_status = 504
        error = "답변 생성 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."
    except AgentUnavailableError:
        reason = "unavailable"
        http_status = 503
        error = "AI 서비스에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
    except KeyError:
        reason = "conversation_not_found"
        http_status = 404
        error = "대화를 찾을 수 없습니다."
    except Exception:
        logger.exception(
            "agent_job_failed job_id=%s conversation_id=%s",
            job_id,
            conversation_id,
        )
        reason = "unexpected_error"
        http_status = 500
        error = "답변을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요."

    store.update(
        job_id,
        status="failed",
        http_status=http_status,
        error=error,
        completed_at=datetime.now(UTC).isoformat(),
    )
    try:
        repository.record_security_event(
            SecurityAuditEvent(
                event_type="agent_request_failed",
                outcome="failure",
                actor_user_id=user.user_id,
                request_id=audit_context["request_id"],
                session_fingerprint=audit_context.get("session_fingerprint"),
                ip_address=audit_context.get("ip_address"),
                user_agent=audit_context.get("user_agent"),
                resource_type="conversation",
                resource_id=str(conversation_id),
                metadata={"reason": reason, "job_id": str(job_id)},
            )
        )
    except Exception:
        logger.exception("agent_job_audit_failed job_id=%s", job_id)
