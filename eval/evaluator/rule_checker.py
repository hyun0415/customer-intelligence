from eval.rules.answer_checker import check_answer
from eval.rules.numeric_checker import check_numbers
from eval.rules.policy_checker import check_policy_grounding
from eval.rules.tool_checker import check_tool

from .schemas import RuleCheckResult


def run_rule_checks(case: dict) -> RuleCheckResult:
    answer_result = check_answer(case)
    tool_result = check_tool(case)
    numeric_result = check_numbers(case)
    policy_result = check_policy_grounding(case)

    notes = [
        *answer_result.notes,
        *tool_result.notes,
        *numeric_result.notes,
        *policy_result.notes,
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
        policy_status_pass=policy_result.status_pass,
        policy_sources_pass=policy_result.sources_pass,
        policy_rule_keys_pass=policy_result.rule_keys_pass,
        policy_facts_pass=policy_result.facts_pass,
        no_evidence_abstention_pass=policy_result.no_evidence_abstention_pass,
        rule_notes=notes,
    )
