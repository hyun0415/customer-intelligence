from eval.evaluator.schemas import ToolCheckResult

def is_tool_execution_error(
    output,
) -> bool:
    """
    LangChain ToolMessage에 저장된 실행 오류인지 확인한다.
    """
    if isinstance(output, dict):
        if output.get("error"):
            return True

        status = str(
            output.get("status", "")
        ).lower()

        return status in {
            "error",
            "failed",
            "failure",
        }

    if not isinstance(output, str):
        return False

    normalized = output.strip().lower()

    return (
        normalized.startswith(
            "error invoking tool"
        )
        or normalized.startswith("error:")
        or (
            "please fix the error "
            "and try again"
            in normalized
        )
    )


def evaluate_required_tool_execution(
    tool_outputs: list[dict],
    required_tools: list[str],
) -> dict:
    """
    필수 Tool이 한 번 이상 정상 결과를 반환했는지 검사한다.
    """
    successful_tools: set[str] = set()
    failed_executions = []

    for tool_output in tool_outputs:
        tool_name = tool_output.get(
            "tool_name"
        )

        if tool_name not in required_tools:
            continue

        output = tool_output.get("output")

        if is_tool_execution_error(output):
            failed_executions.append(
                {
                    "tool_name": tool_name,
                    "error": str(output)[:500],
                }
            )
            continue

        successful_tools.add(tool_name)

    missing_successful_tools = [
        tool_name
        for tool_name in required_tools
        if tool_name not in successful_tools
    ]

    return {
        "tool_execution_pass": (
            not missing_successful_tools
        ),
        "missing_successful_tools": (
            missing_successful_tools
        ),
        "failed_tool_executions": (
            failed_executions
        ),
    }


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
            "필수 도구의 선택 또는 실행 규칙을 "
            "통과하지 못했습니다."
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