from eval.rag_questions import RAG_EVAL_CASES
from src.prompts import SYSTEM_PROMPT
from src.tools import AGENT_TOOLS


def test_rag_prompt_contains_no_evidence_and_conflict_guards():
    assert "no_evidence" in SYSTEM_PROMPT
    assert "policy_conflict" in SYSTEM_PROMPT
    assert "고객 리뷰 근거" in SYSTEM_PROMPT
    assert "내부 정책 근거" in SYSTEM_PROMPT
    assert "정책이 없다" in SYSTEM_PROMPT
    assert "충분히 관련된 근거를 찾지 못했다" in SYSTEM_PROMPT
    assert "의료·안전 문제" in SYSTEM_PROMPT


def test_rag_evaluation_cases_reference_registered_tools():
    registered = {agent_tool.name for agent_tool in AGENT_TOOLS}
    for case in RAG_EVAL_CASES:
        assert set(case["required_tools"]).issubset(registered)
