import json
from typing import Any

from .rubric import SCORE_RUBRIC


def to_pretty_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def build_judge_prompt(
    case: dict,
    rule_result: dict,
) -> str:
    return f"""
{SCORE_RUBRIC}

아래 Customer Intelligence Agent 실행 결과를 평가하라.

## 중요 지침

Python Rule Checker 결과는 보조 근거다.

- answer_present, tool_usage_pass, expected_args_pass는
  객관적인 규칙 검사 결과로 우선 신뢰한다.
- unsupported_numbers는 경고 후보이며 오류 확정이 아니다.
- 비율, 합계, 차이처럼 Tool 출력으로부터 올바르게 계산한 값은
  unsupported_numbers에 있어도 감점하지 않는다.
- 최종 판단은 질문, Tool 출력, Agent 답변을 함께 비교해 수행한다.

## 평가 사례

ID:
{case.get("id", "")}

카테고리:
{case.get("category", "")}

평가 목적:
{case.get("evaluation_focus", "")}

질문:
{case.get("question", "")}

## Python Rule Checker 결과

{to_pretty_json(rule_result)}

## Tool 사용 규칙

Expected tools:
{to_pretty_json(case.get("expected_tools", []))}

Required tools:
{to_pretty_json(case.get("required_tools", []))}

Any-of tools:
{to_pretty_json(case.get("any_of_tools", []))}

Forbidden tools:
{to_pretty_json(case.get("forbidden_tools", []))}

Tool pass:
{case.get("tool_pass", False)}

Missing tools:
{to_pretty_json(case.get("missing_tools", []))}

Unexpected tools:
{to_pretty_json(case.get("unexpected_tools", []))}

## 실제 Tool 호출

{to_pretty_json(case.get("tool_calls", []))}

## Tool 원본 출력

{to_pretty_json(case.get("tool_outputs", []))}

## Agent 최종 답변

{case.get("answer", "")}

제공된 자료만 사용하여 점수를 산출하라.
"""