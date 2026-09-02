import argparse
import json
from datetime import timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from eval.rag_pipeline_cases import RAG_PIPELINE_CASES
from eval.rag_pipeline_comparison import PipelineEvalCase
from src.rag.config import RagSettings
from src.rag.models import KnowledgeSearchRequest
from src.rag.retriever import HybridRetriever

DEFAULT_OUTPUT = Path("eval/results/colab_rerank_input.json")


def collect_candidates(
    retriever: HybridRetriever, request: KnowledgeSearchRequest
) -> list[dict[str, Any]]:
    effective_at = request.effective_at or retriever.clock()
    if effective_at.tzinfo is None:
        effective_at = effective_at.replace(tzinfo=timezone.utc)
    query_embedding = retriever.embedding_provider.embed_query(request.query)
    if len(query_embedding) != retriever.settings.embedding_dimensions:
        raise ValueError("질문 embedding 차원이 DB 설정과 다릅니다.")

    with retriever.connection_factory() as conn:
        fts_rows = retriever._fts_candidates(conn, request, effective_at)
        vector_rows = retriever._vector_candidates(
            conn, request, effective_at, query_embedding
        )
        fused = retriever._fuse(fts_rows, vector_rows)
        parents = retriever._load_parents(conn, fused)

    candidates = []
    for row in fused:
        parent = parents.get(row["parent_chunk_id"])
        if not parent:
            continue
        candidates.append(
            {
                "parent_chunk_id": row["parent_chunk_id"],
                "source_id": row["source_id"],
                "title": row["title"],
                "collection": row["collection"],
                "authority_tier": row["authority_tier"],
                "valid_from": row["valid_from"].isoformat(),
                "product_specific": row["product_specific"],
                "rrf_score": row["rrf_score"],
                "fts_rank": row["fts_rank"],
                "vector_rank": row["vector_rank"],
                "matched_child_ids": row["matched_child_ids"],
                "section_path": parent["section_path"],
                "section_title": parent["section_title"],
                "content": parent["chunk_text"],
            }
        )
    return candidates


def build_export_payload(
    cases: list[PipelineEvalCase], retriever: HybridRetriever
) -> dict[str, Any]:
    exported_cases = []
    for case in cases:
        exported_cases.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "question": case.question,
                "expected_status": case.expected_status,
                "expected_source_ids": case.expected_source_ids,
                "candidates": collect_candidates(retriever, case.request()),
            }
        )
    return {
        "schema_version": 1,
        "reranker_model": "BAAI/bge-m3",
        "reranker_mode": "multi_vector_colbert",
        "max_query_length": 256,
        "max_passage_length": 2048,
        "cases": exported_cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="로컬 PostgreSQL Hybrid 후보를 Colab 재정렬 입력으로 내보냅니다."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--case-id", action="append")
    args = parser.parse_args()

    load_dotenv()
    cases = [PipelineEvalCase.model_validate(case) for case in RAG_PIPELINE_CASES]
    if args.case_id:
        selected = set(args.case_id)
        cases = [case for case in cases if case.case_id in selected]
        missing = selected - {case.case_id for case in cases}
        if missing:
            parser.error(f"존재하지 않는 case-id: {sorted(missing)}")

    retriever = HybridRetriever(
        settings=RagSettings(
            reranker_enabled=False,
            evidence_validation_enabled=False,
        )
    )
    payload = build_export_payload(cases, retriever)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Colab 입력 저장: {args.output}")
    print(f"평가 case: {len(cases)}")
    print(f"후보 Parent: {sum(len(case['candidates']) for case in payload['cases'])}")


if __name__ == "__main__":
    main()
