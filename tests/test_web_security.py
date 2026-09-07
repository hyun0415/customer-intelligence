from datetime import UTC, datetime

import pytest
from langchain_core.messages import ToolMessage

from backend.app.audit import sanitize_metadata, session_fingerprint
from backend.app.config import WebSettings
from backend.app.google_identity import validate_google_identity
from backend.app.tool_events import collect_run_metadata
from src import rag_tools
from src.auth.access import PolicyAccessGrant, policy_access_context
from src.auth.product_context import ProductContext, product_context
from src.rag.models import KnowledgeSearchRequest
from src.rag.retriever import HybridRetriever
from src.tools import escalate_case_tool, get_product_tool


def test_production_rejects_development_login(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEV_LOGIN_ENABLED", "true")
    monkeypatch.setenv("SESSION_SECRET", "x" * 32)

    with pytest.raises(ValueError, match="DEV_LOGIN_ENABLED"):
        WebSettings.from_env()


def test_google_oidc_defaults_to_google_issuer(monkeypatch):
    monkeypatch.setenv("GOOGLE_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("SESSION_SECRET", "x" * 32)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)

    settings = WebSettings.from_env()

    assert settings.oidc_issuer == "https://accounts.google.com"
    assert settings.oidc_enabled is True


def test_session_audit_fingerprint_never_contains_raw_session():
    raw_session = "opaque-session-value"
    fingerprint = session_fingerprint(raw_session, "secret")

    assert fingerprint == session_fingerprint(raw_session, "secret")
    assert raw_session not in fingerprint
    assert fingerprint != session_fingerprint(raw_session, "different-secret")


def test_audit_metadata_redacts_credentials_recursively():
    sanitized = sanitize_metadata(
        {"code": "oauth-code", "nested": {"id_token": "jwt", "reason": "denied"}}
    )

    assert sanitized == {
        "code": "[REDACTED]",
        "nested": {"id_token": "[REDACTED]", "reason": "denied"},
    }


def test_workspace_login_requires_google_hosted_domain_claim():
    with pytest.raises(ValueError, match="Workspace"):
        validate_google_identity(
            {
                "sub": "stable-google-subject",
                "email": "employee@example.com",
                "email_verified": True,
            },
            require_verified_email=True,
            allowed_email_domains=(),
            workspace_domains=("example.com",),
        )


def test_workspace_login_accepts_matching_hosted_domain():
    identity = validate_google_identity(
        {
            "sub": "stable-google-subject",
            "email": "employee@example.com",
            "email_verified": True,
            "hd": "example.com",
        },
        require_verified_email=True,
        allowed_email_domains=(),
        workspace_domains=("example.com",),
    )

    assert identity.subject == "stable-google-subject"
    assert identity.hosted_domain == "example.com"


def test_empty_access_grants_deny_policy_search():
    request = KnowledgeSearchRequest(query="환불 조건", access_grants=[])

    sql, _params = HybridRetriever._filters(
        request, datetime(2026, 9, 3, tzinfo=UTC)
    )

    assert "FALSE" in sql


def test_access_grants_remain_tuple_scoped_in_sql():
    request = KnowledgeSearchRequest(
        query="환불 조건",
        access_grants=[
            PolicyAccessGrant("compensation_policy", "KR", "CS"),
            PolicyAccessGrant("exception_policy", "US", "LEGAL"),
        ],
    )

    sql, params = HybridRetriever._filters(
        request, datetime(2026, 9, 3, tzinfo=UTC)
    )

    assert " OR " in sql
    assert params[2:] == [
        "compensation_policy",
        ["KR", "ALL_JURISDICTIONS"],
        ["CS", "ALL_DEPARTMENTS"],
        "exception_policy",
        ["US", "ALL_JURISDICTIONS"],
        ["LEGAL", "ALL_DEPARTMENTS"],
    ]


def test_rag_tool_injects_server_access_context(monkeypatch):
    captured = {}

    class FakeResponse:
        def model_dump(self, **_kwargs):
            return {"status": "no_evidence", "sources": []}

    class FakeRetriever:
        def search(self, request):
            captured["request"] = request
            return FakeResponse()

    monkeypatch.setattr(
        rag_tools,
        "get_internal_knowledge_retriever",
        lambda: FakeRetriever(),
    )
    grants = [PolicyAccessGrant("compensation_policy", "KR", "CS")]

    with policy_access_context(grants):
        rag_tools.search_internal_knowledge_tool.invoke({"query": "환불 조건"})

    assert captured["request"].access_grants == grants


def test_product_context_overrides_policy_tool_asin(monkeypatch):
    captured = {}

    class FakeResponse:
        def model_dump(self, **_kwargs):
            return {"status": "no_evidence", "sources": []}

    class FakeRetriever:
        def search(self, request):
            captured["request"] = request
            return FakeResponse()

    monkeypatch.setattr(
        rag_tools,
        "get_internal_knowledge_retriever",
        lambda: FakeRetriever(),
    )
    with product_context(ProductContext("B00FIXED001", "선택 상품")):
        rag_tools.search_internal_knowledge_tool.invoke(
            {"query": "환불 조건", "parent_asin": "B00OTHER001"}
        )

    assert captured["request"].parent_asin == "B00FIXED001"


def test_product_context_overrides_review_tool_asin(monkeypatch):
    captured = {}

    def fake_get_product(parent_asin):
        captured["parent_asin"] = parent_asin
        return {"parent_asin": parent_asin}

    monkeypatch.setattr("src.tools.get_product", fake_get_product)
    with product_context(ProductContext("B00FIXED001", "선택 상품")):
        result = get_product_tool.invoke({"parent_asin": "B00OTHER001"})

    assert captured["parent_asin"] == "B00FIXED001"
    assert result["parent_asin"] == "B00FIXED001"


def test_escalation_tool_returns_machine_readable_event():
    result = escalate_case_tool.invoke(
        {"reason": "고객이 피부 이상 반응을 신고함", "category": "medical"}
    )

    assert result["status"] == "escalation"
    assert result["category"] == "medical"


def test_tool_event_parser_accepts_langchain_stringified_dict():
    message = ToolMessage(
        name="search_internal_knowledge_tool",
        tool_call_id="call-1",
        content=str(
            {
                "status": "no_evidence",
                "sources": [],
            }
        ),
    )

    metadata = collect_run_metadata([message])

    assert metadata.status == "no_evidence"
