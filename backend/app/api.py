from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from src.auth.access import ALL_COLLECTIONS
from src.rag.config import ALL_DEPARTMENTS, ALL_JURISDICTIONS, DEFAULT_COLLECTIONS

from .agent_jobs import AgentJobStore, run_agent_job
from .aspect_jobs import AspectJobStore, run_aspect_job
from .audit import event_from_request, session_fingerprint
from .dependencies import (
    current_user,
    get_repository,
    get_session_store,
    get_settings,
    require_roles,
)
from .health import dependency_status
from .models import (
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    CurrentUser,
    DashboardProduct,
    DashboardProductDetail,
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
    if body.product_parent_asin and not repository.product_exists(
        body.product_parent_asin
    ):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "연결할 상품을 찾을 수 없습니다.",
        )
    return repository.create_conversation(
        user.user_id,
        body.title,
        context_mode=body.context_mode,
        product_parent_asin=body.product_parent_asin,
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    user: Annotated[CurrentUser, Depends(current_user)],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    return repository.list_conversations(user.user_id)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def archive_conversation(
    conversation_id: UUID,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    if not repository.archive_conversation(user.user_id, conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "대화를 찾을 수 없습니다.")
    settings = get_settings()
    repository.record_security_event(
        event_from_request(
            request,
            event_type="conversation_archived",
            outcome="success",
            session_secret=settings.session_secret,
            session_id=request.cookies.get(settings.session_cookie_name),
            actor_user_id=user.user_id,
            resource_type="conversation",
            resource_id=str(conversation_id),
        )
    )


@router.get("/dashboard/products", response_model=list[DashboardProduct])
def list_dashboard_products(
    _user: Annotated[CurrentUser, Depends(current_user)],
    repository: Annotated[WebRepository, Depends(get_repository)],
    query: str | None = None,
    limit: int = 12,
):
    if not 1 <= limit <= 50:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "limit은 1 이상 50 이하여야 합니다.",
        )
    return repository.list_dashboard_products(query=query, limit=limit)


@router.get(
    "/dashboard/products/{parent_asin}",
    response_model=DashboardProductDetail,
)
def get_dashboard_product(
    parent_asin: str,
    _user: Annotated[CurrentUser, Depends(current_user)],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    product = repository.get_dashboard_product(parent_asin)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "상품을 찾을 수 없습니다.")
    return product


@router.post(
    "/dashboard/products/{parent_asin}/patterns",
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_dashboard_product_patterns(
    parent_asin: str,
    background_tasks: BackgroundTasks,
    user: Annotated[CurrentUser, Depends(current_user)],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    if not repository.product_exists(parent_asin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "상품을 찾을 수 없습니다.")
    job = AspectJobStore().create(
        user_id=user.user_id,
        parent_asin=parent_asin,
    )
    background_tasks.add_task(run_aspect_job, job["job_id"], parent_asin)
    return {
        "job_id": job["job_id"],
        "parent_asin": parent_asin,
        "status": job["status"],
    }


@router.get("/dashboard/pattern-jobs/{job_id}")
def get_dashboard_pattern_job(
    job_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
):
    job = AspectJobStore().get(job_id)
    if job is None or job["user_id"] != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "분석 작업을 찾을 수 없습니다.")
    return {
        key: value
        for key, value in job.items()
        if key != "user_id"
    }


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
    status_code=status.HTTP_202_ACCEPTED,
)
def create_message(
    conversation_id: UUID,
    body: MessageCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    user: Annotated[CurrentUser, Depends(current_user)],
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    if repository.get_conversation(user.user_id, conversation_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "대화를 찾을 수 없습니다.")
    settings = get_settings()
    job = AgentJobStore().create(
        user_id=user.user_id,
        conversation_id=conversation_id,
    )
    background_tasks.add_task(
        run_agent_job,
        job_id=job["job_id"],
        user=user,
        conversation_id=conversation_id,
        content=body.content,
        repository=repository,
        timeout_seconds=settings.agent_request_timeout_seconds,
        audit_context={
            "request_id": request.state.request_id,
            "session_fingerprint": session_fingerprint(
                request.cookies.get(settings.session_cookie_name),
                settings.session_secret,
            ),
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        },
    )
    return {
        "job_id": job["job_id"],
        "conversation_id": str(conversation_id),
        "status": job["status"],
    }


@router.get("/conversation-jobs/{job_id}")
def get_conversation_job(
    job_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
):
    job = AgentJobStore().get(job_id)
    if job is None or job["user_id"] != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "답변 작업을 찾을 수 없습니다.")
    return {key: value for key, value in job.items() if key != "user_id"}


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
