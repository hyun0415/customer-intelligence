from collections import Counter
from pathlib import Path
from typing import Any

import json


SCORE_FIELDS = [
    "accuracy_score",
    "grounding_score",
    "analysis_score",
    "actionability_score",
    "total_score",
]


def get_numeric_values(
    results: list[dict],
    field: str,
) -> list[float]:
    values = []

    for result in results:
        value = result.get(field)

        if value in ("", None):
            continue

        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue

    return values


def calculate_average(
    results: list[dict],
    field: str,
) -> float | None:
    values = get_numeric_values(results, field)

    if not values:
        return None

    return round(sum(values) / len(values), 2)


def calculate_rate(
    numerator: int,
    denominator: int,
) -> float:
    if denominator == 0:
        return 0.0

    return round(numerator / denominator, 4)


def build_score_distribution(
    results: list[dict],
) -> dict[str, int]:
    distribution = Counter()

    for result in results:
        score = result.get("total_score")

        if score in ("", None):
            continue

        try:
            normalized_score = f"{float(score):.2f}"
        except (TypeError, ValueError):
            continue

        distribution[normalized_score] += 1

    return dict(
        sorted(
            distribution.items(),
            key=lambda item: float(item[0]),
            reverse=True,
        )
    )


def build_category_summary(
    results: list[dict],
) -> dict[str, dict[str, Any]]:
    categories: dict[str, list[dict]] = {}

    for result in results:
        category = result.get("category", "unknown")
        categories.setdefault(category, []).append(result)

    summary = {}

    for category, category_results in categories.items():
        completed = [
            result
            for result in category_results
            if result.get("judge_status") == "completed"
        ]

        summary[category] = {
            "total_cases": len(category_results),
            "completed_cases": len(completed),
            "average_total_score": calculate_average(
                completed,
                "total_score",
            ),
            "average_accuracy_score": calculate_average(
                completed,
                "accuracy_score",
            ),
            "average_grounding_score": calculate_average(
                completed,
                "grounding_score",
            ),
            "average_analysis_score": calculate_average(
                completed,
                "analysis_score",
            ),
            "average_actionability_score": calculate_average(
                completed,
                "actionability_score",
            ),
        }

    return summary


def build_low_score_cases(
    results: list[dict],
    threshold: float = 5.0,
) -> list[dict]:
    low_score_cases = []

    for result in results:
        total_score = result.get("total_score")

        if total_score in ("", None):
            continue

        try:
            score = float(total_score)
        except (TypeError, ValueError):
            continue

        if score >= threshold:
            continue

        low_score_cases.append({
            "id": result.get("id"),
            "category": result.get("category"),
            "total_score": score,
            "accuracy_score": result.get("accuracy_score"),
            "grounding_score": result.get("grounding_score"),
            "analysis_score": result.get("analysis_score"),
            "actionability_score": result.get(
                "actionability_score"
            ),
            "review_notes": result.get("review_notes", ""),
            "score_adjustments": result.get(
                "score_adjustments",
                [],
            ),
        })

    return sorted(
        low_score_cases,
        key=lambda case: case["total_score"],
    )


def build_summary(
    results: list[dict],
) -> dict:
    total_cases = len(results)

    completed_cases = sum(
        result.get("judge_status") == "completed"
        for result in results
    )

    error_cases = sum(
        result.get("judge_status") == "error"
        for result in results
    )

    skipped_cases = sum(
        result.get("judge_status") == "skipped"
        for result in results
    )

    tool_passed_cases = sum(
        bool(result.get("tool_pass", False))
        for result in results
    )

    rule_adjusted_cases = sum(
        bool(result.get("score_adjustments", []))
        for result in results
    )

    average_scores = {
        field: calculate_average(results, field)
        for field in SCORE_FIELDS
    }

    return {
        "total_cases": total_cases,
        "completed_cases": completed_cases,
        "error_cases": error_cases,
        "skipped_cases": skipped_cases,
        "completion_rate": calculate_rate(
            completed_cases,
            total_cases,
        ),
        "tool_passed_cases": tool_passed_cases,
        "tool_pass_rate": calculate_rate(
            tool_passed_cases,
            total_cases,
        ),
        "rule_adjusted_cases": rule_adjusted_cases,
        "rule_adjustment_rate": calculate_rate(
            rule_adjusted_cases,
            completed_cases,
        ),
        "average_scores": average_scores,
        "score_distribution": build_score_distribution(results),
        "category_summary": build_category_summary(results),
        "low_score_cases": build_low_score_cases(results),
    }


def save_summary(
    summary: dict,
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
            summary,
            file,
            ensure_ascii=False,
            indent=2,
            default=str,
        )