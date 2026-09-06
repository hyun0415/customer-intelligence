import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WebSettings:
    app_env: str
    frontend_url: str
    session_cookie_name: str
    session_secret: str
    session_cookie_secure: bool
    dev_login_enabled: bool
    oidc_issuer: str | None
    oidc_client_id: str | None
    oidc_client_secret: str | None
    oidc_allowed_domains: tuple[str, ...]
    oidc_require_verified_email: bool
    oidc_redirect_uri: str | None
    google_workspace_domains: tuple[str, ...]
    bootstrap_admin_emails: tuple[str, ...]

    @property
    def oidc_enabled(self) -> bool:
        return bool(
            self.oidc_issuer
            and self.oidc_client_id
            and self.oidc_client_secret
        )

    @property
    def oidc_provider(self) -> str:
        if (self.oidc_issuer or "").rstrip("/") == "https://accounts.google.com":
            return "google"
        return "oidc"

    @classmethod
    def from_env(cls) -> "WebSettings":
        domains = tuple(
            item.strip().lower()
            for item in os.getenv("OIDC_ALLOWED_DOMAINS", "").split(",")
            if item.strip()
        )
        admin_emails = tuple(
            item.strip().lower()
            for item in os.getenv("BOOTSTRAP_ADMIN_EMAILS", "").split(",")
            if item.strip()
        )
        workspace_domains = tuple(
            item.strip().lower()
            for item in os.getenv("GOOGLE_WORKSPACE_DOMAINS", "").split(",")
            if item.strip()
        )
        google_client_id = os.getenv("GOOGLE_OIDC_CLIENT_ID") or os.getenv("OIDC_CLIENT_ID")
        google_client_secret = os.getenv("GOOGLE_OIDC_CLIENT_SECRET") or os.getenv("OIDC_CLIENT_SECRET")
        settings = cls(
            app_env=os.getenv("APP_ENV", "development").strip().lower(),
            frontend_url=os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/"),
            session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "ci_session"),
            session_secret=os.getenv("SESSION_SECRET", ""),
            session_cookie_secure=_bool_env("SESSION_COOKIE_SECURE", False),
            dev_login_enabled=_bool_env("DEV_LOGIN_ENABLED", False),
            oidc_issuer=os.getenv("OIDC_ISSUER") or (
                "https://accounts.google.com"
                if google_client_id or google_client_secret
                else None
            ),
            oidc_client_id=google_client_id,
            oidc_client_secret=google_client_secret,
            oidc_allowed_domains=domains,
            oidc_require_verified_email=_bool_env(
                "OIDC_REQUIRE_VERIFIED_EMAIL", True
            ),
            oidc_redirect_uri=os.getenv("GOOGLE_OIDC_REDIRECT_URI") or os.getenv("OIDC_REDIRECT_URI"),
            google_workspace_domains=workspace_domains,
            bootstrap_admin_emails=admin_emails,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.app_env == "production" and self.dev_login_enabled:
            raise ValueError("운영 환경에서는 DEV_LOGIN_ENABLED를 사용할 수 없습니다.")
        if (self.oidc_enabled or self.dev_login_enabled) and len(self.session_secret) < 32:
            raise ValueError("로그인 사용 시 SESSION_SECRET은 32자 이상이어야 합니다.")
        if self.app_env == "production" and len(self.session_secret) < 32:
            raise ValueError("운영 환경의 SESSION_SECRET은 32자 이상이어야 합니다.")
        oidc_values = (
            self.oidc_issuer,
            self.oidc_client_id,
            self.oidc_client_secret,
        )
        if any(oidc_values) and not all(oidc_values):
            raise ValueError("OIDC issuer, client id, client secret을 모두 설정해야 합니다.")
        if self.google_workspace_domains and self.oidc_provider != "google":
            raise ValueError("GOOGLE_WORKSPACE_DOMAINS는 Google OIDC에서만 사용할 수 있습니다.")
