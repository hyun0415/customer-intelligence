import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from eval.failure_analysis import classify_agent_failures
from eval.rules.tool_checker import (
    check_expected_args,
    evaluate_required_tool_execution,
)
from src.agent import run_agent

from .questions import EVAL_CASES
from .rag_questions import RAG_EVAL_CASES

VALID_ASIN = "B00RWCDM4A"
INVALID_ASIN = "ZZZZZZZZZZ"

OUTPUT_DIR = Path("eval/results")


def get_messages(result):
    """LangGraph 결과에서 메시지 목록을 가져온다."""
    if isinstance(result, dict):
        return result.get("messages", [])

    return getattr(result, "messages", [])


def get_tool_names(result):
    """에이전트가 호출한 모든 도구 이름을 반환한다."""
    tool_names = []

    for message in get_messages(result):
        tool_calls = getattr(message, "tool_calls", None) or []

        for tool_call in tool_calls:
            name = tool_call.get("name")

            if name:
                tool_names.append(name)

    return tool_names

def serialize_tool_output(content):
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content

    return content

def get_tool_calls(result):
    """도구 이름과 인자를 저장 가능한 형태로 반환한다."""
    calls = []

    for message in get_messages(result):
        tool_calls = getattr(message, "tool_calls", None) or []

        for tool_call in tool_calls:
            calls.append(
                {
                    "name": tool_call.get("name"),
                    "args": tool_call.get("args", {}),
                }
            )

    return calls

def get_tool_outputs(result):
    outputs = []

    for message in get_messages(result):
        if getattr(message, "type", None) != "tool":
            continue

        outputs.append({
            "tool_name": getattr(message, "name", None),
            "tool_call_id": getattr(message, "tool_call_id", None),
            "output": serialize_tool_output(
                getattr(message, "content", "")
            ),
        })

    return outputs

def extract_text_content(content):
    if isinstance(content, str):
        return content.strip()

    if not isinstance(content, list):
        return ""

    texts = []

    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                text = block.get("text", "")

                if text:
                    texts.append(text)
        else:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "")

                if text:
                    texts.append(text)

    return "\n".join(texts).strip()


def get_final_answer(result):
    """마지막 AI 메시지의 답변을 반환한다."""
    for message in reversed(get_messages(result)):
        if getattr(message, "type", None) != "ai":
            continue

        answer = extract_text_content(
            getattr(message, "content", "")
        )

        if answer:
            return answer

    return ""

def evaluate_tool_usage(
    actual_tools,
    required_tools,
    forbidden_tools,
    any_of_tools=None,
):
    any_of_tools = any_of_tools or []

    missing_tools = [
        tool
        for tool in required_tools
        if tool not in actual_tools
    ]

    unexpected_tools = [
        tool
        for tool in forbidden_tools
        if tool in actual_tools
    ]

    alternative_tool_pass = (
        not any_of_tools
        or any(tool in actual_tools for tool in any_of_tools)
    )

    return {
        "tool_pass": (
            not missing_tools
            and not unexpected_tools
            and alternative_tool_pass
        ),
        "missing_tools": missing_tools,
        "unexpected_tools": unexpected_tools,
        "alternative_tool_pass": alternative_tool_pass,
    }


def run_case(case):
    question = case["question"].format(
        valid_asin=VALID_ASIN,
        invalid_asin=INVALID_ASIN,
    )

    print(f'[{case["id"]}] {question}')

    try:
        result = run_agent(question)
        actual_tools = get_tool_names(result)
        tool_calls = get_tool_calls(result)
        tool_outputs = get_tool_outputs(result)
        answer = get_final_answer(result)

        required_tools = case.get(
            "required_tools",
            case.get("expected_tools", []),
        )

        tool_selection = evaluate_tool_usage(
            actual_tools=actual_tools,
            required_tools=required_tools,
            forbidden_tools=case.get(
                "forbidden_tools",
                [],
            ),
            any_of_tools=case.get(
                "any_of_tools",
                [],
            ),
        )

        tool_selection_pass = tool_selection.pop("tool_pass")
        tool_execution = (
            evaluate_required_tool_execution(
                tool_outputs=tool_outputs,
                required_tools=required_tools,
            )
        )

        tool_execution_pass = tool_execution["tool_execution_pass"]

        tool_pass = (
            tool_selection_pass
            and tool_execution_pass
        )

        case_result = {
            **case,
            "question": question,
            "status": "completed",
            "actual_tools": actual_tools,
            "tool_calls": tool_calls,
            "tool_outputs": tool_outputs,
            "answer": answer,
            "tool_selection_pass": (tool_selection_pass),
            "tool_execution_pass": (tool_execution_pass),
            "tool_pass": tool_pass,
            **tool_selection,
            **tool_execution,
            "accuracy_score": "",
            "grounding_score": "",
            "analysis_score": "",
            "actionability_score": "",
            "total_score": "",
            "review_notes": "",
        }
        expected_args_pass, missing_expected_args = check_expected_args(case_result)
        case_result["expected_args_pass"] = expected_args_pass
        case_result["missing_expected_args"] = missing_expected_args
        case_result["failure_types"] = classify_agent_failures(case_result)
        return case_result

    except Exception as error:  # noqa: BLE001 - continue the suite and record the case failure
        case_result = {
            **case,
            "question": question,
            "status": "error",
            "actual_tools": [],
            "tool_calls": [],
            "tool_outputs": [],
            "answer": "",
            "tool_pass": False,
            "missing_tools": case.get(
                "required_tools",
                case.get("expected_tools", []),
            ),
            "unexpected_tools": [],
            "alternative_tool_pass": False,
            "accuracy_score": "",
            "grounding_score": "",
            "analysis_score": "",
            "actionability_score": "",
            "total_score": "",
            "review_notes": str(error),
            "tool_selection_pass": False,
            "tool_execution_pass": False,
            "missing_successful_tools": case.get(
                "required_tools",
                case.get("expected_tools", []),
            ),
            "failed_tool_executions": [],
        }
        case_result["expected_args_pass"] = not bool(case.get("expected_args"))
        case_result["missing_expected_args"] = []
        case_result["failure_types"] = classify_agent_failures(case_result)
        return case_result


def save_json(results, output_path):
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)


def save_csv(results, output_path):
    fieldnames = [
        "id",
        "category",
        "question",
        "evaluation_focus",
        "expected_tools",
        "required_tools",
        "any_of_tools",
        "forbidden_tools",
        "actual_tools",
        "tool_pass",
        "tool_selection_pass",
        "tool_execution_pass",
        "expected_args_pass",
        "missing_expected_args",
        "failure_types",
        "missing_successful_tools",
        "failed_tool_executions",
        "alternative_tool_pass",
        "missing_tools",
        "unexpected_tools",
        "status",
        "accuracy_score",
        "grounding_score",
        "analysis_score",
        "actionability_score",
        "total_score",
        "review_notes",
        "answer",
        "tool_calls",
        "tool_outputs",
    ]

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for result in results:
            row = {}

            for field in fieldnames:
                value = result.get(field, "")

                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)

                row[field] = value

            writer.writerow(row)


def print_summary(results):
    completed = sum(
        result["status"] == "completed"
        for result in results
    )
    tool_passed = sum(
        result["tool_pass"]
        for result in results
    )
    argument_cases = [result for result in results if result.get("expected_args")]
    argument_passed = sum(
        result.get("expected_args_pass", False) for result in argument_cases
    )

    print()
    print("평가 실행 완료")
    print(f"- 실행 완료: {completed}/{len(results)}")
    print(f"- 도구 선택 통과: {tool_passed}/{len(results)}")
    print(f"- 도구 인자 통과: {argument_passed}/{len(argument_cases)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        choices=("review", "policy", "all"),
        default="review",
        help="기존 review 15건, policy 결합 사례 또는 전체를 선택합니다.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    cases = {
        "review": EVAL_CASES,
        "policy": RAG_EVAL_CASES,
        "all": [*EVAL_CASES, *RAG_EVAL_CASES],
    }[args.suite]
    results = [run_case(case) for case in cases]

    json_path = OUTPUT_DIR / f"evaluation_{timestamp}.json"
    csv_path = OUTPUT_DIR / f"evaluation_{timestamp}.csv"

    save_json(results, json_path)
    save_csv(results, csv_path)
    print_summary(results)

    print(f"- JSON: {json_path}")
    print(f"- CSV: {csv_path}")


if __name__ == "__main__":
    main()
