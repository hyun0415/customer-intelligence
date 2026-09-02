from datetime import datetime, timezone

import pytest

from eval.rag_pipeline_cases import RAG_PIPELINE_CASES
from eval.rag_pipeline_comparison import (
    PipelineEvalCase,
    PrecomputedColbertReranker,
    evaluate_stage,
    summarize_stage,
)
from src.rag.models import KnowledgeSearchResponse, KnowledgeSource


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

    assert len(cases) == 14
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.expected_status for case in cases} == {"ok", "no_evidence"}


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
