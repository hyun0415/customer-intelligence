from eval.rules.answer_checker import check_answer
from eval.rules.numeric_checker import check_numbers
from eval.rules.tool_checker import check_tool

from .schemas import RuleCheckResult


def run_rule_checks(case: dict) -> RuleCheckResult:
    answer_result = check_answer(case)
    tool_result = check_tool(case)
    numeric_result = check_numbers(case)

    notes = [
        *answer_result.notes,
        *tool_result.notes,
        *numeric_result.notes,
    ]

    return RuleCheckResult(
        answer_present=answer_result.answer_present,
        tool_outputs_present=(
            tool_result.tool_outputs_present
        ),
        tool_usage_pass=tool_result.tool_usage_pass,
        expected_args_pass=(
            tool_result.expected_args_pass
        ),
        missing_expected_args=(
            tool_result.missing_expected_args
        ),
        unsupported_numbers=(
            numeric_result.unsupported_numbers
        ),
        rule_notes=notes,
    )