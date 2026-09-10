import json
from decimal import Decimal

from langchain_core.messages import AIMessage, ToolMessage

import src.tools as tools_module
from src.response_contract import (
    ResponseMode,
    apply_response_contract,
    render_rating_distribution,
    resolve_response_mode,
)


RATING_ROWS = [
    {"rating": 1.0, "review_count": 212},
    {"rating": 2.0, "review_count": 80},
    {"rating": 3.0, "review_count": 113},
    {"rating": 4.0, "review_count": 122},
    {"rating": 5.0, "review_count": 706},
]


def test_rating_renderer_uses_only_verified_counts():
    answer = render_rating_distribution(RATING_ROWS)

    assert answer is not None
    assert "1,233건" in answer
    assert "405건" in answer
    assert "32.8%" in answer
    assert "불만 원인·인과관계·안전성" in answer


def test_rating_tool_normalizes_database_numbers_for_json(monkeypatch):
    monkeypatch.setattr(
        tools_module,
        "get_rating_distribution",
        lambda parent_asin: [
            {"rating": Decimal("1.0"), "review_count": 2},
            {"rating": Decimal("5.0"), "review_count": 8},
        ],
    )

    result = tools_module.get_rating_distribution_tool.invoke(
        {"parent_asin": "B00TEST001"}
    )

    assert result == [
        {"rating": 1.0, "review_count": 2},
        {"rating": 5.0, "review_count": 8},
    ]
    json.dumps(result)


def test_sql_only_rating_answer_replaces_unverified_llm_analysis():
    result = {
        "messages": [
            ToolMessage(
                content=json.dumps(RATING_ROWS),
                tool_call_id="rating-call",
                name="get_rating_distribution_tool",
            ),
            AIMessage(
                content="탈모 부작용이 반복되므로 라벨 변경이 필요합니다."
            ),
        ]
    }

    guarded = apply_response_contract(result)
    answer = guarded["messages"][-1].content

    assert "32.8%" in answer
    assert "탈모" not in answer
    assert "라벨 변경" not in answer


def test_qualitative_tool_keeps_agent_synthesis():
    original = "검증된 Pattern 결과를 바탕으로 개선안을 설명합니다."
    result = {
        "messages": [
            ToolMessage(
                content=json.dumps(RATING_ROWS),
                tool_call_id="rating-call",
                name="get_rating_distribution_tool",
            ),
            ToolMessage(
                content=json.dumps({"patterns": []}),
                tool_call_id="pattern-call",
                name="get_review_patterns_tool",
            ),
            AIMessage(content=original),
        ]
    }

    guarded = apply_response_contract(result)

    assert guarded["messages"][-1].content == original


def test_unrelated_tool_result_is_not_modified():
    result = {
        "messages": [
            ToolMessage(
                content=json.dumps({"title": "상품"}),
                tool_call_id="product-call",
                name="get_product_tool",
            ),
            AIMessage(content="상품 정보입니다."),
        ]
    }

    assert apply_response_contract(result) == result


def test_rating_plus_product_detail_uses_analytical_mode():
    result = {
        "messages": [
            ToolMessage(
                content=json.dumps({"title": "상품"}),
                tool_call_id="product-call",
                name="get_product_tool",
            ),
            ToolMessage(
                content=json.dumps(RATING_ROWS),
                tool_call_id="rating-call",
                name="get_rating_distribution_tool",
            ),
            AIMessage(content="상품 정보와 평점 분포를 함께 설명합니다."),
        ]
    }

    assert resolve_response_mode(result["messages"]) is ResponseMode.ANALYTICAL
    assert apply_response_contract(result) == result


def test_rating_only_uses_deterministic_mode():
    messages = [
        ToolMessage(
            content=json.dumps(RATING_ROWS),
            tool_call_id="rating-call",
            name="get_rating_distribution_tool",
        )
    ]

    assert resolve_response_mode(messages) is ResponseMode.DETERMINISTIC


def test_repeated_rating_calls_use_analytical_mode():
    messages = [
        ToolMessage(
            content=json.dumps(RATING_ROWS),
            tool_call_id=f"rating-call-{index}",
            name="get_rating_distribution_tool",
        )
        for index in range(2)
    ]

    assert resolve_response_mode(messages) is ResponseMode.ANALYTICAL
