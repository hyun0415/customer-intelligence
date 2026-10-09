import argparse
import csv
import hashlib
import json
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Any, Literal, Protocol

from dotenv import load_dotenv
from openai import OpenAIError
from psycopg import Error as PsycopgError
from pydantic import BaseModel, Field

from eval.rag_pipeline_cases import RAG_PIPELINE_CASES
from src.auth.access import ALL_COLLECTIONS, PolicyAccessGrant
from src.rag.config import RagSettings
from src.rag.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
from src.rag.evidence import LLMEvidenceValidator
from src.rag.models import KnowledgeSearchRequest, KnowledgeSearchResponse
from src.rag.rerankers import (
    BGEM3ColbertReranker,
    RemoteColbertReranker,
    Reranker,
)
from src.rag.retriever import HybridRetriever

StageName = Literal[
    "fts_only",
    "vector_only",
    "hybrid_rrf",
    "hybrid_rrf_bge_m3",
    "full",
    "baseline",
    "rerank",
]
ExpectedStatus = Literal["ok", "no_evidence", "policy_conflict"]
FailureType = Literal[
    "retrieval_miss",
    "rerank_error",
    "wrong_tool",
    "wrong_argument",
    "unsupported_claim",
    "false_no_evidence",
    "false_evidence",
    "access_violation",
    "runtime_error",
]
STAGE_ALIASES = {
    "baseline": "hybrid_rrf",
    "rerank": "hybrid_rrf_bge_m3",
}
DEFAULT_STAGES = (
    "fts_only,vector_only,hybrid_rrf,hybrid_rrf_bge_m3,full"
)
OUTPUT_DIR = Path("eval/results")
EFFECTIVE_AT = datetime(2026, 9, 2, tzinfo=timezone.utc)


class Searcher(Protocol):
    def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResponse: ...


class AcceptedEvidence(BaseModel):
    source_id: str = Field(min_length=1)
    rule_key: str | None = None


class PipelineEvalCase(BaseModel):
    case_id: str
    category: str
    question: str
    evaluation_focus: str = ""
    collections: list[str] | None = None
    parent_asin: str | None = None
    department: str | None = "CS"
    jurisdiction: str | None = "KR"
    effective_at: datetime = EFFECTIVE_AT
    limit: int = Field(default=5, ge=1, le=20)
    access_grants: list[PolicyAccessGrant] | None = None
    expected_status: ExpectedStatus
    expected_source_ids: list[str] = Field(default_factory=list)
    expected_rule_keys: list[str] = Field(default_factory=list)
    accepted_evidence: list[AcceptedEvidence] = Field(default_factory=list)
    expected_facts: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    expected_args: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def request(self) -> KnowledgeSearchRequest:
        return KnowledgeSearchRequest(
            query=self.question,
            collections=self.collections,
            parent_asin=self.parent_asin,
            department=self.department,
            jurisdiction=self.jurisdiction,
            effective_at=self.effective_at,
            limit=self.limit,
            access_grants=self.access_grants,
        )


class PipelineCaseResult(BaseModel):
    stage: StageName
    case_id: str
    category: str
    question: str
    expected_status: ExpectedStatus
    actual_status: str
    expected_source_ids: list[str]
    expected_rule_keys: list[str] = Field(default_factory=list)
    accepted_evidence: list[AcceptedEvidence] = Field(default_factory=list)
    expected_facts: list[str] = Field(default_factory=list)
    retrieved_source_ids: list[str]
    retrieved_rule_keys: list[str] = Field(default_factory=list)
    retrieved_parent_chunk_ids: list[int] = Field(default_factory=list)
    source_recall_at_k: float | None
    reciprocal_rank: float | None
    status_correct: bool
    rule_keys_present: bool = True
    facts_supported: bool = True
    access_scope_valid: bool = True
    latency_ms: float
    colbert_scores: dict[int, float] = Field(default_factory=dict)
    evidence_status: str | None = None
    evidence_reason: str | None = None
    failure_types: list[FailureType] = Field(default_factory=list)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class StageSummary(BaseModel):
    stage: StageName
    case_count: int
    error_count: int
    source_case_count: int
    recall_at_k: float
    mrr: float
    status_accuracy: float
    no_evidence_precision: float
    no_evidence_recall: float
    no_evidence_f1: float
    latency_mean_ms: float
    latency_p50_ms: float
    latency_p95_ms: float
    failure_counts: dict[str, int] = Field(default_factory=dict)
    latency_scope: str = "shared_query_embedding_excluded"


class PipelineComparisonReport(BaseModel):
    generated_at: datetime
    configuration: dict[str, Any] = Field(default_factory=dict)
    stages: list[StageSummary]
    cases: list[PipelineCaseResult]


class CachedEmbeddingProvider:
    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider
        self.query_cache: dict[str, list[float]] = {}

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.provider.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if text not in self.query_cache:
            self.query_cache[text] = self.provider.embed_query(text)
        return list(self.query_cache[text])

    def preload_queries(self, texts: list[str]) -> None:
        for text in dict.fromkeys(texts):
            self.embed_query(text)


class PrecomputedColbertReranker:
    """Colab에서 계산한 BGE-M3 점수를 동일 평가 입력에 재사용한다."""

    def __init__(
        self,
        result_path: Path,
        *,
        expected_queries: list[str] | None = None,
    ) -> None:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        self._scores: dict[str, dict[str, float]] = {}
        for case in payload.get("cases", []):
            query = case["question"]
            self._scores[query] = {
                self._passage_key(candidate["content"]): float(
                    candidate["colbert_score"]
                )
                for candidate in case.get("top_candidates", [])
            }
        if expected_queries is not None:
            missing = [
                query for query in dict.fromkeys(expected_queries)
                if query not in self._scores
            ]
            if missing:
                raise ValueError(
                    "사전 계산된 ColBERT 결과가 현재 평가 질문을 "
                    f"{len(missing)}건 누락합니다. Colab 결과를 다시 생성하세요."
                )

    @staticmethod
    def _passage_key(passage: str) -> str:
        return hashlib.sha256(passage.encode("utf-8")).hexdigest()

    def score(self, query: str, passages: list[str]) -> list[float]:
        query_scores = self._scores.get(query)
        if query_scores is None:
            raise ValueError(f"사전 계산된 ColBERT 질문이 없습니다: {query}")
        floor = min(query_scores.values(), default=0.0) - 1.0
        return [
            query_scores.get(self._passage_key(passage), floor)
            for passage in passages
        ]


def _source_metrics(
    expected: list[str], retrieved: list[str]
) -> tuple[float | None, float | None]:
    if not expected:
        return None, None
    expected_set = set(expected)
    recall = len(expected_set.intersection(retrieved)) / len(expected_set)
    rank = next(
        (
            index
            for index, source_id in enumerate(retrieved, start=1)
            if source_id in expected_set
        ),
        None,
    )
    return recall, (1.0 / rank if rank else 0.0)


def _case_source_metrics(
    case: PipelineEvalCase, retrieved: list[str]
) -> tuple[float | None, float | None]:
    if not case.accepted_evidence:
        return _source_metrics(case.expected_source_ids, retrieved)
    accepted_ids = {item.source_id for item in case.accepted_evidence}
    rank = next(
        (
            index
            for index, source_id in enumerate(retrieved, start=1)
            if source_id in accepted_ids
        ),
        None,
    )
    return (1.0 if rank else 0.0), (1.0 / rank if rank else 0.0)


def _accepted_evidence_present(
    case: PipelineEvalCase, response: KnowledgeSearchResponse
) -> bool:
    if not case.accepted_evidence:
        retrieved_ids = {source.source_id for source in response.sources}
        retrieved_rules = {
            rule_key for source in response.sources for rule_key in source.rule_keys
        }
        return set(case.expected_source_ids).issubset(retrieved_ids) and set(
            case.expected_rule_keys
        ).issubset(retrieved_rules)
    return any(
        source.source_id == accepted.source_id
        and (accepted.rule_key is None or accepted.rule_key in source.rule_keys)
        for accepted in case.accepted_evidence
        for source in response.sources
    )


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    return "".join(normalized.split())


def _facts_supported(expected_facts: list[str], response: KnowledgeSearchResponse) -> bool:
    if not expected_facts:
        return True
    evidence = _normalized_text("\n".join(source.content for source in response.sources))
    return all(_normalized_text(fact) in evidence for fact in expected_facts)


def _access_scope_valid(
    request: KnowledgeSearchRequest, response: KnowledgeSearchResponse
) -> bool:
    effective_at = request.effective_at or response.effective_at
    for source in response.sources:
        if request.collections and source.collection not in request.collections:
            return False
        if request.jurisdiction and source.jurisdiction not in {
            request.jurisdiction,
            "ALL_JURISDICTIONS",
        }:
            return False
        if request.department and source.department not in {
            request.department,
            "ALL_DEPARTMENTS",
        }:
            return False
        if source.parent_asins and request.parent_asin not in source.parent_asins:
            return False
        if source.valid_from > effective_at:
            return False
        if source.valid_to is not None and effective_at >= source.valid_to:
            return False
        if request.access_grants is not None and not any(
            (
                grant.collection in {ALL_COLLECTIONS, source.collection}
                and (
                    grant.jurisdiction == "ALL_JURISDICTIONS"
                    or source.jurisdiction
                    in {grant.jurisdiction, "ALL_JURISDICTIONS"}
                )
                and (
                    grant.department == "ALL_DEPARTMENTS"
                    or source.department in {grant.department, "ALL_DEPARTMENTS"}
                )
            )
            for grant in request.access_grants
        ):
            return False
    return True


def _failure_types(
    stage: StageName,
    case: PipelineEvalCase,
    response: KnowledgeSearchResponse,
    *,
    rules_present: bool,
    facts_supported: bool,
    access_scope_valid: bool,
) -> list[FailureType]:
    failures: list[FailureType] = []
    evidence_present = _accepted_evidence_present(case, response)
    if not evidence_present or not rules_present:
        failures.append("retrieval_miss")
    reranker = response.retrieval.get("reranker") or {}
    if reranker.get("error"):
        failures.append("rerank_error")
    if case.expected_status != "no_evidence" and response.status == "no_evidence":
        failures.append("false_no_evidence")
    if case.expected_status == "no_evidence" and response.status != "no_evidence":
        failures.append("false_evidence")
    if stage == "full" and response.status == "ok" and not facts_supported:
        failures.append("unsupported_claim")
    if not access_scope_valid:
        failures.append("access_violation")
    return list(dict.fromkeys(failures))


def evaluate_stage(
    stage: StageName,
    retriever: Searcher,
    cases: list[PipelineEvalCase],
    timer: Callable[[], float] = perf_counter,
) -> list[PipelineCaseResult]:
    results = []
    for case in cases:
        request = case.request()
        started_at = timer()
        try:
            response = retriever.search(request)
            latency_ms = (timer() - started_at) * 1000
            retrieved = list(
                dict.fromkeys(source.source_id for source in response.sources)
            )
            recall, reciprocal_rank = _case_source_metrics(case, retrieved)
            retrieved_rules = list(
                dict.fromkeys(
                    rule_key
                    for source in response.sources
                    for rule_key in source.rule_keys
                )
            )
            rules_present = (
                _accepted_evidence_present(case, response)
                if case.accepted_evidence
                else set(case.expected_rule_keys).issubset(retrieved_rules)
            )
            facts_supported = _facts_supported(case.expected_facts, response)
            access_scope_valid = _access_scope_valid(request, response)
            assessment = response.evidence_assessment
            results.append(
                PipelineCaseResult(
                    stage=stage,
                    case_id=case.case_id,
                    category=case.category,
                    question=case.question,
                    expected_status=case.expected_status,
                    actual_status=response.status,
                    expected_source_ids=case.expected_source_ids,
                    expected_rule_keys=case.expected_rule_keys,
                    accepted_evidence=case.accepted_evidence,
                    expected_facts=case.expected_facts,
                    retrieved_source_ids=retrieved,
                    retrieved_rule_keys=retrieved_rules,
                    retrieved_parent_chunk_ids=[
                        source.parent_chunk_id for source in response.sources
                    ],
                    source_recall_at_k=recall,
                    reciprocal_rank=reciprocal_rank,
                    status_correct=response.status == case.expected_status,
                    rule_keys_present=rules_present,
                    facts_supported=facts_supported,
                    access_scope_valid=access_scope_valid,
                    latency_ms=round(latency_ms, 3),
                    colbert_scores={
                        source.parent_chunk_id: source.colbert_score
                        for source in response.sources
                        if source.colbert_score is not None
                    },
                    evidence_status=assessment.status if assessment else None,
                    evidence_reason=assessment.reason if assessment else None,
                    failure_types=_failure_types(
                        stage,
                        case,
                        response,
                        rules_present=rules_present,
                        facts_supported=facts_supported,
                        access_scope_valid=access_scope_valid,
                    ),
                    retrieval_metadata=response.retrieval,
                )
            )
        except (
            OpenAIError,
            OSError,
            PsycopgError,
            RuntimeError,
            TimeoutError,
            ValueError,
        ) as exc:
            latency_ms = (timer() - started_at) * 1000
            results.append(
                PipelineCaseResult(
                    stage=stage,
                    case_id=case.case_id,
                    category=case.category,
                    question=case.question,
                    expected_status=case.expected_status,
                    actual_status="error",
                    expected_source_ids=case.expected_source_ids,
                    expected_rule_keys=case.expected_rule_keys,
                    accepted_evidence=case.accepted_evidence,
                    expected_facts=case.expected_facts,
                    retrieved_source_ids=[],
                    source_recall_at_k=(
                        0.0
                        if case.expected_source_ids or case.accepted_evidence
                        else None
                    ),
                    reciprocal_rank=(
                        0.0
                        if case.expected_source_ids or case.accepted_evidence
                        else None
                    ),
                    status_correct=False,
                    latency_ms=round(latency_ms, 3),
                    failure_types=["runtime_error"],
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _nearest_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(percentile * len(ordered) + 0.999) - 1))
    return ordered[index]


def summarize_stage(
    stage: StageName, results: list[PipelineCaseResult]
) -> StageSummary:
    source_results = [
        result for result in results if result.source_recall_at_k is not None
    ]
    expected_no_evidence = {
        result.case_id for result in results if result.expected_status == "no_evidence"
    }
    predicted_no_evidence = {
        result.case_id for result in results if result.actual_status == "no_evidence"
    }
    true_positive = len(expected_no_evidence & predicted_no_evidence)
    precision = _safe_ratio(true_positive, len(predicted_no_evidence))
    recall = _safe_ratio(true_positive, len(expected_no_evidence))
    f1 = _safe_ratio(2 * precision * recall, precision + recall)
    latencies = [result.latency_ms for result in results]
    failure_counts: dict[str, int] = {}
    for result in results:
        for failure_type in result.failure_types:
            failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1

    return StageSummary(
        stage=stage,
        case_count=len(results),
        error_count=sum(result.error is not None for result in results),
        source_case_count=len(source_results),
        recall_at_k=(
            mean(result.source_recall_at_k for result in source_results)
            if source_results
            else 0.0
        ),
        mrr=(
            mean(result.reciprocal_rank for result in source_results)
            if source_results
            else 0.0
        ),
        status_accuracy=mean(float(result.status_correct) for result in results),
        no_evidence_precision=precision,
        no_evidence_recall=recall,
        no_evidence_f1=f1,
        latency_mean_ms=mean(latencies) if latencies else 0.0,
        latency_p50_ms=median(latencies) if latencies else 0.0,
        latency_p95_ms=_nearest_percentile(latencies, 0.95),
        failure_counts=failure_counts,
    )


def build_retrievers(
    stages: list[StageName],
    query_texts: list[str],
    precomputed_rerank_results: Path | None = None,
    candidate_limit: int | None = None,
) -> dict[StageName, HybridRetriever]:
    settings_overrides = {
        "reranker_enabled": False,
        "evidence_validation_enabled": False,
    }
    if candidate_limit is not None:
        settings_overrides["candidate_limit"] = candidate_limit
    base_settings = RagSettings(**settings_overrides)
    vector_stages = {
        "vector_only",
        "hybrid_rrf",
        "hybrid_rrf_bge_m3",
        "full",
    }
    embeddings = None
    if vector_stages.intersection(stages):
        embeddings = CachedEmbeddingProvider(OpenAIEmbeddingProvider(base_settings))
        embeddings.preload_queries(query_texts)
    retrievers: dict[StageName, HybridRetriever] = {}

    if "fts_only" in stages:
        retrievers["fts_only"] = HybridRetriever(
            settings=base_settings,
            retrieval_mode="fts",
        )

    if "vector_only" in stages:
        retrievers["vector_only"] = HybridRetriever(
            embedding_provider=embeddings,
            settings=base_settings,
            retrieval_mode="vector",
        )

    if "hybrid_rrf" in stages:
        retrievers["hybrid_rrf"] = HybridRetriever(
            embedding_provider=embeddings,
            settings=base_settings,
            retrieval_mode="hybrid",
        )

    reranker: Reranker | None = None
    rerank_settings = replace(base_settings, reranker_enabled=True)
    if "hybrid_rrf_bge_m3" in stages or "full" in stages:
        if precomputed_rerank_results:
            reranker = PrecomputedColbertReranker(
                precomputed_rerank_results,
                expected_queries=query_texts,
            )
        elif rerank_settings.reranker_base_url:
            reranker = RemoteColbertReranker(rerank_settings)
        else:
            reranker = BGEM3ColbertReranker(rerank_settings)

    if "hybrid_rrf_bge_m3" in stages:
        retrievers["hybrid_rrf_bge_m3"] = HybridRetriever(
            embedding_provider=embeddings,
            reranker=reranker,
            settings=rerank_settings,
            retrieval_mode="hybrid",
        )

    if "full" in stages:
        full_settings = replace(rerank_settings, evidence_validation_enabled=True)
        retrievers["full"] = HybridRetriever(
            embedding_provider=embeddings,
            reranker=reranker,
            evidence_validator=LLMEvidenceValidator(full_settings),
            settings=full_settings,
            retrieval_mode="hybrid",
        )

    return retrievers


def _write_json(report: PipelineComparisonReport, path: Path) -> None:
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _baseline_blockers(summaries: list[StageSummary]) -> list[str]:
    blockers = []
    for summary in summaries:
        if summary.error_count:
            blockers.append(f"{summary.stage}: runtime_error={summary.error_count}")
        rerank_errors = summary.failure_counts.get("rerank_error", 0)
        if rerank_errors:
            blockers.append(f"{summary.stage}: rerank_error={rerank_errors}")
    return blockers


def _write_csv(results: list[PipelineCaseResult], path: Path) -> None:
    rows = [result.model_dump(mode="json") for result in results]
    fieldnames = list(PipelineCaseResult.model_fields)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (dict, list))
                        else value
                    )
                    for key, value in row.items()
                }
            )


def _write_markdown(summaries: list[StageSummary], path: Path) -> None:
    lines = [
        "| Pipeline | Recall@K | MRR | No-evidence F1 | p95 Latency |",
        "|---|---:|---:|---:|---:|",
    ]
    for summary in summaries:
        lines.append(
            f"| `{summary.stage}` | {summary.recall_at_k:.3f} | "
            f"{summary.mrr:.3f} | {summary.no_evidence_f1:.3f} | "
            f"{summary.latency_p95_ms:.1f} ms |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _comparison_rows(
    current: list[StageSummary], baseline_path: Path
) -> list[dict[str, Any]]:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_by_stage = {}
    for summary in payload.get("stages", []):
        stage = STAGE_ALIASES.get(summary["stage"], summary["stage"])
        baseline_by_stage[stage] = summary

    fields = ("recall_at_k", "mrr", "no_evidence_f1", "latency_p95_ms")
    rows = []
    for summary in current:
        previous = baseline_by_stage.get(summary.stage)
        if previous is None:
            continue
        current_values = summary.model_dump()
        rows.append(
            {
                "stage": summary.stage,
                "baseline": {field: previous[field] for field in fields},
                "current": {field: current_values[field] for field in fields},
                "delta": {
                    field: current_values[field] - float(previous[field])
                    for field in fields
                },
            }
        )
    return rows


def _parse_stages(value: str) -> list[StageName]:
    raw = [part.strip() for part in value.split(",") if part.strip()]
    requested = list(dict.fromkeys(STAGE_ALIASES.get(part, part) for part in raw))
    allowed = {
        "fts_only",
        "vector_only",
        "hybrid_rrf",
        "hybrid_rrf_bge_m3",
        "full",
    }
    unknown = set(requested) - allowed
    if unknown or not requested:
        raise argparse.ArgumentTypeError(
            "stages는 fts_only,vector_only,hybrid_rrf,"
            "hybrid_rrf_bge_m3,full 중에서 지정해야 합니다. "
            "baseline과 rerank 별칭도 지원합니다: "
            f"{sorted(unknown)}"
        )
    return requested  # type: ignore[return-value]


def _print_summary(summaries: list[StageSummary]) -> None:
    print("\nRAG 파이프라인 비교 결과")
    for summary in summaries:
        print(
            f"- {summary.stage}: Recall@K={summary.recall_at_k:.3f}, "
            f"MRR={summary.mrr:.3f}, 상태정확도={summary.status_accuracy:.3f}, "
            f"no_evidence F1={summary.no_evidence_f1:.3f}, "
            f"p50={summary.latency_p50_ms:.1f}ms, "
            f"p95={summary.latency_p95_ms:.1f}ms, 오류={summary.error_count}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PostgreSQL Hybrid, ColBERT rerank, 근거 판정 단계를 비교합니다."
    )
    parser.add_argument(
        "--stages",
        type=_parse_stages,
        default=_parse_stages(DEFAULT_STAGES),
        help=(
            "쉼표로 구분: fts_only,vector_only,hybrid_rrf,"
            "hybrid_rrf_bge_m3,full (baseline/rerank 별칭 지원)"
        ),
    )
    parser.add_argument(
        "--case-id",
        action="append",
        help="특정 case만 실행합니다. 여러 번 지정할 수 있습니다.",
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--candidate-limit",
        type=int,
        help="FTS와 embedding 채널에서 각각 가져올 후보 수를 지정합니다.",
    )
    parser.add_argument(
        "--final-k",
        type=int,
        default=5,
        help="모든 단계에 공통으로 적용할 최종 Parent 결과 수",
    )
    parser.add_argument(
        "--precomputed-rerank-results",
        type=Path,
        help=(
            "Colab BGE-M3 결과 JSON을 재사용합니다. 로컬에서 모델을 로드하지 않고 "
            "동일 고정 평가 세트의 full 단계를 실행할 때 사용합니다."
        ),
    )
    parser.add_argument(
        "--save-baseline",
        type=Path,
        help="현재 전체 JSON을 이후 비교용 기준선으로 추가 저장합니다.",
    )
    parser.add_argument(
        "--overwrite-baseline",
        action="store_true",
        help="기존 --save-baseline 파일 교체를 명시적으로 허용합니다.",
    )
    parser.add_argument(
        "--compare-baseline",
        type=Path,
        help="기존 기준선 JSON과 공통 단계의 지표 차이를 저장합니다.",
    )
    parser.add_argument(
        "--summary-markdown",
        type=Path,
        help="README에 붙일 평가 요약표를 Markdown으로 생성합니다.",
    )
    parser.add_argument(
        "--parser-label",
        choices=("simple", "docling"),
        default="simple",
        help="현재 DB를 적재할 때 사용한 parser를 결과 metadata에 기록합니다.",
    )
    args = parser.parse_args()
    if args.candidate_limit is not None and args.candidate_limit <= 0:
        parser.error("--candidate-limit은 양수여야 합니다.")
    if not 1 <= args.final_k <= 20:
        parser.error("--final-k는 1 이상 20 이하여야 합니다.")
    if (
        args.save_baseline
        and args.save_baseline.exists()
        and not args.overwrite_baseline
    ):
        parser.error(
            "기준선 파일이 이미 있습니다. 교체하려면 --overwrite-baseline을 사용하세요."
        )

    load_dotenv()
    cases = [PipelineEvalCase.model_validate(case) for case in RAG_PIPELINE_CASES]
    cases = [case.model_copy(update={"limit": args.final_k}) for case in cases]
    if args.case_id:
        selected = set(args.case_id)
        cases = [case for case in cases if case.case_id in selected]
        missing = selected - {case.case_id for case in cases}
        if missing:
            parser.error(f"존재하지 않는 case-id: {sorted(missing)}")

    try:
        retrievers = build_retrievers(
            args.stages,
            [case.question for case in cases],
            precomputed_rerank_results=args.precomputed_rerank_results,
            candidate_limit=args.candidate_limit,
        )
    except (
        OpenAIError,
        OSError,
        RuntimeError,
        TimeoutError,
        ValueError,
    ) as exc:
        parser.exit(
            status=2,
            message=(
                "평가 실행 준비 실패: "
                f"{type(exc).__name__}: {exc}\n"
                "OpenAI 연결, API 키와 선택 의존성 설치 상태를 확인하세요.\n"
            ),
        )
    all_results = []
    summaries = []
    for stage in args.stages:
        results = evaluate_stage(stage, retrievers[stage], cases)
        all_results.extend(results)
        summaries.append(summarize_stage(stage, results))

    report = PipelineComparisonReport(
        generated_at=datetime.now(timezone.utc),
        configuration={
            "case_count": len(cases),
            "parser": args.parser_label,
            "case_categories": sorted({case.category for case in cases}),
            "policy_scope": "data/rag/internal_policies synthetic approved policies",
            "effective_at_default": EFFECTIVE_AT.isoformat(),
            "candidate_limit_per_channel": (
                args.candidate_limit or RagSettings().candidate_limit
            ),
            "final_k": args.final_k,
            "embedding_model": RagSettings().embedding_model,
            "reranker_model": RagSettings().reranker_model,
            "evidence_model": RagSettings().evidence_model,
        },
        stages=summaries,
        cases=all_results,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = report.generated_at.strftime("%Y%m%d_%H%M%S")
    json_path = args.output_dir / f"rag_pipeline_comparison_{timestamp}.json"
    csv_path = args.output_dir / f"rag_pipeline_comparison_{timestamp}.csv"
    _write_json(report, json_path)
    _write_csv(all_results, csv_path)
    markdown_path = args.summary_markdown or (
        args.output_dir / f"rag_pipeline_summary_{timestamp}.md"
    )
    _write_markdown(summaries, markdown_path)
    if args.save_baseline:
        blockers = _baseline_blockers(summaries)
        if blockers:
            parser.exit(
                status=2,
                message=(
                    "기준선 저장을 중단했습니다. 실행 오류가 없을 때 다시 "
                    f"실행하세요: {', '.join(blockers)}\n"
                ),
            )
        args.save_baseline.parent.mkdir(parents=True, exist_ok=True)
        _write_json(report, args.save_baseline)
    comparison_path = None
    if args.compare_baseline:
        comparison_path = args.output_dir / f"rag_pipeline_delta_{timestamp}.json"
        comparison_path.write_text(
            json.dumps(
                _comparison_rows(summaries, args.compare_baseline),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    _print_summary(summaries)
    print(f"- JSON: {json_path}")
    print(f"- CSV: {csv_path}")
    print(f"- Markdown: {markdown_path}")
    if args.save_baseline:
        print(f"- Baseline: {args.save_baseline}")
    if comparison_path:
        print(f"- Delta: {comparison_path}")


if __name__ == "__main__":
    main()
