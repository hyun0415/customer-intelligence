from eval.policy_access_evaluation import PolicyAccessResult, summarize_policy_access


def result(**updates):
    payload = {
        "case_id": "AC01",
        "category": "collection_allowed",
        "expected_status": "ok",
        "actual_status": "ok",
        "expected_source_ids": ["policy"],
        "forbidden_source_ids": [],
        "retrieved_source_ids": ["policy"],
        "authorized_recall": 1.0,
        "status_correct": True,
        "access_scope_valid": True,
        "forbidden_exposure_count": 0,
        "external_calls_skipped": True,
        "latency_ms": 10.0,
    }
    payload.update(updates)
    return PolicyAccessResult(**payload)


def test_policy_access_summary_separates_recall_denial_and_leakage():
    summary = summarize_policy_access(
        [
            result(),
            result(
                case_id="AC02",
                category="collection_denied",
                expected_status="no_evidence",
                actual_status="no_evidence",
                expected_source_ids=[],
                retrieved_source_ids=[],
                authorized_recall=None,
                latency_ms=20.0,
            ),
            result(
                case_id="AC11",
                category="empty_grants",
                expected_status="no_evidence",
                actual_status="no_evidence",
                expected_source_ids=[],
                retrieved_source_ids=[],
                authorized_recall=None,
                latency_ms=1.0,
            ),
        ]
    )

    assert summary["authorized_recall_at_k"] == 1.0
    assert summary["denial_accuracy"] == 1.0
    assert summary["access_violation_count"] == 0
    assert summary["external_call_skip_accuracy"] == 1.0
