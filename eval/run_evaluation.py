import csv
import json
from datetime import datetime
from pathlib import Path

from .questions import EVAL_CASES

# tests/test_agent.py에서 사용하는 실제 import 경로로 수정
from src.agent import run_agent


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

        tool_evaluation = evaluate_tool_usage(
            actual_tools=actual_tools,
            required_tools=case.get(
                "required_tools",
                case.get("expected_tools", []),
            ),
            forbidden_tools=case.get("forbidden_tools", []),
            any_of_tools=case.get("any_of_tools", []),
        )

        return {
            **case,
            "question": question,
            "status": "completed",
            "actual_tools": actual_tools,
            "tool_calls": tool_calls,
            "tool_outputs": tool_outputs,
            "answer": answer,
            **tool_evaluation,
            # 아래 항목은 답변을 확인한 뒤 수동 입력
            "accuracy_score": "",
            "grounding_score": "",
            "analysis_score": "",
            "actionability_score": "",
            "total_score": "",
            "review_notes": "",
        }

    except Exception as error:
        return {
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
        }


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
        "alternative_tool_pass",
        "missing_tools",
        "unexpected_tools",
        "status",
        "accuracy_score",
        "analysis_score",
        "actionability_score",
        "total_score",
        "review_notes",
        "answer",
        "tool_calls",
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

    print()
    print("평가 실행 완료")
    print(f"- 실행 완료: {completed}/{len(results)}")
    print(f"- 도구 선택 통과: {tool_passed}/{len(results)}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = [run_case(case) for case in EVAL_CASES]

    json_path = OUTPUT_DIR / f"evaluation_{timestamp}.json"
    csv_path = OUTPUT_DIR / f"evaluation_{timestamp}.csv"

    save_json(results, json_path)
    save_csv(results, csv_path)
    print_summary(results)

    print(f"- JSON: {json_path}")
    print(f"- CSV: {csv_path}")


if __name__ == "__main__":
    main()