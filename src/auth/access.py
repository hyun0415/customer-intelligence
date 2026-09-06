from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

ALL_COLLECTIONS = "ALL_COLLECTIONS"


@dataclass(frozen=True)
class PolicyAccessGrant:
    collection: str
    jurisdiction: str
    department: str


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
