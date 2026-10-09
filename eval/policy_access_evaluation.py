import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from eval.case_loader import load_case_dataset
from src.auth.access import ALL_COLLECTIONS, PolicyAccessGrant
from src.rag.config import ALL_DEPARTMENTS, ALL_JURISDICTIONS, RagSettings
from src.rag.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
from src.rag.models import KnowledgeSearchRequest, KnowledgeSource
from src.rag.retriever import HybridRetriever

OUTPUT_DIR = Path("eval/results")
DEFAULT_EFFECTIVE_AT = datetime(2026, 9, 2, tzinfo=timezone.utc)


class AccessGrantSpec(BaseModel):
    collection: str
    jurisdiction: str
    department: str

    def to_grant(self) -> PolicyAccessGrant:
        return PolicyAccessGrant(**self.model_dump())


class PolicyAccessCase(BaseModel):
    case_id: str
    category: str
    question: str
    collections: list[str] | None = None
    parent_asin: str | None = None
    jurisdiction: str | None = "KR"
    department: str | None = "CS"
    effective_at: datetime = DEFAULT_EFFECTIVE_AT
    access_grants: list[AccessGrantSpec]
    expected_status: str
    expected_source_ids: list[str] = Field(default_factory=list)
    forbidden_source_ids: list[str] = Field(default_factory=list)
    expect_external_calls_skipped: bool = False

    def request(self, limit: int) -> KnowledgeSearchRequest:
        return KnowledgeSearchRequest(
            query=self.question,
            collections=self.collections,
            parent_asin=self.parent_asin,
            jurisdiction=self.jurisdiction,
            department=self.department,
            effective_at=self.effective_at,
            access_grants=[grant.to_grant() for grant in self.access_grants],
            limit=limit,
        )


class PolicyAccessResult(BaseModel):
    case_id: str
    category: str
    expected_status: str
    actual_status: str
    expected_source_ids: list[str]
    forbidden_source_ids: list[str]
    retrieved_source_ids: list[str]
    authorized_recall: float | None
    status_correct: bool
    access_scope_valid: bool
    forbidden_exposure_count: int
    external_calls_skipped: bool
    latency_ms: float
    error: str | None = None


class CountingEmbeddingProvider:
    def __init__(self, delegate: EmbeddingProvider) -> None:
        self.delegate = delegate
        self.query_calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.delegate.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return self.delegate.embed_query(text)


def _source_allowed(request: KnowledgeSearchRequest, source: KnowledgeSource) -> bool:
    effective_at = request.effective_at or DEFAULT_EFFECTIVE_AT
    if request.collections and source.collection not in request.collections:
        return False
    if request.jurisdiction and source.jurisdiction not in {
        request.jurisdiction,
        ALL_JURISDICTIONS,
    }:
        return False
    if request.department and source.department not in {
        request.department,
        ALL_DEPARTMENTS,
    }:
        return False
    if source.parent_asins and request.parent_asin not in source.parent_asins:
        return False
    if source.valid_from > effective_at:
        return False
    if source.valid_to is not None and effective_at >= source.valid_to:
        return False
    if request.access_grants is None:
        return True
    return any(
        grant.collection in {ALL_COLLECTIONS, source.collection}
        and (
            grant.jurisdiction == ALL_JURISDICTIONS
            or source.jurisdiction in {grant.jurisdiction, ALL_JURISDICTIONS}
        )
        and (
            grant.department == ALL_DEPARTMENTS
            or source.department in {grant.department, ALL_DEPARTMENTS}
        )
        for grant in request.access_grants
    )


def evaluate_policy_access(
    retriever: HybridRetriever,
    embedding_provider: CountingEmbeddingProvider | None,
    cases: list[PolicyAccessCase],
    *,
    limit: int = 5,
) -> list[PolicyAccessResult]:
    results = []
    for case in cases:
        request = case.request(limit)
        calls_before = embedding_provider.query_calls if embedding_provider else 0
        started_at = perf_counter()
        try:
            response = retriever.search(request)
            latency_ms = (perf_counter() - started_at) * 1000
            retrieved_ids = [source.source_id for source in response.sources]
            expected = set(case.expected_source_ids)
            recall = (
                len(expected.intersection(retrieved_ids)) / len(expected)
                if expected
                else None
            )
            forbidden_count = sum(
                source_id in set(case.forbidden_source_ids)
                for source_id in retrieved_ids
            )
            scope_valid = all(
                _source_allowed(request, source) for source in response.sources
            )
            external_calls_skipped = (
                (embedding_provider is None or embedding_provider.query_calls == calls_before)
                and bool(response.retrieval.get("external_calls_skipped"))
            )
            results.append(
                PolicyAccessResult(
                    case_id=case.case_id,
                    category=case.category,
                    expected_status=case.expected_status,
                    actual_status=response.status,
                    expected_source_ids=case.expected_source_ids,
                    forbidden_source_ids=case.forbidden_source_ids,
                    retrieved_source_ids=retrieved_ids,
                    authorized_recall=recall,
                    status_correct=response.status == case.expected_status,
                    access_scope_valid=scope_valid,
                    forbidden_exposure_count=forbidden_count,
                    external_calls_skipped=(
                        external_calls_skipped
                        if case.expect_external_calls_skipped
                        else True
                    ),
                    latency_ms=round(latency_ms, 3),
                )
            )
        except Exception as exc:  # noqa: BLE001 - keep the evaluation suite running
            results.append(
                PolicyAccessResult(
                    case_id=case.case_id,
                    category=case.category,
                    expected_status=case.expected_status,
                    actual_status="error",
                    expected_source_ids=case.expected_source_ids,
                    forbidden_source_ids=case.forbidden_source_ids,
                    retrieved_source_ids=[],
                    authorized_recall=0.0 if case.expected_source_ids else None,
                    status_correct=False,
                    access_scope_valid=False,
                    forbidden_exposure_count=0,
                    external_calls_skipped=False,
                    latency_ms=round((perf_counter() - started_at) * 1000, 3),
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


def summarize_policy_access(results: list[PolicyAccessResult]) -> dict[str, Any]:
    authorized = [item for item in results if item.authorized_recall is not None]
    denied = [item for item in results if item.expected_status == "no_evidence"]
    latencies = sorted(item.latency_ms for item in results)
    p95_index = max(0, min(len(latencies) - 1, int(0.95 * len(latencies) + 0.999) - 1))
    return {
        "case_count": len(results),
        "status_accuracy": mean(float(item.status_correct) for item in results),
        "authorized_recall_at_k": mean(
            item.authorized_recall for item in authorized
        ) if authorized else 0.0,
        "denial_accuracy": mean(
            float(item.actual_status == "no_evidence") for item in denied
        ) if denied else 0.0,
        "access_violation_count": sum(
            (not item.access_scope_valid) or item.forbidden_exposure_count > 0
            for item in results
        ),
        "external_call_skip_accuracy": mean(
            float(item.external_calls_skipped)
            for item in results
            if item.category == "empty_grants"
        ),
        "latency_p50_ms": median(latencies),
        "latency_p95_ms": latencies[p95_index],
        "error_count": sum(item.error is not None for item in results),
    }


def _write_outputs(
    results: list[PolicyAccessResult],
    summary: dict[str, Any],
    metadata: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"policy_access_evaluation_{timestamp}.json"
    csv_path = output_dir / f"policy_access_evaluation_{timestamp}.csv"
    markdown_path = output_dir / f"policy_access_summary_{timestamp}.md"
    json_path.write_text(
        json.dumps(
            {
                "metadata": metadata,
                "summary": summary,
                "cases": [item.model_dump() for item in results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        rows = [item.model_dump() for item in results]
        writer = csv.DictWriter(handle, fieldnames=list(PolicyAccessResult.model_fields))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, list)
                    else value
                    for key, value in row.items()
                }
            )
    markdown_path.write_text(
        "\n".join(
            [
                "| Cases | Authorized Recall@K | Denial Accuracy | Access Violations | External-call Skip | p95 Latency |",
                "|---:|---:|---:|---:|---:|---:|",
                (
                    f"| {summary['case_count']} | "
                    f"{summary['authorized_recall_at_k']:.3f} | "
                    f"{summary['denial_accuracy']:.3f} | "
                    f"{summary['access_violation_count']} | "
                    f"{summary['external_call_skip_accuracy']:.3f} | "
                    f"{summary['latency_p95_ms']:.1f} ms |"
                ),
            ]
        ) + "\n",
        encoding="utf-8",
    )
    return json_path, csv_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Policy access-scope evaluation")
    parser.add_argument("--final-k", type=int, default=5)
    parser.add_argument(
        "--retrieval-mode",
        choices=("fts", "vector"),
        default="fts",
        help="권한 평가의 검색 채널입니다. 기본 FTS는 외부 embedding API가 필요 없습니다.",
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    if not 1 <= args.final_k <= 20:
        parser.error("--final-k는 1 이상 20 이하여야 합니다.")

    load_dotenv()
    dataset = load_case_dataset("policy_access_cases.json")
    cases = [PolicyAccessCase.model_validate(case) for case in dataset.cases]
    settings = RagSettings(
        reranker_enabled=False,
        evidence_validation_enabled=False,
    )
    embeddings = (
        CountingEmbeddingProvider(OpenAIEmbeddingProvider(settings))
        if args.retrieval_mode == "vector"
        else None
    )
    retriever = HybridRetriever(
        embedding_provider=embeddings,
        settings=settings,
        retrieval_mode=args.retrieval_mode,
    )
    results = evaluate_policy_access(
        retriever,
        embeddings,
        cases,
        limit=args.final_k,
    )
    summary = summarize_policy_access(results)
    metadata = {
        "schema_version": dataset.schema_version,
        "dataset_version": dataset.dataset_version,
        "case_count": len(cases),
        "retrieval_mode": args.retrieval_mode,
        "final_k": args.final_k,
        "policy_scope": dataset.policy_scope,
        "labeling_method": dataset.labeling_method,
    }
    json_path, csv_path, markdown_path = _write_outputs(
        results, summary, metadata, args.output_dir
    )
    print("정책 접근 통제 평가 결과")
    print(f"- Retrieval Mode: {args.retrieval_mode}")
    print(f"- Authorized Recall@K: {summary['authorized_recall_at_k']:.3f}")
    print(f"- Denial Accuracy: {summary['denial_accuracy']:.3f}")
    print(f"- Access Violations: {summary['access_violation_count']}")
    print(f"- External-call Skip: {summary['external_call_skip_accuracy']:.3f}")
    print(f"- JSON: {json_path}")
    print(f"- CSV: {csv_path}")
    print(f"- Markdown: {markdown_path}")


if __name__ == "__main__":
    main()
