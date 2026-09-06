from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from openai import OpenAIError
from pgvector.vector import Vector

from src.auth.access import ALL_COLLECTIONS

from .config import ALL_DEPARTMENTS, ALL_JURISDICTIONS, RagSettings
from .embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
from .evidence import EvidenceValidator, LLMEvidenceValidator
from .models import (
    EvidenceAssessment,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSource,
    PolicyConflict,
)
from .repository import ConnectionFactory, rag_connect
from .rerankers import BGEM3ColbertReranker, Reranker


class HybridRetriever:
    def __init__(
        self,
        connection_factory: ConnectionFactory = rag_connect,
        embedding_provider: EmbeddingProvider | None = None,
        reranker: Reranker | None = None,
        evidence_validator: EvidenceValidator | None = None,
        settings: RagSettings | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings or RagSettings()
        self.settings.validate()
        self.connection_factory = connection_factory
        self.embedding_provider = embedding_provider or OpenAIEmbeddingProvider(
            self.settings
        )
        self.reranker = reranker
        if self.reranker is None and self.settings.reranker_enabled:
            self.reranker = BGEM3ColbertReranker(self.settings)
        self.evidence_validator = evidence_validator
        if (
            self.evidence_validator is None
            and self.settings.evidence_validation_enabled
        ):
            self.evidence_validator = LLMEvidenceValidator(self.settings)
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

        if request.access_grants is not None:
            if not request.access_grants:
                conditions.append("FALSE")
            else:
                grant_conditions = []
                for grant in request.access_grants:
                    grant_parts = []
                    if grant.collection != ALL_COLLECTIONS:
                        grant_parts.append("col.name = %s")
                        params.append(grant.collection)
                    if grant.jurisdiction != ALL_JURISDICTIONS:
                        grant_parts.append("d.jurisdiction = ANY(%s)")
                        params.append(
                            [grant.jurisdiction, ALL_JURISDICTIONS]
                        )
                    if grant.department != ALL_DEPARTMENTS:
                        grant_parts.append("d.department = ANY(%s)")
                        params.append([grant.department, ALL_DEPARTMENTS])
                    grant_conditions.append(
                        "(" + " AND ".join(grant_parts or ["TRUE"]) + ")"
                    )
                conditions.append("(" + " OR ".join(grant_conditions) + ")")

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
              AND 1 - (c.embedding <=> %s) >= %s
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
                self.settings.minimum_relevance_similarity,
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
    def _rank_key(row: dict[str, Any]) -> tuple[Any, ...]:
        colbert_score = row.get("colbert_score")
        return (
            colbert_score is None,
            -float(colbert_score) if colbert_score is not None else 0.0,
            -row["rrf_score"],
            -int(row["product_specific"]),
            row["authority_tier"],
            -row["valid_from"].timestamp(),
            row["document_id"],
        )

    def _rerank(
        self,
        query: str,
        rows: list[dict[str, Any]],
        parents: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not rows or self.reranker is None:
            return rows
        rerankable = [row for row in rows if row["parent_chunk_id"] in parents]
        passages = [parents[row["parent_chunk_id"]]["chunk_text"] for row in rerankable]
        scores = self.reranker.score(query, passages)
        if len(scores) != len(rerankable):
            raise ValueError("ColBERT 점수 수와 검색 후보 수가 다릅니다.")

        score_by_parent = {
            row["parent_chunk_id"]: score
            for row, score in zip(rerankable, scores, strict=True)
        }
        ranked = []
        for row in rows:
            ranked.append(
                {
                    **row,
                    "colbert_score": score_by_parent.get(row["parent_chunk_id"]),
                }
            )
        return sorted(ranked, key=self._rank_key)

    def _rerank_with_fallback(
        self,
        query: str,
        rows: list[dict[str, Any]],
        parents: dict[int, dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str | None]:
        try:
            return self._rerank(query, rows, parents), None
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            if not self.settings.reranker_fallback_to_rrf:
                raise
            return rows, type(exc).__name__

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
        return sorted(resolved, key=HybridRetriever._rank_key)

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

    @staticmethod
    def _apply_evidence_assessment(
        sources: list[KnowledgeSource], assessment: EvidenceAssessment
    ) -> tuple[
        str, list[KnowledgeSource], list[PolicyConflict], EvidenceAssessment
    ]:
        if assessment.status == "sufficient":
            supported_parent_ids = set(assessment.supported_parent_chunk_ids)
            supported_sources = [
                source
                for source in sources
                if source.parent_chunk_id in supported_parent_ids
            ]
            if supported_sources:
                return "ok", supported_sources, [], assessment
            assessment = assessment.model_copy(
                update={
                    "status": "insufficient",
                    "reason": "근거 판정 결과에 사용 가능한 Parent 청크가 없습니다.",
                    "missing_information": [
                        "질문을 직접 뒷받침하는 승인 정책 Parent 청크"
                    ],
                }
            )
            return "no_evidence", [], [], assessment

        if assessment.status == "conflict":
            conflict_ids = assessment.supported_source_ids or [
                source.source_id for source in sources
            ]
            conflicts = [
                PolicyConflict(
                    rule_key="semantic_evidence_conflict",
                    reason=assessment.reason,
                    source_ids=sorted(set(conflict_ids)),
                )
            ]
            return "policy_conflict", sources, conflicts, assessment

        return "no_evidence", [], [], assessment

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
            fused = self._fuse(fts_rows, vector_rows)
            parents = self._load_parents(conn, fused)
            fused, reranker_error = self._rerank_with_fallback(
                request.query, fused, parents
            )
            fused = self._resolve_policy_priority(fused)
            conflicts = self._conflicts(fused)
            fused = fused[: request.limit]

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
                    colbert_score=row.get("colbert_score"),
                    product_specific=row["product_specific"],
                )
            )

        validation_error = None
        if conflicts:
            status = "policy_conflict"
            conflict_source_ids = {
                source_id
                for conflict in conflicts
                for source_id in conflict.source_ids
            }
            assessment = EvidenceAssessment(
                status="conflict",
                reason="동일 우선순위의 정책 결론이 서로 충돌합니다.",
                supported_source_ids=sorted(conflict_source_ids),
                supported_parent_chunk_ids=[
                    source.parent_chunk_id
                    for source in sources
                    if source.source_id in conflict_source_ids
                ],
            )
        elif not sources:
            status = "no_evidence"
            assessment = EvidenceAssessment(
                status="insufficient",
                reason="검색 조건을 충족하는 승인 정책 근거가 없습니다.",
                missing_information=["질문에 직접 답할 수 있는 승인 정책 근거"],
            )
        elif self.evidence_validator is None:
            status = "ok"
            assessment = None
        else:
            try:
                assessment = self.evidence_validator.assess(request.query, sources)
            except (OpenAIError, RuntimeError, TimeoutError, ValueError) as exc:
                validation_error = type(exc).__name__
                assessment = EvidenceAssessment(
                    status="insufficient",
                    reason="근거 유효성 판정기를 사용할 수 없어 안전하게 답변을 보류합니다.",
                    missing_information=["근거 유효성 판정 재시도 또는 담당자 확인"],
                )

            status, sources, conflicts, assessment = self._apply_evidence_assessment(
                sources, assessment
            )

        return KnowledgeSearchResponse(
            status=status,
            query=request.query,
            effective_at=effective_at,
            sources=sources,
            conflicts=conflicts,
            evidence_assessment=assessment,
            retrieval={
                "sparse": "postgresql_fts_ts_rank_cd",
                "dense": self.settings.embedding_model,
                "fusion": "rrf",
                "rrf_k": self.settings.rrf_k,
                "reranker": (
                    {
                        "model": self.settings.reranker_model,
                        "mode": "multi_vector_colbert",
                        "device": self.settings.reranker_device,
                        "failure_policy": (
                            "rrf_fallback"
                            if self.settings.reranker_fallback_to_rrf
                            else "raise"
                        ),
                        "error": reranker_error,
                    }
                    if self.reranker is not None
                    else None
                ),
                "evidence_validation": {
                    "enabled": self.evidence_validator is not None,
                    "model": (
                        self.settings.evidence_model
                        if self.evidence_validator is not None
                        else None
                    ),
                    "error": validation_error,
                },
                "minimum_relevance": {
                    "metric": "cosine_similarity",
                    "threshold": self.settings.minimum_relevance_similarity,
                    "fts_matches_bypass_vector_threshold": True,
                },
                "fts_candidates": len(fts_rows),
                "vector_candidates": len(vector_rows),
            },
        )
