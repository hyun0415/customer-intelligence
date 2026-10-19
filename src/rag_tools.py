from datetime import datetime
from functools import lru_cache

from langchain_core.tools import tool

from src.auth.access import ALL_COLLECTIONS, get_policy_access_grants
from src.auth.product_context import get_product_context
from src.database import connect
from src.rag.models import ALL_DEPARTMENTS, ALL_JURISDICTIONS, KnowledgeSearchRequest
from src.rag.retriever import HybridRetriever


@lru_cache(maxsize=1)
def get_internal_knowledge_retriever() -> HybridRetriever:
    return HybridRetriever()


@tool
def get_policy_search_options_tool():
    """
    현재 사용자가 검색할 수 있는 정책의 Collection·관할·담당 부서 표준값을 조회한다.

    이 값은 정책의 저장 범위를 제한하는 필터다. 질문에 등장한 협업·보고 대상 부서를
    department로 추론하지 않는다. 사용자가 정책의 소유 부서나 적용 범위를 명시적으로
    제한할 때만 정책 검색 Tool의 필터로 사용한다.
    """
    grants = get_policy_access_grants()
    conditions = [
        "col.is_active",
        """
        EXISTS (
            SELECT 1
            FROM rag_document_versions v
            WHERE v.document_id = d.document_id
              AND v.approval_status = 'APPROVED'
        )
        """,
    ]
    params = []
    if grants is not None:
        if not grants:
            conditions.append("FALSE")
        else:
            grant_conditions = []
            for grant in grants:
                grant_parts = []
                if grant.collection != ALL_COLLECTIONS:
                    grant_parts.append("col.name = %s")
                    params.append(grant.collection)
                if grant.jurisdiction != ALL_JURISDICTIONS:
                    grant_parts.append("d.jurisdiction = ANY(%s)")
                    params.append([grant.jurisdiction, ALL_JURISDICTIONS])
                if grant.department != ALL_DEPARTMENTS:
                    grant_parts.append("d.department = ANY(%s)")
                    params.append([grant.department, ALL_DEPARTMENTS])
                grant_conditions.append(
                    "(" + " AND ".join(grant_parts or ["TRUE"]) + ")"
                )
            conditions.append("(" + " OR ".join(grant_conditions) + ")")

    query = f"""
        SELECT DISTINCT
            col.name AS collection,
            col.description AS collection_description,
            d.jurisdiction,
            d.department
        FROM rag_documents d
        JOIN rag_collections col ON col.collection_id = d.collection_id
        WHERE {' AND '.join(conditions)}
        ORDER BY col.name, d.jurisdiction, d.department
    """
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()

    collections = {
        row["collection"]: row["collection_description"] for row in rows
    }
    active_product = get_product_context()
    return {
        "collections": [
            {"value": name, "description": description}
            for name, description in sorted(collections.items())
        ],
        "jurisdictions": sorted({row["jurisdiction"] for row in rows}),
        "departments": sorted({row["department"] for row in rows}),
        "active_parent_asin": (
            active_product.parent_asin if active_product is not None else None
        ),
        "filter_guidance": {
            "department": (
                "정책 소유 부서를 명시적으로 제한할 때만 사용한다. "
                "질문에 등장한 보고·전달 대상 부서는 query에만 포함한다."
            ),
            "jurisdiction": "사용자가 적용 국가나 관할을 명시한 경우에만 사용한다.",
        },
    }


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
