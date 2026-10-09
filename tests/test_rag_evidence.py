from src.rag.evidence import EVIDENCE_VALIDATION_PROMPT


def test_evidence_prompt_treats_supported_negative_answer_as_sufficient():
    assert '정답이 "아니오"라는 이유만으로 insufficient' in EVIDENCE_VALIDATION_PROMPT
    assert '정책이 "5건 이상"을 기준으로 정하고 질문이 4건' in EVIDENCE_VALIDATION_PROMPT


def test_evidence_prompt_does_not_infer_policy_absence_from_omission():
    assert "문서에 단순히 언급되지 않았다는 이유로" in EVIDENCE_VALIDATION_PROMPT
    assert "완결된 조건이 없다면\ninsufficient" in EVIDENCE_VALIDATION_PROMPT
