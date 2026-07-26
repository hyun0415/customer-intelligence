from pathlib import Path


LOW_SCORE_THRESHOLD = 5.0


def append_list_section(
    lines: list[str],
    title: str,
    items: list[str],
) -> None:
    if not items:
        return

    lines.append(f"### {title}")
    lines.append("")

    for item in items:
        lines.append(f"- {item}")

    lines.append("")


def build_dashboard(
    results: list[dict],
    tool_metrics: dict | None = None,
) -> str:
    lines = [
        "# Evaluation Error Dashboard",
        "",
    ]

    low_score_cases = []

    for result in results:
        score = result.get("total_score")

        if score in ("", None):
            continue

        try:
            numeric_score = float(score)
        except (TypeError, ValueError):
            continue

        if numeric_score >= LOW_SCORE_THRESHOLD:
            continue

        low_score_cases.append(result)

    low_score_cases.sort(key=lambda result: float(result["total_score"]))

    lines.append(f"Total low-score cases: {len(low_score_cases)}")
    lines.append("")

    # 저점 사례 출력
    for result in low_score_cases:
        case_id = result.get("id", "unknown")
        category = result.get("category", "unknown")

        lines.append(f"## {case_id} - {category}")
        lines.append("")

        lines.append(f"- Total Score: {result.get('total_score', '')}")
        lines.append(f"- Accuracy: {result.get('accuracy_score', '')}")
        lines.append(f"- Grounding: {result.get('grounding_score', '')}")
        lines.append(f"- Analysis: {result.get('analysis_score', '')}")
        lines.append(f"- Actionability: {result.get('actionability_score', '')}")
        lines.append("")

        append_list_section(lines, "Strengths", result.get("strengths", []),)
        append_list_section(lines, "Problems", result.get("problems", []),)
        append_list_section(lines, "Evidence", result.get("evidence", []),)
        append_list_section(lines, "Suggestions", result.get("suggestions", []),)

        notes = str(result.get("review_notes", "")).strip()

        if notes:
            lines.append("### Summary")
            lines.append("")
            lines.append(notes)
            lines.append("")

        append_list_section(
            lines,
            "Rule Adjustments",
            result.get("score_adjustments", []),
        )

        lines.append("---")
        lines.append("")

    # 중요: 이 부분은 위 for문이 완전히 끝난 뒤 실행
    optional_usage = tool_metrics.get("optional_tool_usage", []) if tool_metrics else []

    if optional_usage:
        lines.append("# Optional Tool Usage")
        lines.append("")
        lines.append("평가 기준의 대안 Tool 또는 명시되지 않은 추가 Tool 호출입니다.")
        lines.append("")

        for usage in optional_usage:
            case_id = usage.get("id", "unknown")
            category = usage.get("category", "unknown")

            lines.append(f"## {case_id} - {category}")
            lines.append("")

            alternative_called = usage.get("alternative_called_tools", [],)
            unlisted_tools = usage.get("unlisted_tools", [],)

            append_list_section(lines, "Selected Alternative Tools", alternative_called,)
            append_list_section(lines, "Unlisted Additional Tools", unlisted_tools,)
            append_list_section(lines, "All Called Tools", usage.get("actual_tools", []),)

            lines.append("---")
            lines.append("")

    return "\n".join(lines)


def save_dashboard(
    markdown: str,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        markdown,
        encoding="utf-8",
    )
