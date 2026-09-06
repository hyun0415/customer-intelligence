from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .api import router as api_router
from .auth import router as auth_router
from .dependencies import get_settings
from uuid import uuid4

settings = get_settings()

app = FastAPI(title="Customer Intelligence API", version="0.1.0")


@app.middleware("http")
async def request_id_middleware(request, call_next):
    request.state.request_id = uuid4()
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(request.state.request_id)
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
