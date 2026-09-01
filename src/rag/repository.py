import hashlib
from collections.abc import Callable, Sequence
from typing import Any

from pgvector.psycopg import register_vector
from pgvector.vector import Vector
from psycopg.types.json import Jsonb

from src.database import connect

from .config import RagSettings
from .models import ChunkDraft, LoadedPolicyDocument

ConnectionFactory = Callable[[], Any]


def rag_connect():
    conn = connect()
    register_vector(conn)
    return conn


class RagRepository:
    def __init__(
        self,
        connection_factory: ConnectionFactory = rag_connect,
        settings: RagSettings | None = None,
    ) -> None:
        self.connection_factory = connection_factory
        self.settings = settings or RagSettings()

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def upsert_document(
        self, document: LoadedPolicyDocument, chunks: Sequence[ChunkDraft]
    ) -> int:
        metadata = document.metadata
        digest = self.content_hash(document.cleaned_content)

        with self.connection_factory() as conn:  # noqa: SIM117
            with conn.transaction():
                collection = conn.execute(
                    "SELECT collection_id FROM rag_collections WHERE name = %s AND is_active",
                    (metadata.collection,),
                ).fetchone()
                if not collection:
                    raise ValueError(
                        f"활성 collection이 없습니다: {metadata.collection}"
                    )

                row = conn.execute(
                    """
                    INSERT INTO rag_documents (
                        source_id, collection_id, source_type, authority_tier,
                        publisher, title, source_url, language, jurisdiction,
                        department, policy_key, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_id) DO UPDATE SET
                        collection_id = EXCLUDED.collection_id,
                        source_type = EXCLUDED.source_type,
                        authority_tier = EXCLUDED.authority_tier,
                        publisher = EXCLUDED.publisher,
                        title = EXCLUDED.title,
                        source_url = EXCLUDED.source_url,
                        language = EXCLUDED.language,
                        jurisdiction = EXCLUDED.jurisdiction,
                        department = EXCLUDED.department,
                        policy_key = EXCLUDED.policy_key,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING document_id
                    """,
                    (
                        metadata.source_id,
                        collection["collection_id"],
                        metadata.source_type,
                        metadata.authority_tier,
                        metadata.publisher,
                        metadata.title,
                        metadata.source_url,
                        metadata.language,
                        metadata.jurisdiction,
                        metadata.department,
                        metadata.policy_key,
                        Jsonb(metadata.metadata),
                    ),
                ).fetchone()
                document_id = row["document_id"]

                existing = conn.execute(
                    """
                    SELECT document_version_id
                    FROM rag_document_versions
                    WHERE document_id = %s AND content_hash = %s
                    """,
                    (document_id, digest),
                ).fetchone()
                if existing:
                    return existing["document_version_id"]

                if metadata.supersedes_version is not None:
                    superseded = conn.execute(
                        """
                        UPDATE rag_document_versions
                        SET valid_to = %s, is_current = FALSE
                        WHERE document_id = %s
                          AND version_number = %s
                          AND valid_from < %s
                          AND (valid_to IS NULL OR valid_to > %s)
                        RETURNING document_version_id
                        """,
                        (
                            metadata.valid_from,
                            document_id,
                            metadata.supersedes_version,
                            metadata.valid_from,
                            metadata.valid_from,
                        ),
                    ).fetchone()
                    if not superseded:
                        raise ValueError(
                            "supersedes_version에 해당하는 종료 가능한 이전 버전이 없습니다."
                        )

                overlap = conn.execute(
                    """
                    SELECT version_number
                    FROM rag_document_versions
                    WHERE document_id = %s
                      AND valid_from < COALESCE(%s, 'infinity'::timestamptz)
                      AND COALESCE(valid_to, 'infinity'::timestamptz) > %s
                    LIMIT 1
                    """,
                    (document_id, metadata.valid_to, metadata.valid_from),
                ).fetchone()
                if overlap:
                    raise ValueError(
                        "기존 정책 버전과 유효기간이 겹칩니다: "
                        f"version={overlap['version_number']}"
                    )
                version = conn.execute(
                    """
                    INSERT INTO rag_document_versions (
                        document_id, version_number, content_hash, raw_content,
                        cleaned_content, valid_from, valid_to, approval_status, is_current,
                        supersedes_version, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s)
                    RETURNING document_version_id
                    """,
                    (
                        document_id,
                        metadata.version_number,
                        digest,
                        document.raw_content,
                        document.cleaned_content,
                        metadata.valid_from,
                        metadata.valid_to,
                        metadata.approval_status,
                        metadata.supersedes_version,
                        Jsonb(metadata.metadata),
                    ),
                ).fetchone()
                version_id = version["document_version_id"]

                conn.execute(
                    "UPDATE rag_document_versions SET is_current = FALSE WHERE document_id = %s",
                    (document_id,),
                )
                conn.execute(
                    """
                    UPDATE rag_document_versions
                    SET is_current = TRUE
                    WHERE document_version_id = (
                        SELECT document_version_id
                        FROM rag_document_versions
                        WHERE document_id = %s
                          AND valid_from <= CURRENT_TIMESTAMP
                          AND (valid_to IS NULL OR CURRENT_TIMESTAMP < valid_to)
                        ORDER BY valid_from DESC, version_number DESC
                        LIMIT 1
                    )
                    """,
                    (document_id,),
                )

                conn.execute(
                    "DELETE FROM rag_document_products WHERE document_id = %s",
                    (document_id,),
                )
                for parent_asin in metadata.parent_asins:
                    conn.execute(
                        """
                        INSERT INTO rag_document_products (document_id, parent_asin)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (document_id, parent_asin),
                    )

                parent_ids: dict[int, int] = {}
                for chunk in chunks:
                    if chunk.chunk_level != "parent":
                        continue
                    inserted = self._insert_chunk(conn, version_id, chunk, None)
                    parent_ids[chunk.chunk_index] = inserted

                for chunk in chunks:
                    if chunk.chunk_level != "child":
                        continue
                    if chunk.parent_index not in parent_ids:
                        raise ValueError(
                            f"child의 parent chunk가 없습니다: {chunk.parent_index}"
                        )
                    self._insert_chunk(
                        conn, version_id, chunk, parent_ids[chunk.parent_index]
                    )

                return version_id

    def _insert_chunk(
        self, conn, version_id: int, chunk: ChunkDraft, parent_id: int | None
    ) -> int:
        row = conn.execute(
            """
            INSERT INTO rag_chunks (
                document_version_id, parent_chunk_id, chunk_level, chunk_index,
                section_path, section_title, chunk_text, embedding_text,
                token_count, embedding_model, embedding_version, embedding,
                rule_key, rule_effect, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING chunk_id
            """,
            (
                version_id,
                parent_id,
                chunk.chunk_level,
                chunk.chunk_index,
                chunk.section_path,
                chunk.section_title,
                chunk.chunk_text,
                chunk.embedding_text,
                chunk.token_count,
                self.settings.embedding_model if chunk.embedding is not None else None,
                self.settings.embedding_version
                if chunk.embedding is not None
                else None,
                Vector(chunk.embedding) if chunk.embedding is not None else None,
                chunk.rule_key,
                chunk.rule_effect,
                Jsonb(chunk.metadata),
            ),
        ).fetchone()
        return row["chunk_id"]
