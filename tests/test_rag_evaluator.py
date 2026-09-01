from datetime import datetime, timezone

from eval.rag_evaluator import RagEvaluator, RagRetrievalCase
from src.rag.models import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSource,
)


def source(source_id, rank, rule_key):
    return KnowledgeSource(
        document_id=rank,
        document_version_id=rank,
        parent_chunk_id=rank,
        matched_child_ids=[rank],
        source_id=source_id,
        title=source_id,
        collection="compensation_policy",
        authority_tier=1,
        version_number=1,
        valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        jurisdiction="ALL_JURISDICTIONS",
        department="ALL_DEPARTMENTS",
        parent_asins=[],
        policy_key="test",
        rule_keys=[rule_key],
        section_path="test",
        section_title="test",
        content="test",
        rrf_score=1 / (60 + rank),
    )


class FakeRetriever:
    def search(self, request):
        return KnowledgeSearchResponse(
            status="ok",
            query=request.query,
            effective_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            sources=[source("irrelevant", 1, "other"), source("expected", 2, "target")],
        )


def test_rag_evaluator_calculates_recall_mrr_and_hit_rate():
    summary = RagEvaluator(FakeRetriever()).evaluate(
        [
            RagRetrievalCase(
                case_id="R01",
                request=KnowledgeSearchRequest(query="test"),
                expected_source_ids=["expected"],
                expected_rule_keys=["target"],
            )
        ]
    )

    assert summary.recall_at_k == 1.0
    assert summary.mrr == 0.5
    assert summary.hit_rate == 1.0
