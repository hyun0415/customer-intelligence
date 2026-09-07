import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

process_started_at = perf_counter()

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from .api import router as api_router
from .auth import router as auth_router
from .dependencies import get_settings

settings = get_settings()
logger = logging.getLogger("customer_intelligence.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "application_ready startup_ms=%.1f",
        (perf_counter() - process_started_at) * 1000,
    )
    yield
    logger.info("application_stopped")


app = FastAPI(
    title="Customer Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_id_middleware(request, call_next):
    request.state.request_id = uuid4()
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed method=%s path=%s request_id=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            request.state.request_id,
            (perf_counter() - started_at) * 1000,
        )
        response = JSONResponse(
            status_code=500,
            content={
                "detail": "서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
                "request_id": str(request.state.request_id),
            },
        )
    response.headers["X-Request-ID"] = str(request.state.request_id)
    logger.info(
        "request_completed method=%s path=%s status=%s request_id=%s duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        request.state.request_id,
        (perf_counter() - started_at) * 1000,
    )
    return response
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret or "development-oidc-state-only-secret",
    session_cookie="ci_oidc_state",
    same_site="lax",
    https_only=settings.session_cookie_secure,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)
app.include_router(auth_router)
app.include_router(api_router)
