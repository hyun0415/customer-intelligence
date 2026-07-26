import re
import pytest
from langchain_core.messages import AIMessage
from src.agent import extract_text, run_agent


VALID_ASIN = "B005IHT8KI"
INVALID_ASIN = "ZZZZZZZZZZ"

pytestmark = pytest.mark.integration


def get_tool_calls(result):
    """에이전트 실행 메시지에서 모든 도구 호출을 추출한다."""
    tool_calls = []

    for message in result["messages"]:
        if isinstance(message, AIMessage):
            tool_calls.extend(message.tool_calls)

    return tool_calls


def get_tool_names(result):
    return [call["name"] for call in get_tool_calls(result)]


def find_tool_call(result, tool_name):
    return [
        call
        for call in get_tool_calls(result)
        if call["name"] == tool_name
    ]


def get_final_answer(result):
    return extract_text(result["messages"][-1].content)


def test_asin_question_uses_required_tools_without_search():
    """ASIN이 명시된 분석 질문은 제품 검색 없이 필요한 조회 도구를 사용한다."""
    result = run_agent(
        f"""
        ASIN {VALID_ASIN} 제품의 전체 리뷰 통계를 확인하고,
        helpful_vote가 높은 3점 이하 리뷰 20개를 조회해서
        주요 불만 3가지를 분석해줘.
        """
    )

    tool_names = get_tool_names(result)

    assert "search_product_tool" not in tool_names
    assert "get_product_tool" in tool_names
    assert "get_helpful_reviews_tool" in tool_names
    assert "get_rating_distribution_tool" in tool_names


def test_helpful_review_filter_arguments_are_correct():
    """자연어 조건이 올바른 도구 인자로 변환되어야 한다."""
    result = run_agent(
        f"""
        ASIN {VALID_ASIN}에서 helpful_vote가 1 이상인
        3점 이하 리뷰를 공감 투표 순으로 20개 조회해줘.
        """
    )

    calls = find_tool_call(result, "get_helpful_reviews_tool")

    assert calls, "get_helpful_reviews_tool이 호출되지 않았습니다."

    args = calls[0]["args"]

    assert args["parent_asin"] == VALID_ASIN
    assert args["rating_max"] == 3
    assert args["min_helpful_votes"] == 1
    assert args["limit"] == 20


def test_product_name_without_asin_uses_search_tool():
    """제품명만 주어지면 먼저 제품 검색 도구를 호출해야 한다."""
    result = run_agent(
        "Neutrogena Anti-Residue Shampoo 제품을 찾아서 후보를 보여줘."
    )

    calls = find_tool_call(result, "search_product_tool")

    assert calls, "제품명이 주어졌지만 검색 도구가 호출되지 않았습니다."
    assert "Neutrogena" in calls[0]["args"]["keyword"]


def test_invalid_asin_is_handled_naturally():
    """존재하지 않는 ASIN에서 최종 답변을 생성하고 제품이 없음을 안내한다."""
    result = run_agent(
        f"ASIN {INVALID_ASIN} 제품의 상세 정보와 리뷰 통계를 알려줘."
    )

    tool_names = get_tool_names(result)
    answer = get_final_answer(result)

    assert "get_product_tool" in tool_names
    assert answer.strip()

    expected_expressions = [
        "찾을 수 없",
        "존재하지 않",
        "확인되지 않",
        "조회되지 않",
        "검색 결과가 없",
        "반환되지 않",
    ]

    assert any(expression in answer for expression in expected_expressions), (
        f"제품이 없다는 안내가 명확하지 않습니다: {answer}"
    )

    import re


def test_requested_review_count_is_passed_as_limit():
    """사용자가 요청한 리뷰 개수가 limit 인자로 정확히 전달되어야 한다."""
    result = run_agent(
        f"""
        ASIN {VALID_ASIN}에서 helpful_vote가 1 이상인
        3점 이하 리뷰를 7개 조회해줘.
        """
    )

    calls = find_tool_call(result, "get_helpful_reviews_tool")

    assert calls, "get_helpful_reviews_tool이 호출되지 않았습니다."

    args = calls[0]["args"]

    assert args["parent_asin"] == VALID_ASIN
    assert args["limit"] == 7
    assert args["rating_max"] == 3
    assert args["min_helpful_votes"] == 1

def test_rating_max_is_not_added_without_rating_condition():
    """평점 조건이 없으면 rating_max를 임의로 설정하지 않아야 한다."""
    result = run_agent(
        f"""
        ASIN {VALID_ASIN}에서 helpful_vote가 높은 리뷰를
        평점 제한 없이 10개 조회해줘.
        """
    )

    calls = find_tool_call(result, "get_helpful_reviews_tool")

    assert calls, "get_helpful_reviews_tool이 호출되지 않았습니다."

    args = calls[0]["args"]

    assert args["parent_asin"] == VALID_ASIN
    assert args["limit"] == 10
    assert args.get("rating_max") is None

def test_simple_product_detail_does_not_call_review_tools():
    """단순 제품 상세 조회에서는 리뷰 관련 도구를 호출하지 않아야 한다."""
    result = run_agent(
        f"""
        ASIN {VALID_ASIN} 제품의 제목, 브랜드, 가격과
        기본 제품 정보만 알려줘. 리뷰 분석은 하지 마.
        """
    )

    tool_names = get_tool_names(result)

    assert "get_product_tool" in tool_names
    assert "search_product_tool" not in tool_names
    assert "get_helpful_reviews_tool" not in tool_names
    assert "get_rating_distribution_tool" not in tool_names

def test_ambiguous_product_name_returns_multiple_candidates():
    """모호한 제품명은 검색한 뒤 여러 후보를 제시해야 한다."""
    result = run_agent(
        """
        shampoo 제품을 찾아줘.
        하나를 임의로 선택하지 말고 관련 후보를 여러 개 보여줘.
        """
    )

    search_calls = find_tool_call(result, "search_product_tool")
    answer = get_final_answer(result)

    assert search_calls, "search_product_tool이 호출되지 않았습니다."
    assert "shampoo" in search_calls[0]["args"]["keyword"].lower()

    # 답변에 서로 다른 ASIN 후보가 최소 2개 포함되는지 확인한다.
    asins = set(re.findall(r"\bB[A-Z0-9]{9}\b", answer.upper()))

    assert len(asins) >= 2, (
        "여러 제품 후보가 제시되지 않았습니다.\n"
        f"발견된 ASIN: {sorted(asins)}\n"
        f"최종 답변: {answer}"
    )