from typing import Literal

FailureType = Literal[
    "retrieval_miss",
    "rerank_error",
    "wrong_tool",
    "wrong_argument",
    "unsupported_claim",
    "false_no_evidence",
    "false_evidence",
    "access_violation",
    "runtime_error",
]


def classify_agent_failures(case: dict) -> list[FailureType]:
    failures: list[FailureType] = []
    if case.get("status") == "error":
        failures.append("runtime_error")
    if case.get("tool_selection_pass") is False:
        failures.append("wrong_tool")
    if case.get("expected_args") and case.get("expected_args_pass") is False:
        failures.append("wrong_argument")

    rule_check = case.get("rule_check") or {}
    if rule_check.get("unsupported_numbers"):
        failures.append("unsupported_claim")
    if not rule_check.get("policy_sources_pass", True) or not rule_check.get(
        "policy_rule_keys_pass", True
    ):
        failures.append("retrieval_miss")
    if not rule_check.get("policy_facts_pass", True):
        failures.append("unsupported_claim")
    if not rule_check.get("no_evidence_abstention_pass", True):
        failures.append("unsupported_claim")
    if not rule_check.get("policy_status_pass", True):
        if case.get("expected_status") == "no_evidence":
            failures.append("false_evidence")
        else:
            failures.append("false_no_evidence")
    return list(dict.fromkeys(failures))
