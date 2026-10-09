from datetime import datetime, timezone

import pytest

from eval.rag_pipeline_cases import RAG_PIPELINE_CASES
from eval.rag_pipeline_comparison import (
    AcceptedEvidence,
    PipelineEvalCase,
    PrecomputedColbertReranker,
    StageSummary,
    _baseline_blockers,
    _parse_stages,
    evaluate_stage,
    summarize_stage,
)
from src.rag.models import KnowledgeSearchResponse, KnowledgeSource
from src.rag.rerankers import RemoteColbertReranker


def source(source_id: str) -> KnowledgeSource:
    return KnowledgeSource(
        document_id=1,
        document_version_id=1,
        parent_chunk_id=1,
        matched_child_ids=[1],
        source_id=source_id,
        title=source_id,
        collection="compensation_policy",
        authority_tier=1,
        version_number=1,
        valid_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
        jurisdiction="KR",
        department="CS",
        parent_asins=[],
        policy_key="test",
        section_path="test",
        section_title="test",
        content="test",
        rrf_score=0.1,
    )


class FakeRetriever:
    def search(self, request):
        if request.query == "정상 질문":
            status = "ok"
            sources = [source("expected")]
        else:
            status = "no_evidence"
            sources = []
        return KnowledgeSearchResponse(
            status=status,
            query=request.query,
            effective_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
            sources=sources,
        )


def test_fixed_pipeline_cases_are_unique_and_valid():
    cases = [PipelineEvalCase.model_validate(case) for case in RAG_PIPELINE_CASES]

    assert len(cases) == 24
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.expected_status for case in cases} == {"ok", "no_evidence"}
    assert all(case.evaluation_focus for case in cases)
    assert all(
        (case.expected_rule_keys or case.accepted_evidence) and case.expected_facts
        for case in cases
        if case.expected_status == "ok"
    )


def test_alternative_policy_evidence_accepts_any_valid_source_and_rule():
    case = PipelineEvalCase(
        case_id="T03",
        category="safety",
        question="안전 담당자에게 넘겨야 하나?",
        expected_status="ok",
        accepted_evidence=[
            AcceptedEvidence(source_id="policy-a", rule_key="policy-a:1"),
            AcceptedEvidence(source_id="policy-b", rule_key="policy-b:2"),
        ],
    )
    matched = source("policy-b").model_copy(update={"rule_keys": ["policy-b:2"]})

    class AlternativeRetriever:
        def search(self, request):
            return KnowledgeSearchResponse(
                status="ok",
                query=request.query,
                effective_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
                sources=[matched],
            )

    result = evaluate_stage("hybrid_rrf", AlternativeRetriever(), [case])[0]

    assert result.source_recall_at_k == 1.0
    assert result.reciprocal_rank == 1.0
    assert result.rule_keys_present is True
    assert "retrieval_miss" not in result.failure_types


def test_legacy_stage_names_map_to_explicit_ablation_names():
    assert _parse_stages("baseline,rerank,full") == [
        "hybrid_rrf",
        "hybrid_rrf_bge_m3",
        "full",
    ]


def test_stage_comparison_calculates_retrieval_status_and_latency_metrics():
    cases = [
        PipelineEvalCase(
            case_id="T01",
            category="normal",
            question="정상 질문",
            expected_status="ok",
            expected_source_ids=["expected"],
        ),
        PipelineEvalCase(
            case_id="T02",
            category="hard_negative",
            question="근거 없는 질문",
            expected_status="no_evidence",
        ),
    ]
    times = iter([0.0, 0.1, 0.1, 0.3])

    results = evaluate_stage(
        "baseline", FakeRetriever(), cases, timer=lambda: next(times)
    )
    summary = summarize_stage("baseline", results)

    assert summary.recall_at_k == 1.0
    assert summary.mrr == 1.0
    assert summary.status_accuracy == 1.0
    assert summary.no_evidence_precision == 1.0
    assert summary.no_evidence_recall == 1.0
    assert summary.no_evidence_f1 == 1.0
    assert summary.latency_p50_ms == pytest.approx(150.0)
    assert summary.latency_p95_ms == pytest.approx(200.0)


def test_precomputed_colbert_reranker_reuses_scores_and_sinks_unknowns(tmp_path):
    result_path = tmp_path / "colab.json"
    result_path.write_text(
        """
        {
          "cases": [{
            "question": "질문",
            "top_candidates": [
              {"content": "직접 근거", "colbert_score": 0.8},
              {"content": "간접 근거", "colbert_score": 0.4}
            ]
          }]
        }
        """,
        encoding="utf-8",
    )

    reranker = PrecomputedColbertReranker(result_path)

    assert reranker.score("질문", ["간접 근거", "미등록", "직접 근거"]) == [
        0.4,
        -0.6,
        0.8,
    ]


def test_precomputed_colbert_rejects_missing_current_questions(tmp_path):
    result_path = tmp_path / "colab.json"
    result_path.write_text(
        '{"cases":[{"question":"기존 질문","top_candidates":[]}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="1건 누락"):
        PrecomputedColbertReranker(
            result_path,
            expected_queries=["기존 질문", "새 질문"],
        )


def test_baseline_save_is_blocked_by_runtime_or_rerank_errors():
    clean = StageSummary(
        stage="vector_only",
        case_count=1,
        error_count=0,
        source_case_count=1,
        recall_at_k=1,
        mrr=1,
        status_accuracy=1,
        no_evidence_precision=1,
        no_evidence_recall=1,
        no_evidence_f1=1,
        latency_mean_ms=1,
        latency_p50_ms=1,
        latency_p95_ms=1,
    )
    degraded = clean.model_copy(
        update={
            "stage": "hybrid_rrf_bge_m3",
            "failure_counts": {"rerank_error": 2},
        }
    )

    assert _baseline_blockers([clean]) == []
    assert _baseline_blockers([degraded]) == [
        "hybrid_rrf_bge_m3: rerank_error=2"
    ]


def test_stage_builder_uses_remote_reranker_when_base_url_is_set(monkeypatch):
    monkeypatch.setenv("RAG_RERANKER_BASE_URL", "https://colab.example")
    monkeypatch.setattr(
        "eval.rag_pipeline_comparison.CachedEmbeddingProvider.preload_queries",
        lambda self, texts: None,
    )

    from eval.rag_pipeline_comparison import build_retrievers

    retrievers = build_retrievers(["hybrid_rrf_bge_m3"], ["질문"])

    assert isinstance(
        retrievers["hybrid_rrf_bge_m3"].reranker,
        RemoteColbertReranker,
    )
