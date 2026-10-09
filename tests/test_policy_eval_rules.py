from eval.evaluator.rule_checker import run_rule_checks
from eval.evaluator.runner import apply_rule_caps
from eval.evaluator.schemas import RuleCheckResult
from eval.failure_analysis import classify_agent_failures


def policy_case():
    return {
        "status": "completed",
        "answer": "무료 재배송은 1회입니다.",
        "tool_pass": True,
        "tool_calls": [
            {"name": "search_internal_knowledge_tool", "args": {"limit": 5}}
        ],
        "tool_outputs": [
            {
                "tool_name": "search_internal_knowledge_tool",
                "output": {
                    "status": "ok",
                    "sources": [
                        {
                            "source_id": "reship",
                            "rule_keys": ["reshipment_policy:2"],
                            "content": "무료 재배송은 1회로 제한한다.",
                        }
                    ],
                },
            }
        ],
        "expected_status": "ok",
        "expected_source_ids": ["reship"],
        "expected_rule_keys": ["reshipment_policy:2"],
        "expected_facts": ["무료 재배송은 1회"],
    }


def test_policy_rule_checker_verifies_status_source_rule_and_fact():
    result = run_rule_checks(policy_case())

    assert result.policy_status_pass is True
    assert result.policy_sources_pass is True
    assert result.policy_rule_keys_pass is True
    assert result.policy_facts_pass is True


def test_policy_rule_checker_classifies_missing_grounding():
    case = policy_case()
    case["expected_facts"] = ["무료 재배송은 2회"]
    rule_result = run_rule_checks(case)
    case["rule_check"] = rule_result.model_dump()

    assert rule_result.policy_facts_pass is False
    assert "unsupported_claim" in classify_agent_failures(case)


def test_no_evidence_requires_explicit_abstention_language():
    case = policy_case()
    case["expected_status"] = "no_evidence"
    case["expected_source_ids"] = []
    case["expected_rule_keys"] = []
    case["expected_facts"] = []
    case["answer"] = "현금 보상이 승인됩니다."
    case["tool_outputs"][0]["output"] = {
        "status": "no_evidence",
        "sources": [],
    }

    result = run_rule_checks(case)

    assert result.no_evidence_abstention_pass is False


def test_policy_failure_caps_grounding_without_numeric_adjustment():
    scores, adjustments = apply_rule_caps(
        {
            "accuracy_score": 5,
            "grounding_score": 5,
            "analysis_score": 5,
            "actionability_score": 5,
        },
        RuleCheckResult(
            answer_present=True,
            tool_outputs_present=True,
            tool_usage_pass=True,
            expected_args_pass=True,
            policy_facts_pass=False,
        ),
    )

    assert scores["accuracy_score"] == 5
    assert scores["grounding_score"] == 2
    assert len(adjustments) == 1
