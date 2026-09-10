from datetime import datetime, timezone
from pathlib import Path

import pytest
from pgvector.psycopg import register_vector

from src.database import connect
from src.rag.chunker import ParentChildChunker
from src.rag.config import ALL_DEPARTMENTS, ALL_JURISDICTIONS, RagSettings
from src.rag.ingestion import RagIngestionService
from src.rag.models import EvidenceAssessment, KnowledgeSearchRequest, PolicyMetadata
from src.rag.repository import RagRepository
from src.rag.retriever import HybridRetriever

pytestmark = pytest.mark.integration


class FakeEncoding:
    def encode(self, text):
        return list(text.encode("utf-8"))

    def decode(self, tokens):
        return bytes(tokens).decode("utf-8", errors="ignore")


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [[1.0] + [0.0] * 1535 for _ in texts]

    def embed_query(self, text):
        return [1.0] + [0.0] * 1535


class FakeBGEEmbeddings:
    def embed_documents(self, texts):
        return [[1.0] + [0.0] * 1023 for _ in texts]

    def embed_query(self, text):
        return [1.0] + [0.0] * 1023


class FakeReranker:
    def score(self, query, passages):
        return [1.0 for _ in passages]


class AlwaysSufficientValidator:
    def assess(self, query, sources):
        return EvidenceAssessment(
            status="sufficient",
            reason="테스트 정책이 질문을 직접 뒷받침합니다.",
            supported_source_ids=[source.source_id for source in sources],
            supported_parent_chunk_ids=[source.parent_chunk_id for source in sources],
        )


class BorrowedConnection:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def test_schema_ingestion_and_hybrid_retrieval_round_trip(tmp_path):
    conn = connect()
    register_vector(conn)
    try:
        migrations = Path(__file__).parents[1] / "db" / "migrations"
        for filename in ("004_policy_rag.sql", "010_multi_model_embeddings.sql"):
            conn.execute(
                (migrations / filename).read_text(encoding="utf-8"),
                prepare=False,
            )

        path = tmp_path / "policy.md"
        path.write_text(
            "# 테스트 재배송 규칙\n\n테스트 증빙이 확인된 경우 테스트 재배송 검토가 가능하다.",
            encoding="utf-8",
        )
        metadata = PolicyMetadata(
            source_id="pytest_internal_reshipment",
            collection="compensation_policy",
            source_type="approved_policy",
            authority_tier=1,
            publisher="Test Operations",
            title="테스트 재배송 정책",
            language="ko",
            jurisdiction=ALL_JURISDICTIONS,
            department=ALL_DEPARTMENTS,
            policy_key="pytest_reshipment",
            approval_status="APPROVED",
            version_number=1,
            valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            metadata={
                "rules": {
                    "테스트 재배송 규칙": {
                        "rule_key": "pytest_reshipment_eligibility",
                        "rule_effect": "ALLOW_TEST_REVIEW",
                    }
                }
            },
        )

        def factory():
            return BorrowedConnection(conn)

        service = RagIngestionService(
            repository=RagRepository(connection_factory=factory),
            embedding_provider=FakeEmbeddings(),
            chunker=ParentChildChunker(encoding=FakeEncoding()),
        )
        service.ingest(path, metadata)

        path.write_text(
            "# 테스트 재배송 규칙\n\n개정된 테스트 증빙이 확인된 경우 테스트 재배송 검토가 가능하다.",
            encoding="utf-8",
        )
        service.ingest(
            path,
            metadata.model_copy(
                update={
                    "version_number": 2,
                    "valid_from": datetime(2026, 6, 1, tzinfo=timezone.utc),
                    "supersedes_version": 1,
                }
            ),
        )

        bge_settings = RagSettings(
            embedding_provider="remote_bge_m3",
            embedding_model="BAAI/bge-m3",
            embedding_dimensions=1024,
            embedding_base_url="http://bge.test",
        )
        bge_service = RagIngestionService(
            repository=RagRepository(
                connection_factory=factory,
                settings=bge_settings,
            ),
            embedding_provider=FakeBGEEmbeddings(),
            chunker=ParentChildChunker(bge_settings, encoding=FakeEncoding()),
            settings=bge_settings,
        )
        version_id = bge_service.ingest(
            path,
            metadata.model_copy(
                update={
                    "version_number": 2,
                    "valid_from": datetime(2026, 6, 1, tzinfo=timezone.utc),
                    "supersedes_version": 1,
                }
            ),
        )
        bge_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM rag_chunk_embeddings e
            JOIN rag_chunks c ON c.chunk_id = e.chunk_id
            WHERE c.document_version_id = %s AND e.model_key = 'BAAI/bge-m3'
            """,
            (version_id,),
        ).fetchone()["count"]
        assert bge_count > 0

        response = HybridRetriever(
            connection_factory=factory,
            embedding_provider=FakeEmbeddings(),
            reranker=FakeReranker(),
            evidence_validator=AlwaysSufficientValidator(),
            clock=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc),
        ).search(
            KnowledgeSearchRequest(
                query="테스트 재배송 증빙",
                collections=["compensation_policy"],
                parent_asin="B005IHT8KI",
                jurisdiction="KR",
                department="CS",
                limit=5,
            )
        )

        assert response.status == "ok"
        assert response.sources[0].source_id == "pytest_internal_reshipment"
        assert response.sources[0].version_number == 2
        assert response.sources[0].rule_keys == ["pytest_reshipment_eligibility"]
    finally:
        conn.rollback()
        conn.close()
