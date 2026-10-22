from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from src.rag.config import ALL_DEPARTMENTS, ALL_JURISDICTIONS

ALL_COLLECTIONS = "ALL_COLLECTIONS"


@dataclass(frozen=True)
class PolicyAccessGrant:
    collection: str
    jurisdiction: str
    department: str


def policy_source_is_allowed(
    metadata: dict, grants: list[PolicyAccessGrant]
) -> bool:
    """저장된 정책 근거를 현재 사용자의 접근 범위로 다시 확인한다."""
    for grant in grants:
        collection_allowed = (
            grant.collection == ALL_COLLECTIONS
            or grant.collection == metadata.get("collection")
        )
        jurisdiction_allowed = (
            grant.jurisdiction == ALL_JURISDICTIONS
            or metadata.get("jurisdiction")
            in {grant.jurisdiction, ALL_JURISDICTIONS}
        )
        department_allowed = (
            grant.department == ALL_DEPARTMENTS
            or metadata.get("department")
            in {grant.department, ALL_DEPARTMENTS}
        )
        if collection_allowed and jurisdiction_allowed and department_allowed:
            return True
    return False


_policy_access_grants: ContextVar[tuple[PolicyAccessGrant, ...] | None] = (
    ContextVar("policy_access_grants", default=None)
)


def get_policy_access_grants() -> tuple[PolicyAccessGrant, ...] | None:
    """현재 요청에 서버가 부여한 정책 접근 범위를 반환한다."""
    return _policy_access_grants.get()


@contextmanager
def policy_access_context(
    grants: list[PolicyAccessGrant] | tuple[PolicyAccessGrant, ...],
) -> Iterator[None]:
    token = _policy_access_grants.set(tuple(grants))
    try:
        yield
    finally:
        _policy_access_grants.reset(token)
