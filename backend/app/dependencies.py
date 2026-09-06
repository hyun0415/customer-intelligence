from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyCookie

from src.auth.session_store import RedisSessionStore

from .config import WebSettings
from .models import CurrentUser, UserRole
from .repository import WebRepository
from .audit import event_from_request


@lru_cache(maxsize=1)
def get_settings() -> WebSettings:
    return WebSettings.from_env()


@lru_cache(maxsize=1)
def get_repository() -> WebRepository:
    return WebRepository()


@lru_cache(maxsize=1)
def get_session_store() -> RedisSessionStore:
    return RedisSessionStore()


def session_cookie():
    return APIKeyCookie(
        name=get_settings().session_cookie_name,
        auto_error=False,
    )


def current_user(
    request: Request,
    session_id: Annotated[str | None, Depends(session_cookie())],
    repository: Annotated[WebRepository, Depends(get_repository)],
    sessions: Annotated[RedisSessionStore, Depends(get_session_store)],
) -> CurrentUser:
    if not session_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다.")
    session = sessions.get_session(session_id)
    if not session:
        repository.record_security_event(
            event_from_request(
                request,
                event_type="authentication_denied",
                outcome="denied",
                session_secret=get_settings().session_secret,
                session_id=session_id,
                metadata={"reason": "expired_or_unknown_session"},
            )
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "세션이 만료되었습니다.")
    user = repository.get_user(int(session["user_id"]))
    if user is None or not user.is_active:
        repository.record_security_event(
            event_from_request(
                request,
                event_type="authentication_denied",
                outcome="denied",
                session_secret=get_settings().session_secret,
                session_id=session_id,
                actor_user_id=int(session["user_id"]),
                metadata={"reason": "inactive_or_unknown_user"},
            )
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "사용할 수 없는 계정입니다.")
    return user


def require_roles(*roles: UserRole):
    def dependency(
        request: Request,
        user: Annotated[CurrentUser, Depends(current_user)],
        repository: Annotated[WebRepository, Depends(get_repository)],
    ) -> CurrentUser:
        if user.role not in roles:
            settings = get_settings()
            session_id = request.cookies.get(settings.session_cookie_name)
            repository.record_security_event(
                event_from_request(
                    request,
                    event_type="authorization_denied",
                    outcome="denied",
                    session_secret=settings.session_secret,
                    session_id=session_id,
                    actor_user_id=user.user_id,
                    metadata={
                        "actual_role": user.role.value,
                        "required_roles": [role.value for role in roles],
                        "path": request.url.path,
                    },
                )
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "권한이 없습니다.")
        return user

    return dependency
