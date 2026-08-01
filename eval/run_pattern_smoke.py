import json
from pathlib import Path

from eval.questions import EVAL_CASES
from eval.run_agent_evaluation import run_case


CASE_IDS = {"E05", "E08"}

OUTPUT_PATH = Path(
    "eval/results/evaluation_pattern_smoke.json"
)


def main():
    selected_cases = [
        case
        for case in EVAL_CASES
        if case["id"] in CASE_IDS
    ]

    results = [
        run_case(case)
        for case in selected_cases
    ]

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_PATH.write_text(
        json.dumps(
            results,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    for result in results:
        print()
        print(f"- case: {result['id']}")
        print(
            "- actual_tools: "
            f"{result['actual_tools']}"
        )
        print(
            "- tool_selection_pass: "
            f"{result['tool_selection_pass']}"
        )
        print(
            "- tool_execution_pass: "
            f"{result['tool_execution_pass']}"
        )
        print(
            "- tool_pass: "
            f"{result['tool_pass']}"
        )
        print(
            "- missing_successful_tools: "
            f"{result['missing_successful_tools']}"
        )
        print(
            "- failed_tool_executions: "
            f"{result['failed_tool_executions']}"
        )

    print()
    print(f"저장 완료: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()