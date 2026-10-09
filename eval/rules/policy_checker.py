import unicodedata

from eval.evaluator.schemas import PolicyCheckResult


def _normalize(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).lower().split())


def _policy_outputs(case: dict) -> list[dict]:
    outputs = []
    for item in case.get("tool_outputs", []):
        if item.get("tool_name") != "search_internal_knowledge_tool":
            continue
        output = item.get("output")
        if isinstance(output, dict):
            outputs.append(output)
    return outputs


def check_policy_grounding(case: dict) -> PolicyCheckResult:
    expected_status = case.get("expected_status")
    expected_sources = set(case.get("expected_source_ids") or [])
    expected_rules = set(case.get("expected_rule_keys") or [])
    expected_facts = case.get("expected_facts") or []
    if not any((expected_status, expected_sources, expected_rules, expected_facts)):
        return PolicyCheckResult()

    outputs = _policy_outputs(case)
    statuses = {output.get("status") for output in outputs}
    sources = [source for output in outputs for source in output.get("sources", [])]
    source_ids = {source.get("source_id") for source in sources}
    rule_keys = {
        rule_key for source in sources for rule_key in source.get("rule_keys", [])
    }
    evidence = _normalize("\n".join(str(source.get("content", "")) for source in sources))

    status_pass = not expected_status or expected_status in statuses
    sources_pass = expected_sources.issubset(source_ids)
    rule_keys_pass = expected_rules.issubset(rule_keys)
    facts_pass = all(_normalize(fact) in evidence for fact in expected_facts)
    answer = _normalize(str(case.get("answer", "")))
    abstention_markers = (
        "근거부족",
        "근거를찾지못",
        "확인되지",
        "확인이필요",
        "담당자",
        "안내할수없",
    )
    no_evidence_returned = "no_evidence" in statuses
    no_evidence_abstention_pass = (
        not no_evidence_returned
        or any(marker in answer for marker in abstention_markers)
    )
    notes = []
    if not status_pass:
        notes.append(
            f"정책 상태 불일치: expected={expected_status!r}, actual={sorted(statuses, key=str)}"
        )
    if not sources_pass:
        notes.append(f"필수 정책 source 누락: {sorted(expected_sources - source_ids)}")
    if not rule_keys_pass:
        notes.append(f"필수 정책 조항 누락: {sorted(expected_rules - rule_keys)}")
    if not facts_pass:
        notes.append("정답 근거 문구가 검색된 정책 본문에 모두 존재하지 않습니다.")
    if not no_evidence_abstention_pass:
        notes.append("no_evidence 결과 뒤에 근거 부족 또는 담당자 확인을 명시하지 않았습니다.")
    return PolicyCheckResult(
        status_pass=status_pass,
        sources_pass=sources_pass,
        rule_keys_pass=rule_keys_pass,
        facts_pass=facts_pass,
        no_evidence_abstention_pass=no_evidence_abstention_pass,
        notes=notes,
    )
