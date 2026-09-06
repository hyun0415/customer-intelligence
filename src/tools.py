
from langchain_core.tools import tool

from src.analysis.review_patterns import build_review_patterns
from src.analysis.schemas import ReviewSelectionCriteria
from src.database import (
    compare_products,
    get_helpful_reviews,
    get_monthly_review_trend,
    get_negative_reviews,
    get_product,
    get_rating_distribution,
    get_recent_reviews,
    get_reviews_by_date,
    search_products,
)
from src.rag_tools import search_internal_knowledge_tool


@tool
def search_product_tool(keyword: str, limit: int = 5):
    """제품명이나 브랜드명으로 제품을 검색한다."""
    return search_products(keyword, limit)


@tool
def get_product_tool(parent_asin: str):
    """
    제품 ID로 제품 상세 정보와 리뷰 통계를 조회한다.

    주요 집계 필드:
    - rating_number: Amazon 상품 메타데이터에 표시된 전체 평점 수
    - review_count: 현재 분석 DB에 저장된 리뷰 수
    - negative_count: 분석 DB에서 평점 3점 이하인 리뷰 수
    - verified_count: 분석 DB에서 구매 인증된 리뷰 수
    """
    product = get_product(parent_asin)

    if product is None:
        return {}

    return product

@tool
def get_recent_reviews_tool(parent_asin: str, limit: int = 10):
    """특정 제품의 최신 리뷰를 조회한다."""
    return get_recent_reviews(parent_asin, limit)


@tool
def get_negative_reviews_tool(parent_asin: str, limit: int = 10):
    """특정 제품의 평점 3점 이하 부정·중립 리뷰를 최신순으로 조회한다."""
    return get_negative_reviews(parent_asin, limit)


@tool
def get_helpful_reviews_tool(
    parent_asin: str,
    limit: int = 10,
    rating_max: float | None = None,
    min_helpful_votes: int = 1,
):
    """특정 제품에서 공감 투표가 많은 리뷰를 조회한다."""
    return get_helpful_reviews(
        parent_asin=parent_asin,
        limit=limit,
        rating_max=rating_max,
        min_helpful_votes=min_helpful_votes,
    )


@tool
def get_rating_distribution_tool(parent_asin: str):
    """특정 제품의 1~5점 평점별 리뷰 수를 조회한다."""
    return get_rating_distribution(parent_asin)


@tool
def get_reviews_by_date_tool(
    parent_asin: str,
    start_at: str,
    end_at: str,
    limit: int = 20,
    rating_max: float | None = None,
    verified_only: bool = False,
):
    """특정 날짜 범위의 리뷰를 조회한다. 종료일은 포함하지 않는다."""
    return get_reviews_by_date(
        parent_asin=parent_asin,
        start_at=start_at,
        end_at=end_at,
        rating_max=rating_max,
        verified_only=verified_only,
        limit=limit,
    )


@tool
def get_monthly_review_trend_tool(
    parent_asin: str,
    start_at: str | None = None,
    end_at: str | None = None,
):
    """특정 제품의 월별 리뷰 수, 평균 평점, 부정 비율을 조회한다."""
    return get_monthly_review_trend(
        parent_asin=parent_asin,
        start_at=start_at,
        end_at=end_at,
    )


@tool
def compare_products_tool(parent_asins: list[str]):
    """여러 제품의 평점, 리뷰 수, 부정 비율 등 주요 지표를 비교한다."""
    return compare_products(parent_asins)

@tool
def get_review_patterns_tool(
    parent_asin: str,
    limit: int = 20,
):
    """
    주요 불만, 반복 불만, 불만 패턴, 개선 우선순위 또는
    고객 관점의 제품 강점·약점 분석에서
    약점의 반복성과 상대적 중요도를 확인할 때 사용한다.

    helpful_vote가 1 이상인 평점 3점 이하 리뷰를
    공감 투표 내림차순으로 조회하고,
    Aspect별 패턴과 표본 선정 기준을 반환한다.
    """
    rating_max = 3
    min_helpful_votes = 1

    reviews = get_helpful_reviews(
        parent_asin=parent_asin,
        rating_max=rating_max,
        min_helpful_votes=min_helpful_votes,
        limit=limit,
    )

    selection_criteria = ReviewSelectionCriteria(
        rating_max=rating_max,
        min_helpful_votes=min_helpful_votes,
        sort_by="helpful_vote_desc",
        requested_limit=limit,
    )

    return build_review_patterns(
        reviews=reviews,
        selection_criteria=selection_criteria,
    )


@tool
def escalate_case_tool(reason: str, category: str = "other"):
    """
    의료·안전 위험 또는 사람이 즉시 확인해야 하는 사안을 escalation한다.

    category는 medical, safety, policy_conflict, other 중 하나를 사용한다.
    이 도구는 요청을 표시하며, Web API가 로그인 사용자와 대화에 연결해 저장한다.
    """
    allowed = {"medical", "safety", "policy_conflict", "other"}
    if category not in allowed:
        raise ValueError(f"지원하지 않는 escalation category입니다: {category}")
    return {
        "status": "escalation",
        "category": category,
        "reason": reason,
    }


AGENT_TOOLS = [
    search_product_tool,
    get_product_tool,
    get_recent_reviews_tool,
    get_negative_reviews_tool,
    get_helpful_reviews_tool,
    get_rating_distribution_tool,
    get_reviews_by_date_tool,
    get_monthly_review_trend_tool,
    compare_products_tool,
    get_review_patterns_tool,
    search_internal_knowledge_tool,
    escalate_case_tool,
]


if __name__ == "__main__":
    print("도구 목록")

    for agent_tool in AGENT_TOOLS:
        print(
            f"- {agent_tool.name}: "
            f"{agent_tool.description}"
        )

    print("\nReview Pattern 테스트")

    result = get_review_patterns_tool.invoke(
        {
            "parent_asin": "B00RWCDM4A",
            "limit": 20,
        }
    )

    if hasattr(result, "model_dump"):
        result = result.model_dump()

    required_fields = {
        "sample_size",
        "extracted_review_count",
        "pattern_review_count",
        "patterns",
    }

    missing_fields = (
        required_fields - result.keys()
    )

    if missing_fields:
        raise AssertionError(
            "필수 결과 필드 누락: "
            f"{sorted(missing_fields)}"
        )

    print(
        f"- sample_size: "
        f"{result['sample_size']}"
    )
    print(
        f"- extracted_review_count: "
        f"{result['extracted_review_count']}"
    )
    print(
        f"- pattern_review_count: "
        f"{result['pattern_review_count']}"
    )
    print(
        f"- pattern_count: "
        f"{len(result['patterns'])}"
    )

    print("\n상위 Pattern")

    for pattern in result["patterns"][:5]:
        if not pattern["evidence"]:
            raise AssertionError(
                f"{pattern['topic']}의 evidence가 없습니다."
            )

        print(
            f"- {pattern['label']} "
            f"({pattern['topic']}): "
            f"count={pattern['count']}, "
            f"ratio={pattern['ratio']}, "
            f"confidence="
            f"{pattern['average_confidence']}"
        )

        for evidence in pattern["evidence"][:2]:
            print(
                f"  · review["
                f"{evidence['source_index']}]: "
                f"{evidence['evidence']}"
            )
