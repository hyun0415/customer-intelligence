from datetime import datetime, timezone

import pytest

from src.rag.config import RagSettings
from src.rag.models import KnowledgeSearchRequest
from src.rag.retriever import HybridRetriever

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [[0.0] * 1536 for _ in texts]

    def embed_query(self, text):
        return [0.0] * 1536


def candidate(
    *,
    chunk_id,
    parent_chunk_id,
    source_id,
    authority_tier=1,
    parent_asins=None,
    rule_key="reshipment_eligibility",
    rule_effect="ALLOW_WITH_EVIDENCE",
):
    return {
        "chunk_id": chunk_id,
        "parent_chunk_id": parent_chunk_id,
        "rule_key": rule_key,
        "rule_effect": rule_effect,
        "document_id": parent_chunk_id,
        "source_id": source_id,
        "title": source_id,
        "source_url": None,
        "authority_tier": authority_tier,
        "jurisdiction": "ALL_JURISDICTIONS",
        "department": "CS",
        "policy_key": "reshipment_policy",
        "document_version_id": parent_chunk_id + 100,
        "version_number": 1,
        "valid_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "valid_to": None,
        "supersedes_version": None,
        "collection": "compensation_policy",
        "parent_asins": parent_asins or [],
    }


def retriever():
    return HybridRetriever(
        connection_factory=lambda: None,
        embedding_provider=FakeEmbeddings(),
        settings=RagSettings(candidate_limit=20),
        clock=lambda: NOW,
    )


def test_filters_apply_effective_scope_to_both_channels():
    request = KnowledgeSearchRequest(
        query="재배송 가능 여부",
        collections=["compensation_policy"],
        parent_asin="B00TEST001",
        jurisdiction="KR",
        department="CS",
    )
    sql, params = HybridRetriever._filters(request, NOW)

    assert "v.valid_from <= %s" in sql
    assert "rag_document_products" in sql
    assert "d.jurisdiction = ANY(%s)" in sql
    assert "d.department = ANY(%s)" in sql
    assert ["KR", "ALL_JURISDICTIONS"] in params
    assert ["CS", "ALL_DEPARTMENTS"] in params


def test_rrf_uses_best_rank_per_parent_and_deduplicates_parent():
    instance = retriever()
    first = candidate(chunk_id=1, parent_chunk_id=10, source_id="policy-a")
    same_parent = candidate(chunk_id=2, parent_chunk_id=10, source_id="policy-a")
    other = candidate(chunk_id=3, parent_chunk_id=20, source_id="policy-b")

    fused = instance._fuse([first, same_parent, other], [other, first])

    assert len(fused) == 2
    policy_a = next(row for row in fused if row["source_id"] == "policy-a")
    assert policy_a["fts_rank"] == 1
    assert policy_a["vector_rank"] == 2
    assert policy_a["matched_child_ids"] == [1, 2]


def test_higher_authority_resolves_different_rule_effects():
    rows = [
        {
            **candidate(
                chunk_id=1, parent_chunk_id=10, source_id="approved", authority_tier=1
            ),
            "product_specific": False,
        },
        {
            **candidate(
                chunk_id=2,
                parent_chunk_id=20,
                source_id="team-guide",
                authority_tier=3,
                rule_effect="DENY",
            ),
            "product_specific": False,
        },
    ]
    assert HybridRetriever._conflicts(rows) == []
    resolved = HybridRetriever._resolve_policy_priority(
        [{**row, "rrf_score": 0.01} for row in rows]
    )
    assert [row["source_id"] for row in resolved] == ["approved"]


def test_equal_priority_different_rule_effects_return_conflict():
    rows = [
        {
            **candidate(chunk_id=1, parent_chunk_id=10, source_id="policy-a"),
            "product_specific": False,
        },
        {
            **candidate(
                chunk_id=2,
                parent_chunk_id=20,
                source_id="policy-b",
                rule_effect="DENY",
            ),
            "product_specific": False,
        },
    ]
    conflicts = HybridRetriever._conflicts(rows)
    assert len(conflicts) == 1
    assert conflicts[0].source_ids == ["policy-a", "policy-b"]


class CapturingConnection:
    def __init__(self):
        self.query = ""
        self.params = []

    def execute(self, query, params):
        self.query = query
        self.params = params
        return self

    def fetchall(self):
        return []


def test_vector_candidates_apply_minimum_relevance_similarity():
    instance = retriever()
    conn = CapturingConnection()
    request = KnowledgeSearchRequest(query="관련 정책", jurisdiction="KR")

    rows = instance._vector_candidates(conn, request, NOW, [0.0] * 1536)

    assert rows == []
    assert "1 - (c.embedding <=> %s) >= %s" in conn.query
    assert conn.params[-3] == instance.settings.minimum_relevance_similarity


def test_minimum_relevance_similarity_must_be_between_zero_and_one():
    with pytest.raises(ValueError, match="최소 관련성"):
        RagSettings(minimum_relevance_similarity=1.01).validate()
