import argparse
import csv
import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Literal, Protocol

from dotenv import load_dotenv
from openai import OpenAIError
from psycopg import Error as PsycopgError
from pydantic import BaseModel, Field

from eval.rag_pipeline_cases import RAG_PIPELINE_CASES
from src.rag.config import RagSettings
from src.rag.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
from src.rag.evidence import LLMEvidenceValidator
from src.rag.models import KnowledgeSearchRequest, KnowledgeSearchResponse
from src.rag.rerankers import BGEM3ColbertReranker, Reranker
from src.rag.retriever import HybridRetriever

StageName = Literal["baseline", "rerank", "full"]
ExpectedStatus = Literal["ok", "no_evidence", "policy_conflict"]
OUTPUT_DIR = Path("eval/results")
EFFECTIVE_AT = datetime(2026, 9, 2, tzinfo=timezone.utc)


class Searcher(Protocol):
    def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResponse: ...


class PipelineEvalCase(BaseModel):
    case_id: str
    category: str
    question: str
    collections: list[str] | None = None
    parent_asin: str | None = None
    department: str | None = "CS"
    jurisdiction: str | None = "KR"
    effective_at: datetime = EFFECTIVE_AT
    limit: int = Field(default=5, ge=1, le=20)
    expected_status: ExpectedStatus
    expected_source_ids: list[str] = Field(default_factory=list)

    def request(self) -> KnowledgeSearchRequest:
        return KnowledgeSearchRequest(
            query=self.question,
            collections=self.collections,
            parent_asin=self.parent_asin,
            department=self.department,
            jurisdiction=self.jurisdiction,
            effective_at=self.effective_at,
            limit=self.limit,
        )


class PipelineCaseResult(BaseModel):
    stage: StageName
    case_id: str
    category: str
    question: str
    expected_status: ExpectedStatus
    actual_status: str
    expected_source_ids: list[str]
    retrieved_source_ids: list[str]
    retrieved_parent_chunk_ids: list[int] = Field(default_factory=list)
    source_recall_at_k: float | None
    reciprocal_rank: float | None
    status_correct: bool
    latency_ms: float
    colbert_scores: dict[int, float] = Field(default_factory=dict)
    evidence_status: str | None = None
    evidence_reason: str | None = None
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
    latency_scope: str = "shared_query_embedding_excluded"


class PipelineComparisonReport(BaseModel):
    generated_at: datetime
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

    def __init__(self, result_path: Path) -> None:
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


def evaluate_stage(
    stage: StageName,
    retriever: Searcher,
    cases: list[PipelineEvalCase],
    timer: Callable[[], float] = perf_counter,
) -> list[PipelineCaseResult]:
    results = []
    for case in cases:
        started_at = timer()
        try:
            response = retriever.search(case.request())
            latency_ms = (timer() - started_at) * 1000
            retrieved = list(
                dict.fromkeys(source.source_id for source in response.sources)
            )
            recall, reciprocal_rank = _source_metrics(
                case.expected_source_ids, retrieved
            )
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
                    retrieved_source_ids=retrieved,
                    retrieved_parent_chunk_ids=[
                        source.parent_chunk_id for source in response.sources
                    ],
                    source_recall_at_k=recall,
                    reciprocal_rank=reciprocal_rank,
                    status_correct=response.status == case.expected_status,
                    latency_ms=round(latency_ms, 3),
                    colbert_scores={
                        source.parent_chunk_id: source.colbert_score
                        for source in response.sources
                        if source.colbert_score is not None
                    },
                    evidence_status=assessment.status if assessment else None,
                    evidence_reason=assessment.reason if assessment else None,
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
                    retrieved_source_ids=[],
                    source_recall_at_k=0.0 if case.expected_source_ids else None,
                    reciprocal_rank=0.0 if case.expected_source_ids else None,
                    status_correct=False,
                    latency_ms=round(latency_ms, 3),
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
    embeddings = CachedEmbeddingProvider(OpenAIEmbeddingProvider(base_settings))
    embeddings.preload_queries(query_texts)
    retrievers: dict[StageName, HybridRetriever] = {}

    if "baseline" in stages:
        retrievers["baseline"] = HybridRetriever(
            embedding_provider=embeddings,
            settings=base_settings,
        )

    reranker: Reranker | None = None
    rerank_settings = replace(base_settings, reranker_enabled=True)
    if "rerank" in stages or "full" in stages:
        reranker = (
            PrecomputedColbertReranker(precomputed_rerank_results)
            if precomputed_rerank_results
            else BGEM3ColbertReranker(rerank_settings)
        )

    if "rerank" in stages:
        retrievers["rerank"] = HybridRetriever(
            embedding_provider=embeddings,
            reranker=reranker,
            settings=rerank_settings,
        )

    if "full" in stages:
        full_settings = replace(rerank_settings, evidence_validation_enabled=True)
        retrievers["full"] = HybridRetriever(
            embedding_provider=embeddings,
            reranker=reranker,
            evidence_validator=LLMEvidenceValidator(full_settings),
            settings=full_settings,
        )

    return retrievers


def _write_json(report: PipelineComparisonReport, path: Path) -> None:
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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


def _parse_stages(value: str) -> list[StageName]:
    requested = list(dict.fromkeys(part.strip() for part in value.split(",")))
    allowed = {"baseline", "rerank", "full"}
    unknown = set(requested) - allowed
    if unknown or not requested:
        raise argparse.ArgumentTypeError(
            f"stages는 baseline,rerank,full 중에서 지정해야 합니다: {sorted(unknown)}"
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
        default=_parse_stages("baseline,rerank,full"),
        help="쉼표로 구분: baseline,rerank,full",
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
        "--precomputed-rerank-results",
        type=Path,
        help=(
            "Colab BGE-M3 결과 JSON을 재사용합니다. 로컬에서 모델을 로드하지 않고 "
            "동일 고정 평가 세트의 full 단계를 실행할 때 사용합니다."
        ),
    )
    args = parser.parse_args()
    if args.candidate_limit is not None and args.candidate_limit <= 0:
        parser.error("--candidate-limit은 양수여야 합니다.")

    load_dotenv()
    cases = [PipelineEvalCase.model_validate(case) for case in RAG_PIPELINE_CASES]
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
        stages=summaries,
        cases=all_results,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = report.generated_at.strftime("%Y%m%d_%H%M%S")
    json_path = args.output_dir / f"rag_pipeline_comparison_{timestamp}.json"
    csv_path = args.output_dir / f"rag_pipeline_comparison_{timestamp}.csv"
    _write_json(report, json_path)
    _write_csv(all_results, csv_path)
    _print_summary(summaries)
    print(f"- JSON: {json_path}")
    print(f"- CSV: {csv_path}")


if __name__ == "__main__":
    main()
