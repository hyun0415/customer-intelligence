import argparse
import csv
import json
from pathlib import Path
from typing import Any

from eval.evaluator.judge import LLMJudge
from eval.evaluator.runner import evaluate_cases


DEFAULT_RESULTS_DIR = Path("eval/results")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Agent 평가 결과 JSON을 LLM Judge로 자동 채점합니다."
        )
    )

    parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        help=(
            "채점할 evaluation JSON 파일 경로. "
            "생략하면 가장 최근 파일을 사용합니다."
        ),
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            "평가에 사용할 모델. 생략하면 "
            "EVALUATOR_MODEL 환경변수를 사용합니다."
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="이미 점수가 있는 항목도 다시 평가합니다.",
    )

    return parser.parse_args()


def find_latest_evaluation(
    results_dir: Path = DEFAULT_RESULTS_DIR,
) -> Path:
    candidates = [
        path
        for path in results_dir.glob("evaluation_*.json")
        if not path.name.startswith("judged_")
    ]

    if not candidates:
        raise FileNotFoundError(
            f"평가 JSON을 찾을 수 없습니다: {results_dir}"
        )

    return max(
        candidates,
        key=lambda path: path.stat().st_mtime,
    )


def load_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            "평가 JSON의 최상위 구조는 리스트여야 합니다."
        )

    return data


def save_json(
    results: list[dict],
    output_path: Path,
) -> None:
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            results,
            file,
            ensure_ascii=False,
            indent=2,
            default=str,
        )


def serialize_csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(
            value,
            ensure_ascii=False,
            default=str,
        )

    return value


def collect_fieldnames(
    results: list[dict],
) -> list[str]:
    preferred_fields = [
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
        "judge_status",
        "accuracy_score",
        "grounding_score",
        "analysis_score",
        "actionability_score",
        "total_score",
        "review_notes",

        # 새로 추가
        "rule_check",
        "raw_judge_scores",
        "score_adjustments",

        "answer",
        "tool_calls",
        "tool_outputs",
        "judge_error",
    ]
    
    discovered_fields = {
        key
        for result in results
        for key in result
    }

    ordered_fields = [
        field
        for field in preferred_fields
        if field in discovered_fields
    ]

    remaining_fields = sorted(
        discovered_fields - set(ordered_fields)
    )

    return ordered_fields + remaining_fields


def save_csv(
    results: list[dict],
    output_path: Path,
) -> None:
    fieldnames = collect_fieldnames(results)

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()

        for result in results:
            row = {
                field: serialize_csv_value(
                    result.get(field, "")
                )
                for field in fieldnames
            }
            writer.writerow(row)


def create_output_paths(
    input_path: Path,
) -> tuple[Path, Path]:
    base_name = input_path.stem

    json_path = input_path.with_name(
        f"judged_{base_name}.json"
    )
    csv_path = input_path.with_name(
        f"judged_{base_name}.csv"
    )

    return json_path, csv_path


def print_progress(
    result: dict,
    index: int,
    total: int,
) -> None:
    case_id = result.get("id", f"case-{index}")
    judge_status = result.get("judge_status", "unknown")
    total_score = result.get("total_score", "-")

    print(
        f"[{index}/{total}] "
        f"{case_id} | "
        f"{judge_status} | "
        f"score={total_score}"
    )


def print_summary(results: list[dict]) -> None:
    completed = [
        result
        for result in results
        if result.get("judge_status") == "completed"
    ]

    errors = [
        result
        for result in results
        if result.get("judge_status") == "error"
    ]

    print()
    print("LLM Judge 평가 완료")
    print(f"- 전체 사례: {len(results)}")
    print(f"- 채점 완료: {len(completed)}")
    print(f"- 채점 실패: {len(errors)}")

    if completed:
        score_fields = [
            "accuracy_score",
            "grounding_score",
            "analysis_score",
            "actionability_score",
            "total_score",
        ]

        for field in score_fields:
            values = [
                float(result[field])
                for result in completed
                if result.get(field) not in ("", None)
            ]

            if values:
                average = sum(values) / len(values)
                print(f"- 평균 {field}: {average:.2f}")


def main() -> None:
    args = parse_args()

    input_path = (
        args.input_path
        if args.input_path
        else find_latest_evaluation()
    )

    if not input_path.exists():
        raise FileNotFoundError(
            f"입력 파일을 찾을 수 없습니다: {input_path}"
        )

    print(f"입력 파일: {input_path}")

    cases = load_json(input_path)
    judge = LLMJudge(model=args.model)

    results = evaluate_cases(
        cases=cases,
        judge=judge,
        overwrite=args.overwrite,
        on_case_completed=print_progress,
    )

    json_path, csv_path = create_output_paths(input_path)

    save_json(results, json_path)
    save_csv(results, csv_path)
    print_summary(results)

    print(f"- JSON: {json_path}")
    print(f"- CSV: {csv_path}")


if __name__ == "__main__":
    main()