from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    name: str
    hosted_domain: str | None


def validate_google_identity(
    userinfo: dict[str, Any],
    *,
    require_verified_email: bool,
    allowed_email_domains: tuple[str, ...],
    workspace_domains: tuple[str, ...],
) -> GoogleIdentity:
    subject = str(userinfo.get("sub", "")).strip()
    email = str(userinfo.get("email", "")).strip().lower()
    name = str(userinfo.get("name") or email).strip()
    hosted_domain = str(userinfo.get("hd", "")).strip().lower() or None
    if not subject or not email:
        raise ValueError("Google 사용자 정보가 부족합니다.")
    if require_verified_email and userinfo.get("email_verified") is not True:
        raise ValueError("확인되지 않은 이메일입니다.")
    if allowed_email_domains:
        email_domain = email.rsplit("@", 1)[-1]
        if email_domain not in allowed_email_domains:
            raise ValueError("허용되지 않은 이메일 도메인입니다.")
    if workspace_domains and hosted_domain not in workspace_domains:
        raise ValueError("허용되지 않은 Google Workspace 계정입니다.")
    return GoogleIdentity(subject, email, name, hosted_domain)
