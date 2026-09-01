from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pgvector.vector import Vector

from .config import ALL_DEPARTMENTS, ALL_JURISDICTIONS, RagSettings
from .embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
from .models import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSource,
    PolicyConflict,
)
from .repository import ConnectionFactory, rag_connect


class HybridRetriever:
    def __init__(
        self,
        connection_factory: ConnectionFactory = rag_connect,
        embedding_provider: EmbeddingProvider | None = None,
        settings: RagSettings | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings or RagSettings()
        self.settings.validate()
        self.connection_factory = connection_factory
        self.embedding_provider = embedding_provider or OpenAIEmbeddingProvider(
            self.settings
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _filters(
        request: KnowledgeSearchRequest, effective_at: datetime
    ) -> tuple[str, list[Any]]:
        conditions = [
            "v.valid_from <= %s",
            "(v.valid_to IS NULL OR %s < v.valid_to)",
            "v.approval_status = 'APPROVED'",
        ]
        params: list[Any] = [effective_at, effective_at]

        if request.collections:
            conditions.append("col.name = ANY(%s)")
            params.append(request.collections)
        if request.parent_asin:
            conditions.append(
                """
                (
                    NOT EXISTS (
                        SELECT 1 FROM rag_document_products all_dp
                        WHERE all_dp.document_id = d.document_id
                    )
                    OR EXISTS (
                        SELECT 1 FROM rag_document_products match_dp
                        WHERE match_dp.document_id = d.document_id
                          AND match_dp.parent_asin = %s
                    )
                )
                """
            )
            params.append(request.parent_asin)
        if request.jurisdiction:
            conditions.append("d.jurisdiction = ANY(%s)")
            params.append([request.jurisdiction, ALL_JURISDICTIONS])
        if request.department:
            conditions.append("d.department = ANY(%s)")
            params.append([request.department, ALL_DEPARTMENTS])

        return " AND ".join(conditions), params

    @staticmethod
    def _base_select() -> str:
        return """
            SELECT
                c.chunk_id, c.parent_chunk_id, c.rule_key, c.rule_effect,
                d.document_id, d.source_id, d.title, d.source_url,
                d.authority_tier, d.jurisdiction, d.department, d.policy_key,
                v.document_version_id, v.version_number, v.valid_from, v.valid_to,
                v.supersedes_version, col.name AS collection,
                COALESCE((
                    SELECT array_agg(dp.parent_asin ORDER BY dp.parent_asin)
                    FROM rag_document_products dp
                    WHERE dp.document_id = d.document_id
                ), ARRAY[]::text[]) AS parent_asins
            FROM rag_chunks c
            JOIN rag_document_versions v ON v.document_version_id = c.document_version_id
            JOIN rag_documents d ON d.document_id = v.document_id
            JOIN rag_collections col ON col.collection_id = d.collection_id
        """

    def _fts_candidates(
        self, conn, request: KnowledgeSearchRequest, effective_at: datetime
    ) -> list[dict[str, Any]]:
        filters, params = self._filters(request, effective_at)
        query = (
            self._base_select()
            + f"""
            WHERE c.chunk_level = 'child'
              AND c.search_vector @@ plainto_tsquery('simple', %s)
              AND {filters}
            ORDER BY ts_rank_cd(c.search_vector, plainto_tsquery('simple', %s), 32) DESC,
                     c.chunk_id
            LIMIT %s
        """
        )
        return conn.execute(
            query,
            [request.query, *params, request.query, self.settings.candidate_limit],
        ).fetchall()

    def _vector_candidates(
        self,
        conn,
        request: KnowledgeSearchRequest,
        effective_at: datetime,
        query_embedding: list[float],
    ) -> list[dict[str, Any]]:
        filters, params = self._filters(request, effective_at)
        query = (
            self._base_select()
            + f"""
            WHERE c.chunk_level = 'child'
              AND c.embedding IS NOT NULL
              AND c.embedding_model = %s
              AND {filters}
            ORDER BY c.embedding <=> %s, c.chunk_id
            LIMIT %s
        """
        )
        return conn.execute(
            query,
            [
                self.settings.embedding_model,
                *params,
                Vector(query_embedding),
                self.settings.candidate_limit,
            ],
        ).fetchall()

    def _fuse(
        self, fts_rows: list[dict[str, Any]], vector_rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        parents: dict[int, dict[str, Any]] = {}
        channel_best: dict[int, dict[str, int]] = defaultdict(dict)
        matched_children: dict[int, set[int]] = defaultdict(set)

        for channel, rows in (("fts", fts_rows), ("vector", vector_rows)):
            for rank, row in enumerate(rows, start=1):
                parent_id = row["parent_chunk_id"]
                parents.setdefault(parent_id, dict(row))
                matched_children[parent_id].add(row["chunk_id"])
                channel_best[parent_id].setdefault(channel, rank)

        fused = []
        for parent_id, row in parents.items():
            fts_rank = channel_best[parent_id].get("fts")
            vector_rank = channel_best[parent_id].get("vector")
            score = sum(
                1.0 / (self.settings.rrf_k + rank)
                for rank in (fts_rank, vector_rank)
                if rank is not None
            )
            row.update(
                parent_chunk_id=parent_id,
                matched_child_ids=sorted(matched_children[parent_id]),
                fts_rank=fts_rank,
                vector_rank=vector_rank,
                rrf_score=score,
                product_specific=bool(row["parent_asins"]),
            )
            fused.append(row)

        return sorted(
            fused,
            key=lambda row: (
                -row["rrf_score"],
                -int(row["product_specific"]),
                row["authority_tier"],
                -row["valid_from"].timestamp(),
                row["document_id"],
            ),
        )

    @staticmethod
    def _resolve_policy_priority(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        ungrouped = []
        for row in rows:
            if row.get("rule_key"):
                grouped[row["rule_key"]].append(row)
            else:
                ungrouped.append(row)

        resolved = list(ungrouped)
        for candidates in grouped.values():
            best_priority = min(
                (
                    -int(candidate["product_specific"]),
                    candidate["authority_tier"],
                    -candidate["valid_from"].timestamp(),
                )
                for candidate in candidates
            )
            resolved.extend(
                candidate
                for candidate in candidates
                if (
                    -int(candidate["product_specific"]),
                    candidate["authority_tier"],
                    -candidate["valid_from"].timestamp(),
                )
                == best_priority
            )
        return sorted(resolved, key=lambda row: (-row["rrf_score"], row["document_id"]))

    @staticmethod
    def _load_parents(conn, rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        if not rows:
            return {}
        parent_ids = [row["parent_chunk_id"] for row in rows]
        parents = conn.execute(
            """
            SELECT chunk_id, section_path, section_title, chunk_text, rule_key, rule_effect
            FROM rag_chunks
            WHERE chunk_id = ANY(%s) AND chunk_level = 'parent'
            """,
            (parent_ids,),
        ).fetchall()
        return {row["chunk_id"]: row for row in parents}

    @staticmethod
    def _conflicts(rows: list[dict[str, Any]]) -> list[PolicyConflict]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row.get("rule_key") and row.get("rule_effect"):
                grouped[row["rule_key"]].append(row)

        conflicts = []
        for rule_key, candidates in grouped.items():
            best_priority = min(
                (
                    -int(candidate["product_specific"]),
                    candidate["authority_tier"],
                    -candidate["valid_from"].timestamp(),
                )
                for candidate in candidates
            )
            peers = [
                candidate
                for candidate in candidates
                if (
                    -int(candidate["product_specific"]),
                    candidate["authority_tier"],
                    -candidate["valid_from"].timestamp(),
                )
                == best_priority
            ]
            effects = {candidate["rule_effect"] for candidate in peers}
            if len(effects) > 1:
                conflicts.append(
                    PolicyConflict(
                        rule_key=rule_key,
                        reason="동일 적용 범위, authority, 발효일의 정책 결론이 서로 다릅니다.",
                        source_ids=sorted(
                            {candidate["source_id"] for candidate in peers}
                        ),
                    )
                )
        return conflicts

    def search(
        self, request: KnowledgeSearchRequest | dict[str, Any]
    ) -> KnowledgeSearchResponse:
        if not isinstance(request, KnowledgeSearchRequest):
            request = KnowledgeSearchRequest.model_validate(request)
        effective_at = request.effective_at or self.clock()
        if effective_at.tzinfo is None:
            effective_at = effective_at.replace(tzinfo=timezone.utc)

        query_embedding = self.embedding_provider.embed_query(request.query)
        if len(query_embedding) != self.settings.embedding_dimensions:
            raise ValueError("질문 embedding 차원이 DB 설정과 다릅니다.")

        with self.connection_factory() as conn:
            fts_rows = self._fts_candidates(conn, request, effective_at)
            vector_rows = self._vector_candidates(
                conn, request, effective_at, query_embedding
            )
            fused = self._resolve_policy_priority(self._fuse(fts_rows, vector_rows))
            conflicts = self._conflicts(fused)
            fused = fused[: request.limit]
            parents = self._load_parents(conn, fused)

        sources = []
        for row in fused:
            parent = parents.get(row["parent_chunk_id"])
            if not parent:
                continue
            row["rule_key"] = parent.get("rule_key") or row.get("rule_key")
            row["rule_effect"] = parent.get("rule_effect") or row.get("rule_effect")
            sources.append(
                KnowledgeSource(
                    document_id=row["document_id"],
                    document_version_id=row["document_version_id"],
                    parent_chunk_id=row["parent_chunk_id"],
                    matched_child_ids=row["matched_child_ids"],
                    source_id=row["source_id"],
                    title=row["title"],
                    collection=row["collection"],
                    authority_tier=row["authority_tier"],
                    version_number=row["version_number"],
                    valid_from=row["valid_from"],
                    valid_to=row["valid_to"],
                    jurisdiction=row["jurisdiction"],
                    department=row["department"],
                    parent_asins=row["parent_asins"],
                    policy_key=row["policy_key"],
                    rule_keys=[row["rule_key"]] if row.get("rule_key") else [],
                    section_path=parent["section_path"],
                    section_title=parent["section_title"],
                    content=parent["chunk_text"],
                    source_url=row["source_url"],
                    fts_rank=row["fts_rank"],
                    vector_rank=row["vector_rank"],
                    rrf_score=row["rrf_score"],
                    product_specific=row["product_specific"],
                )
            )

        if conflicts:
            status = "policy_conflict"
        elif sources:
            status = "ok"
        else:
            status = "no_evidence"

        return KnowledgeSearchResponse(
            status=status,
            query=request.query,
            effective_at=effective_at,
            sources=sources,
            conflicts=conflicts,
            retrieval={
                "sparse": "postgresql_fts_ts_rank_cd",
                "dense": self.settings.embedding_model,
                "fusion": "rrf",
                "rrf_k": self.settings.rrf_k,
                "fts_candidates": len(fts_rows),
                "vector_candidates": len(vector_rows),
            },
        )
