from typing import Annotated
from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.auth.access import ALL_COLLECTIONS
from src.rag.config import ALL_DEPARTMENTS, ALL_JURISDICTIONS, DEFAULT_COLLECTIONS

from .agent_service import ConversationAgentService
from .audit import event_from_request
from .dependencies import (
    current_user,
    get_repository,
    get_session_store,
    get_settings,
    require_roles,
)
from .execution import AgentRequestTimeoutError, AgentUnavailableError
from .health import dependency_status
from .models import (
    AgentResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    CurrentUser,
    EscalationUpdate,
    MessageCreate,
    ScopeReplaceRequest,
    UserAccessUpdate,
    UserRole,
)
from .repository import WebRepository

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    dependencies = {"postgres": False, "redis": False}
    try:
        dependencies = dependency_status(repository, get_session_store())
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {
                "message": "서비스 의존성이 아직 준비되지 않았습니다.",
                "dependencies": dependencies,
            },
        ) from exc
    if not all(dependencies.values()):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {
                "message": "서비스 의존성이 아직 준비되지 않았습니다.",
                "dependencies": dependencies,
            },
        )
    return {"status": "ready", "dependencies": dependencies}


@router.post("/conversations", response_model=ConversationSummary, status_code=201)
def create_conversation(
    body: ConversationCreate,
    user: Annotated[CurrentUser, Depends(current_user)],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    return repository.create_conversation(user.user_id, body.title)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    user: Annotated[CurrentUser, Depends(current_user)],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    return repository.list_conversations(user.user_id)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    conversation = repository.get_conversation(user.user_id, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "대화를 찾을 수 없습니다.")
    return conversation


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AgentResponse,
)
async def create_message(
    conversation_id: UUID,
    body: MessageCreate,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    try:
        settings = get_settings()
        return await ConversationAgentService(
            repository,
            timeout_seconds=settings.agent_request_timeout_seconds,
        ).respond(
            user=user,
            conversation_id=conversation_id,
            content=body.content,
        )
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "대화를 찾을 수 없습니다.") from exc
    except AgentRequestTimeoutError as exc:
        repository.record_security_event(
            event_from_request(
                request,
                event_type="agent_request_failed",
                outcome="timeout",
                session_secret=settings.session_secret,
                session_id=request.cookies.get(settings.session_cookie_name),
                actor_user_id=user.user_id,
                resource_type="conversation",
                resource_id=str(conversation_id),
            )
        )
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "답변 생성 시간이 초과되었습니다. 질문은 저장되었으며 잠시 후 다시 시도해 주세요.",
        ) from exc
    except AgentUnavailableError as exc:
        repository.record_security_event(
            event_from_request(
                request,
                event_type="agent_request_failed",
                outcome="unavailable",
                session_secret=settings.session_secret,
                session_id=request.cookies.get(settings.session_cookie_name),
                actor_user_id=user.user_id,
                resource_type="conversation",
                resource_id=str(conversation_id),
            )
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI 서비스에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc


@router.get("/admin/users", response_model=list[CurrentUser])
def list_users(
    _admin: Annotated[CurrentUser, Depends(require_roles(UserRole.ADMIN))],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    return repository.list_users()


@router.get("/admin/security-audit-events")
def list_security_audit_events(
    _admin: Annotated[CurrentUser, Depends(require_roles(UserRole.ADMIN))],
    repository: Annotated[WebRepository, Depends(get_repository)],
    limit: int = 100,
):
    if not 1 <= limit <= 500:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "limit은 1 이상 500 이하여야 합니다.",
        )
    return repository.list_security_events(limit)


@router.put("/admin/users/{user_id}/scopes", response_model=CurrentUser)
def replace_scopes(
    user_id: int,
    body: ScopeReplaceRequest,
    request: Request,
    admin: Annotated[CurrentUser, Depends(require_roles(UserRole.ADMIN))],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    valid_collections = {*DEFAULT_COLLECTIONS, ALL_COLLECTIONS}
    for scope in body.scopes:
        if scope.collection not in valid_collections:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"지원하지 않는 collection입니다: {scope.collection}",
            )
        if not scope.jurisdiction.strip() or not scope.department.strip():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "관할과 부서는 빈 값일 수 없습니다.",
            )
    try:
        updated = repository.replace_user_scopes(user_id, body.scopes)
        settings = get_settings()
        repository.record_security_event(
            event_from_request(
                request,
                event_type="policy_scopes_changed",
                outcome="success",
                session_secret=settings.session_secret,
                session_id=request.cookies.get(settings.session_cookie_name),
                actor_user_id=admin.user_id,
                resource_type="user",
                resource_id=str(user_id),
                metadata={"scopes": [asdict(scope) for scope in body.scopes]},
            )
        )
        return updated
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사용자를 찾을 수 없습니다.") from exc


@router.put("/admin/users/{user_id}/access", response_model=CurrentUser)
def update_user_access(
    user_id: int,
    body: UserAccessUpdate,
    request: Request,
    admin: Annotated[CurrentUser, Depends(require_roles(UserRole.ADMIN))],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    try:
        updated = repository.update_user_access(user_id, body.role, body.is_active)
        settings = get_settings()
        repository.record_security_event(
            event_from_request(
                request,
                event_type="user_access_changed",
                outcome="success",
                session_secret=settings.session_secret,
                session_id=request.cookies.get(settings.session_cookie_name),
                actor_user_id=admin.user_id,
                resource_type="user",
                resource_id=str(user_id),
                metadata={"role": body.role.value, "is_active": body.is_active},
            )
        )
        return updated
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사용자를 찾을 수 없습니다.") from exc


@router.get("/escalations")
def list_escalations(
    _manager: Annotated[
        CurrentUser,
        Depends(require_roles(UserRole.MANAGER, UserRole.ADMIN)),
    ],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    return repository.list_escalations()


@router.put("/escalations/{escalation_id}")
def update_escalation(
    escalation_id: UUID,
    body: EscalationUpdate,
    request: Request,
    manager: Annotated[
        CurrentUser,
        Depends(require_roles(UserRole.MANAGER, UserRole.ADMIN)),
    ],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    try:
        updated = repository.update_escalation(escalation_id, body.status)
        settings = get_settings()
        repository.record_security_event(
            event_from_request(
                request,
                event_type="escalation_status_changed",
                outcome="success",
                session_secret=settings.session_secret,
                session_id=request.cookies.get(settings.session_cookie_name),
                actor_user_id=manager.user_id,
                resource_type="escalation",
                resource_id=str(escalation_id),
                metadata={"status": body.status},
            )
        )
        return updated
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escalation을 찾을 수 없습니다.") from exc


SCOPE_SENTINELS = {
    "collection": ALL_COLLECTIONS,
    "jurisdiction": ALL_JURISDICTIONS,
    "department": ALL_DEPARTMENTS,
}
