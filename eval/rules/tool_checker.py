from eval.evaluator.schemas import ToolCheckResult


def find_tool_call(
    tool_calls: list[dict],
    tool_name: str,
) -> dict | None:
    for tool_call in tool_calls:
        if tool_call.get("name") == tool_name:
            return tool_call

    return None


def check_expected_args(
    case: dict,
) -> tuple[bool, list[str]]:
    expected_args_by_tool = case.get("expected_args", {})

    if not expected_args_by_tool:
        return True, []

    tool_calls = case.get("tool_calls", [])
    missing = []

    for tool_name, expected_args in expected_args_by_tool.items():
        actual_call = find_tool_call(
            tool_calls,
            tool_name,
        )

        if actual_call is None:
            missing.append(
                f"{tool_name}: tool not called"
            )
            continue

        actual_args = actual_call.get("args", {})

        for arg_name, expected_value in expected_args.items():
            actual_value = actual_args.get(arg_name)

            if actual_value != expected_value:
                missing.append(
                    f"{tool_name}.{arg_name}: "
                    f"expected={expected_value!r}, "
                    f"actual={actual_value!r}"
                )

    return not missing, missing


def check_tool(case: dict) -> ToolCheckResult:
    tool_outputs_present = bool(
        case.get("tool_outputs", [])
    )

    tool_usage_pass = bool(
        case.get("tool_pass", False)
    )

    expected_args_pass, missing_expected_args = (
        check_expected_args(case)
    )

    notes = []

    if not tool_outputs_present:
        notes.append("도구 원본 출력이 없습니다.")

    if not tool_usage_pass:
        notes.append(
            "도구 선택 규칙을 통과하지 못했습니다."
        )

    if not expected_args_pass:
        notes.append(
            "요청된 Tool 인자가 정확히 전달되지 않았습니다."
        )

    return ToolCheckResult(
        tool_outputs_present=tool_outputs_present,
        tool_usage_pass=tool_usage_pass,
        expected_args_pass=expected_args_pass,
        missing_expected_args=missing_expected_args,
        notes=notes,
    )