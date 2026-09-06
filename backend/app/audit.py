import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "code",
    "id_token",
    "refresh_token",
    "session_id",
    "token",
}


def session_fingerprint(session_id: str | None, secret: str) -> str | None:
    if not session_id:
        return None
    return hmac.new(
        secret.encode("utf-8"), session_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if str(key).lower() in SENSITIVE_KEYS
                else sanitize_metadata(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    return value


@dataclass(frozen=True)
class SecurityAuditEvent:
    event_type: str
    outcome: str
    actor_user_id: int | None = None
    oidc_issuer: str | None = None
    oidc_subject: str | None = None
    session_fingerprint: str | None = None
    request_id: UUID = field(default_factory=uuid4)
    ip_address: str | None = None
    user_agent: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def database_values(self) -> tuple[Any, ...]:
        return (
            uuid4(),
            self.event_type,
            self.outcome,
            self.actor_user_id,
            self.oidc_issuer,
            self.oidc_subject,
            self.session_fingerprint,
            self.request_id,
            self.ip_address,
            self.user_agent,
            self.resource_type,
            self.resource_id,
            json.dumps(sanitize_metadata(self.metadata), ensure_ascii=False),
        )


def event_from_request(
    request: Any,
    *,
    event_type: str,
    outcome: str,
    session_secret: str,
    session_id: str | None = None,
    actor_user_id: int | None = None,
    oidc_issuer: str | None = None,
    oidc_subject: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SecurityAuditEvent:
    request_id = getattr(request.state, "request_id", None) or uuid4()
    client = getattr(request, "client", None)
    return SecurityAuditEvent(
        event_type=event_type,
        outcome=outcome,
        actor_user_id=actor_user_id,
        oidc_issuer=oidc_issuer,
        oidc_subject=oidc_subject,
        session_fingerprint=session_fingerprint(session_id, session_secret),
        request_id=request_id,
        ip_address=getattr(client, "host", None),
        user_agent=request.headers.get("user-agent"),
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata or {},
    )
