from functools import lru_cache
from typing import Annotated
from urllib.parse import urljoin

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from src.auth.access import ALL_COLLECTIONS, PolicyAccessGrant
from src.rag.config import ALL_DEPARTMENTS, ALL_JURISDICTIONS

from .config import WebSettings
from .audit import event_from_request
from .dependencies import (
    current_user,
    get_repository,
    get_session_store,
    get_settings,
)
from .models import CurrentUser, DevLoginRequest, UserRole
from .repository import WebRepository
from .google_identity import validate_google_identity

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config")
async def auth_config() -> dict[str, bool | str]:
    settings = get_settings()
    return {
        "oidc_enabled": settings.oidc_enabled,
        "dev_login_enabled": settings.dev_login_enabled,
        "oidc_provider": settings.oidc_provider,
    }


@lru_cache(maxsize=1)
def get_oauth_client() -> OAuth:
    settings = get_settings()
    if not settings.oidc_enabled:
        raise RuntimeError("OIDC가 설정되지 않았습니다.")
    oauth = OAuth()
    oauth.register(
        name="corporate",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=urljoin(
            settings.oidc_issuer.rstrip("/") + "/",
            ".well-known/openid-configuration",
        ),
        client_kwargs={"scope": "openid profile email"},
    )
    return oauth


def _set_session_cookie(
    response: Response,
    session_id: str,
    settings: WebSettings,
) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=None,
        path="/",
    )


def _validate_identity(userinfo: dict, settings: WebSettings) -> tuple[str, str, str]:
    try:
        identity = validate_google_identity(
            userinfo,
            require_verified_email=settings.oidc_require_verified_email,
            allowed_email_domains=settings.oidc_allowed_domains,
            workspace_domains=settings.google_workspace_domains,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return identity.subject, identity.email, identity.name


def _apply_bootstrap_admin(
    user: CurrentUser, settings: WebSettings, repository: WebRepository
) -> CurrentUser:
    if user.email.lower() in settings.bootstrap_admin_emails:
        return repository.update_user_access(user.user_id, UserRole.ADMIN, True)
    return user


def _persist_identity(
    *,
    repository: WebRepository,
    settings: WebSettings,
    issuer: str,
    subject: str,
    email: str,
    name: str,
) -> CurrentUser:
    user = repository.upsert_user(
        issuer=issuer,
        subject=subject,
        email=email,
        display_name=name,
    )
    return _apply_bootstrap_admin(user, settings, repository)


@router.get("/login")
async def login(
    request: Request,
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    settings = get_settings()
    if not settings.oidc_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "OIDC가 설정되지 않았습니다.")
    redirect_uri = settings.oidc_redirect_uri or str(request.url_for("oidc_callback"))
    await run_in_threadpool(
        repository.record_security_event,
        event_from_request(
            request,
            event_type="oidc_login_started",
            outcome="success",
            session_secret=settings.session_secret,
            oidc_issuer=settings.oidc_issuer,
        ),
    )
    authorization_options = {"prompt": "select_account"}
    if len(settings.google_workspace_domains) == 1:
        # hd는 계정 선택 화면의 힌트일 뿐이며 callback에서 다시 검증한다.
        authorization_options["hd"] = settings.google_workspace_domains[0]
    return await get_oauth_client().corporate.authorize_redirect(
        request, redirect_uri, **authorization_options
    )


@router.get("/callback", name="oidc_callback")
async def oidc_callback(
    request: Request,
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    settings = get_settings()
    try:
        token = await get_oauth_client().corporate.authorize_access_token(request)
    except OAuthError as exc:
        await run_in_threadpool(
            repository.record_security_event,
            event_from_request(
                request,
                event_type="oidc_login_failed",
                outcome="failure",
                session_secret=settings.session_secret,
                oidc_issuer=settings.oidc_issuer,
                metadata={"error_type": type(exc).__name__},
            ),
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "OIDC 로그인이 실패했습니다.") from exc
    userinfo = token.get("userinfo") or {}
    try:
        subject, email, name = _validate_identity(userinfo, settings)
    except HTTPException as exc:
        await run_in_threadpool(
            repository.record_security_event,
            event_from_request(
                request,
                event_type="oidc_identity_denied",
                outcome="denied",
                session_secret=settings.session_secret,
                oidc_issuer=settings.oidc_issuer,
                oidc_subject=str(userinfo.get("sub") or "") or None,
                metadata={"reason": exc.detail},
            ),
        )
        raise
    user = await run_in_threadpool(
        _persist_identity,
        repository=repository,
        settings=settings,
        issuer=settings.oidc_issuer or "",
        subject=subject,
        email=email,
        name=name,
    )
    session_id = await run_in_threadpool(
        get_session_store().create_session, user.user_id
    )
    await run_in_threadpool(
        repository.record_security_event,
        event_from_request(
            request,
            event_type="oidc_login_succeeded",
            outcome="success",
            session_secret=settings.session_secret,
            session_id=session_id,
            actor_user_id=user.user_id,
            oidc_issuer=settings.oidc_issuer,
            oidc_subject=subject,
            metadata={"workspace_domain": userinfo.get("hd")},
        ),
    )
    request.session.clear()
    response = RedirectResponse(settings.frontend_url, status_code=303)
    _set_session_cookie(response, session_id, settings)
    return response


@router.post("/dev-login", response_model=CurrentUser)
def dev_login(
    body: DevLoginRequest,
    request: Request,
    response: Response,
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    settings = get_settings()
    if not settings.dev_login_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "개발 로그인이 비활성화되어 있습니다.")
    user = repository.upsert_user(
        issuer="development",
        subject=body.email.lower(),
        email=body.email.lower(),
        display_name=body.display_name,
    )
    user = _apply_bootstrap_admin(user, settings, repository)
    if not user.policy_scopes:
        user = repository.replace_user_scopes(
            user.user_id,
            [PolicyAccessGrant(ALL_COLLECTIONS, ALL_JURISDICTIONS, ALL_DEPARTMENTS)],
        )
    session_id = get_session_store().create_session(user.user_id)
    repository.record_security_event(
        event_from_request(
            request,
            event_type="development_login_succeeded",
            outcome="success",
            session_secret=settings.session_secret,
            session_id=session_id,
            actor_user_id=user.user_id,
        )
    )
    _set_session_cookie(response, session_id, settings)
    return user


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    repository: Annotated[WebRepository, Depends(get_repository)],
):
    settings = get_settings()
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        session = get_session_store().get_session(session_id)
        get_session_store().delete_session(session_id)
        repository.record_security_event(
            event_from_request(
                request,
                event_type="logout",
                outcome="success",
                session_secret=settings.session_secret,
                session_id=session_id,
                actor_user_id=int(session["user_id"]) if session else None,
            )
        )
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=CurrentUser)
def me(
    user: Annotated[CurrentUser, Depends(current_user)],
) -> CurrentUser:
    return user
