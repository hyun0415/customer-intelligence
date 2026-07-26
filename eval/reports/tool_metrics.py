import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def safe_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()

    return {str(item) for item in value if item not in ("", None)}


def divide(
    numerator: int,
    denominator: int,
) -> float:
    if denominator == 0:
        return 0.0

    return round(numerator / denominator, 4)


def calculate_f1(
    precision: float,
    recall: float,
) -> float:
    if precision + recall == 0:
        return 0.0

    return round(
        2 * precision * recall / (precision + recall),
        4,
    )


def get_required_tools(case: dict) -> set[str]:
    """
    반드시 호출해야 하는 Tool을 반환한다.

    required_tools가 없으면 기존 expected_tools를 사용한다.
    """
    required_tools = safe_set(case.get("required_tools", []))

    if required_tools:
        return required_tools

    return safe_set(case.get("expected_tools", []))


def evaluate_case_tools(case: dict) -> dict:

    required_tools = get_required_tools(case)
    alternative_tools = safe_set(case.get("any_of_tools", []))
    forbidden_tools = safe_set(case.get("forbidden_tools", []))
    actual_tools = safe_set(case.get("actual_tools", []))
    optional_tools = safe_set(case.get("optional_tools", []))

    true_positive_tools = required_tools & actual_tools
    missing_required_tools = required_tools - actual_tools
    alternative_called_tools = alternative_tools & actual_tools
    optional_called_tools = optional_tools & actual_tools
    alternative_pass = not alternative_tools or bool(alternative_called_tools)

    forbidden_called_tools = forbidden_tools & actual_tools
    explicitly_allowed_tools = (required_tools | alternative_tools | optional_tools)

    unlisted_tools = (actual_tools - explicitly_allowed_tools - forbidden_tools)
    supported_called_tools = (true_positive_tools | alternative_called_tools | (optional_tools & actual_tools))

    tool_pass = (
        not missing_required_tools and alternative_pass and not forbidden_called_tools
    )

    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "required_tools": sorted(required_tools),
        "alternative_tools": sorted(alternative_tools),
        "forbidden_tools": sorted(forbidden_tools),
        "actual_tools": sorted(actual_tools),
        "supported_called_tools": sorted(supported_called_tools),
        "true_positive_tools": sorted(true_positive_tools),
        "missing_required_tools": sorted(missing_required_tools),
        "alternative_called_tools": sorted(alternative_called_tools),
        "optional_called_tools": sorted(optional_called_tools),
        "alternative_pass": alternative_pass,
        "forbidden_called_tools": sorted(forbidden_called_tools),
        "unlisted_tools": sorted(unlisted_tools),
        "tool_pass": tool_pass,
    }


def initialize_tool_stats() -> dict:
    return {
        "required_count": 0,
        "alternative_expected_count": 0,
        "optional_expected_count": 0,
        "actual_count": 0,
        "required_true_positive": 0,
        "required_false_negative": 0,
        "alternative_selected_count": 0,
        "optional_selected_count": 0,
        "supported_call_count": 0,
        "forbidden_count": 0,
        "forbidden_called_count": 0,
        "unlisted_call_count": 0,
    }


def build_per_tool_metrics(
    results: list[dict],
) -> list[dict]:
    stats = defaultdict(initialize_tool_stats)
    total_cases = len(results)

    for case in results:

        required_tools = get_required_tools(case)
        alternative_tools = safe_set(case.get("any_of_tools", []))
        forbidden_tools = safe_set(case.get("forbidden_tools", []))
        actual_tools = safe_set(case.get("actual_tools", []))
        optional_tools = safe_set(case.get("optional_tools", []))

        allowed_tools = (required_tools | alternative_tools | optional_tools)
        all_tools = (required_tools | alternative_tools | optional_tools| forbidden_tools | actual_tools)

        for tool_name in all_tools:
            tool_stats = stats[tool_name]

            is_required = tool_name in required_tools
            is_alternative = tool_name in alternative_tools
            is_forbidden = tool_name in forbidden_tools
            is_called = tool_name in actual_tools
            is_optional = tool_name in optional_tools
            is_allowed = tool_name in allowed_tools

            if is_required:
                tool_stats["required_count"] += 1

                if is_called:
                    tool_stats["required_true_positive"] += 1
                else:
                    tool_stats["required_false_negative"] += 1

            if is_alternative:
                tool_stats["alternative_expected_count"] += 1

                if is_called:
                    tool_stats["alternative_selected_count"] += 1

            if is_optional:
                tool_stats["optional_expected_count"] += 1

                if is_called:
                    tool_stats["optional_selected_count"] += 1

            if is_forbidden:
                tool_stats["forbidden_count"] += 1

                if is_called:
                    tool_stats["forbidden_called_count"] += 1

            if not is_called:
                continue

            # 실제 호출은 케이스당 Tool별 한 번만 집계한다.
            tool_stats["actual_count"] += 1

            if is_allowed:
                tool_stats["supported_call_count"] += 1
            elif not is_forbidden:
                tool_stats["unlisted_call_count"] += 1
     
    rows = []

    for tool_name, tool_stats in stats.items():

        actual_count = tool_stats["actual_count"]
        required_count = tool_stats["required_count"]

        # 호출한 Tool이 required 또는 any_of로
        # 명시적으로 허용됐던 비율
        precision = divide(
            tool_stats["supported_call_count"],
            actual_count,
        )

        required_count = tool_stats["required_count"]

        # 반드시 호출해야 했던 상황에서의 재현율
        required_recall = (
            divide(
                tool_stats["required_true_positive"],
                required_count,
            )
            if required_count > 0
            else None
        )

        # any_of 후보로 제시된 상황 중
        # 실제로 이 Tool이 선택된 비율
        alternative_selection_rate = (
            divide(
                tool_stats["alternative_selected_count"],
                tool_stats["alternative_expected_count"],
            )
            if tool_stats["alternative_expected_count"] > 0
            else None
        )

        optional_selection_rate = (
            divide(
                tool_stats["optional_selected_count"],
                tool_stats["optional_expected_count"],
            )
            if tool_stats["optional_expected_count"] > 0
            else None
        )

        f1_score = (
            calculate_f1(precision, required_recall,)
            if required_recall is not None
            else None
        )

        unsupported_call_count = (tool_stats["forbidden_called_count"] + tool_stats["unlisted_call_count"])

        rows.append({
            "tool_name": tool_name,
            **tool_stats,
            "unsupported_call_count": (unsupported_call_count),
            "call_rate": divide(actual_count, total_cases),
            "precision": precision,
            "required_recall": required_recall,
            "f1_score": f1_score,
            "alternative_selection_rate": (alternative_selection_rate),
            "optional_selection_rate": (optional_selection_rate),
        })

    return sorted(rows, key=lambda row: row["tool_name"],)


def build_micro_metrics(
    case_metrics: list[dict],
) -> dict:
    supported_calls = sum(len(case["supported_called_tools"]) for case in case_metrics)
    actual_calls = sum(len(case["actual_tools"]) for case in case_metrics)

    required_true_positive = sum(
        len(case["true_positive_tools"]) for case in case_metrics
    )

    required_expected = sum(len(case["required_tools"]) for case in case_metrics)

    precision = divide(
        supported_calls,
        actual_calls,
    )

    required_recall = divide(
        required_true_positive,
        required_expected,
    )

    return {
        "supported_calls": supported_calls,
        "actual_calls": actual_calls,
        "required_true_positive": (required_true_positive),
        "required_expected": required_expected,
        "precision": precision,
        "required_recall": required_recall,
        "f1_score": calculate_f1(
            precision,
            required_recall,
        ),
    }


def calculate_macro_average(
    rows: list[dict],
    field: str,
) -> float:
    values = []

    for row in rows:
        value = row.get(field)

        if value in ("", None):
            continue

        numeric_value = float(value)

        if not 0.0 <= numeric_value <= 1.0:
            raise ValueError(
                f"{field} must be between 0 and 1: "
                f"tool={row.get('tool_name')}, "
                f"value={numeric_value}"
            )

        values.append(numeric_value)

    if not values:
        return 0.0

    return round(
        sum(values) / len(values),
        4,
    )


def build_optional_usage(
    case_metrics: list[dict],
) -> list[dict]:
    optional_usage = []

    for case in case_metrics:
        alternative_called = case.get(
            "alternative_called_tools",
            [],
        )

        unlisted_tools = case.get(
            "unlisted_tools",
            [],
        )

        if not alternative_called and not unlisted_tools:
            continue

        optional_usage.append(
            {
                "id": case.get("id"),
                "category": case.get("category"),
                "alternative_called_tools": (alternative_called),
                "unlisted_tools": unlisted_tools,
                "actual_tools": case.get(
                    "actual_tools",
                    [],
                ),
            }
        )

    return optional_usage


def build_tool_metrics(
    results: list[dict],
) -> dict:
    
    case_metrics = [evaluate_case_tools(case) for case in results]
    per_tool_metrics = build_per_tool_metrics(results)

    total_cases = len(case_metrics)
    tool_passed_cases = sum(case["tool_pass"] for case in case_metrics)
    alternative_cases = [case for case in case_metrics if case["alternative_tools"]]

    alternative_passed_cases = sum(
        case["alternative_pass"] for case in alternative_cases
    )

    forbidden_call_cases = sum(
        bool(case["forbidden_called_tools"]) for case in case_metrics
    )

    unlisted_call_cases = sum(bool(case["unlisted_tools"]) for case in case_metrics)
    optional_usage = build_optional_usage(case_metrics)

    return {
        "total_cases": total_cases,
        "tool_passed_cases": tool_passed_cases,
        "tool_pass_rate": divide(
            tool_passed_cases,
            total_cases,
        ),
        "alternative_cases": len(alternative_cases),
        "alternative_passed_cases": (alternative_passed_cases),
        "alternative_pass_rate": divide(
            alternative_passed_cases,
            len(alternative_cases),
        ),
        "forbidden_call_cases": (forbidden_call_cases),
        "forbidden_call_rate": divide(
            forbidden_call_cases,
            total_cases,
        ),
        "unlisted_call_cases": (unlisted_call_cases),
        "unlisted_call_rate": divide(
            unlisted_call_cases,
            total_cases,
        ),
        "micro_average": build_micro_metrics(case_metrics),
        "macro_average": {
            "precision": calculate_macro_average(
                per_tool_metrics,
                "precision",
            ),
            "required_recall": (
                calculate_macro_average(
                    [row for row in per_tool_metrics if row["required_count"] > 0],
                    "required_recall",
                )
            ),
            "f1_score": calculate_macro_average(
                [row for row in per_tool_metrics if row["required_count"] > 0],
                "f1_score",
            ),
        },
        "per_tool_metrics": per_tool_metrics,
        "optional_tool_usage": optional_usage,
        "case_metrics": case_metrics,
    }


def save_tool_metrics_json(
    metrics: dict,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metrics,
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

    if value is None:
        return ""

    return value


def save_tool_metrics_csv(
    per_tool_metrics: list[dict],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "tool_name",
        "required_count",
        "alternative_expected_count",
        "optional_expected_count",
        "actual_count",
        "call_rate",
        "required_true_positive",
        "required_false_negative",
        "alternative_selected_count",
        "optional_selected_count",
        "supported_call_count",
        "forbidden_count",
        "forbidden_called_count",
        "unlisted_call_count",
        "unsupported_call_count",
        "precision",
        "required_recall",
        "f1_score",
        "alternative_selection_rate",
        "optional_selection_rate",
    ]

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

        for row in per_tool_metrics:
            writer.writerow(
                {field: serialize_csv_value(row.get(field, "")) for field in fieldnames}
            )
