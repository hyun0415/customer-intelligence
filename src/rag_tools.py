from datetime import datetime
from functools import lru_cache

from langchain_core.tools import tool

from src.auth.access import get_policy_access_grants
from src.auth.product_context import get_product_context
from src.rag.models import KnowledgeSearchRequest
from src.rag.retriever import HybridRetriever


@lru_cache(maxsize=1)
def get_internal_knowledge_retriever() -> HybridRetriever:
    return HybridRetriever()


@tool
def search_internal_knowledge_tool(
    query: str,
    collections: list[str] | None = None,
    parent_asin: str | None = None,
    department: str | None = None,
    jurisdiction: str | None = None,
    effective_at: str | None = None,
    limit: int = 5,
):
    """
    사내 환불·재배송·보상·프로모션·제품 운영·CS SOP·예외 승인 정책을 검색한다.

    고객 리뷰나 리뷰 통계를 조회하는 도구가 아니다. 정책 적용 시점을 묻는 경우
    effective_at에 ISO 8601 날짜 또는 시각을 전달한다. 검색 결과의 status가
    no_evidence이면 정책을 추측하지 말고, policy_conflict이면 임의로 해결하지 않는다.
    """
    active_product = get_product_context()
    if active_product is not None:
        parent_asin = active_product.parent_asin
    parsed_effective_at = datetime.fromisoformat(effective_at) if effective_at else None
    request = KnowledgeSearchRequest(
        query=query,
        collections=collections,
        parent_asin=parent_asin,
        department=department,
        jurisdiction=jurisdiction,
        effective_at=parsed_effective_at,
        limit=limit,
        access_grants=get_policy_access_grants(),
    )
    return get_internal_knowledge_retriever().search(request).model_dump(mode="json")
