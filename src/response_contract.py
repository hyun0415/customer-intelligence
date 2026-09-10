import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage


class ResponseMode(StrEnum):
    """Agent 응답에서 코드와 LLM이 각각 책임지는 범위다."""

    DETERMINISTIC = "deterministic"
    ANALYTICAL = "analytical"


Renderer = Callable[[Any], str | None]


@dataclass(frozen=True)
class DeterministicContract:
    """단독 호출 시 Tool 결과만으로 확정할 수 있는 응답 계약이다."""

    renderer: Renderer


def _json_content(content: Any) -> Any | None:
    if isinstance(content, (dict, list)):
        return content
    if not isinstance(content, str):
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _rating_counts(payload: Any) -> dict[int, int] | None:
    if not isinstance(payload, list):
        return None

    counts: dict[int, int] = {}
    for row in payload:
        if not isinstance(row, Mapping):
            return None
        try:
            rating = float(row["rating"])
            count = int(row["review_count"])
        except (KeyError, TypeError, ValueError):
            return None
        if not rating.is_integer() or not 1 <= rating <= 5 or count < 0:
            return None
        counts[int(rating)] = count

    return counts if counts else None


def render_rating_distribution(payload: Any) -> str | None:
    """검증된 평점 집계만 사용해 결정론적인 Markdown 답변을 만든다."""
    counts = _rating_counts(payload)
    if counts is None:
        return None

    total = sum(counts.values())
    if total <= 0:
        return "현재 분석 DB에서 해당 상품의 평점 리뷰를 찾지 못했습니다."

    table_rows = []
    for rating in range(5, 0, -1):
        count = counts.get(rating, 0)
        ratio = count / total * 100
        table_rows.append(f"| {rating}점 | {count:,}건 | {ratio:.1f}% |")

    negative_count = sum(counts.get(rating, 0) for rating in range(1, 4))
    negative_ratio = negative_count / total * 100

    return "\n".join(
        [
            "### 평점 분포",
            "",
            f"현재 분석 DB에 저장된 리뷰 **{total:,}건** 기준입니다.",
            "",
            "| 평점 | 리뷰 수 | 비율 |",
            "|---:|---:|---:|",
            *table_rows,
            f"| **합계** | **{total:,}건** | **100.0%** |",
            "",
            (
                f"저평점(1~3점)은 **{negative_count:,}건**, "
                f"전체 표본의 **{negative_ratio:.1f}%**입니다."
            ),
            "",
            (
                "리뷰 본문 분석 Tool은 실행되지 않았으므로 "
                "불만 원인·인과관계·안전성은 이 결과에서 판단하지 않았습니다."
            ),
        ]
    )


DETERMINISTIC_CONTRACTS = {
    "get_rating_distribution_tool": DeterministicContract(
        renderer=render_rating_distribution
    ),
}


def _tool_outputs(messages: list[Any]) -> list[tuple[str, Any]]:
    outputs: list[tuple[str, Any]] = []
    for message in messages:
        if isinstance(message, ToolMessage) and message.name:
            outputs.append((message.name, _json_content(message.content)))
    return outputs


def resolve_response_mode(messages: list[Any]) -> ResponseMode:
    """단일 결정론 Tool만 호출된 경우에만 코드 렌더링을 허용한다."""
    outputs = _tool_outputs(messages)
    if len(outputs) == 1 and outputs[0][0] in DETERMINISTIC_CONTRACTS:
        return ResponseMode.DETERMINISTIC
    return ResponseMode.ANALYTICAL


def apply_response_contract(result: dict[str, Any]) -> dict[str, Any]:
    """정형 단독 조회는 코드가 확정하고, 복합 해석은 LLM 응답을 유지한다."""
    messages = list(result.get("messages", []))
    if resolve_response_mode(messages) is ResponseMode.ANALYTICAL:
        return result

    tool_name, output = _tool_outputs(messages)[0]
    rendered = DETERMINISTIC_CONTRACTS[tool_name].renderer(
        output
    )
    if (
        rendered is None
        or not messages
        or not isinstance(messages[-1], AIMessage)
    ):
        return result

    contracted_messages = list(messages)
    contracted_messages[-1] = messages[-1].model_copy(
        update={"content": rendered}
    )
    return {**result, "messages": contracted_messages}
