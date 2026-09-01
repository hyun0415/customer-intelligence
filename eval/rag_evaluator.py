from statistics import mean
from typing import Protocol

from pydantic import BaseModel, Field

from src.rag.models import KnowledgeSearchRequest, KnowledgeSearchResponse


class Searcher(Protocol):
    def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResponse: ...


class RagRetrievalCase(BaseModel):
    case_id: str
    request: KnowledgeSearchRequest
    expected_source_ids: list[str] = Field(default_factory=list)
    expected_rule_keys: list[str] = Field(default_factory=list)


class RagCaseResult(BaseModel):
    case_id: str
    retrieved_source_ids: list[str]
    recall_at_k: float
    reciprocal_rank: float
    hit: bool
    status: str


class RagEvaluationSummary(BaseModel):
    cases: list[RagCaseResult]
    recall_at_k: float
    mrr: float
    hit_rate: float


class RagEvaluator:
    def __init__(self, retriever: Searcher) -> None:
        self.retriever = retriever

    def evaluate(self, cases: list[RagRetrievalCase]) -> RagEvaluationSummary:
        results = [self._evaluate_case(case) for case in cases]
        if not results:
            return RagEvaluationSummary(
                cases=[], recall_at_k=0.0, mrr=0.0, hit_rate=0.0
            )
        return RagEvaluationSummary(
            cases=results,
            recall_at_k=mean(result.recall_at_k for result in results),
            mrr=mean(result.reciprocal_rank for result in results),
            hit_rate=mean(float(result.hit) for result in results),
        )

    def _evaluate_case(self, case: RagRetrievalCase) -> RagCaseResult:
        response = self.retriever.search(case.request)
        retrieved = [source.source_id for source in response.sources]
        expected = set(case.expected_source_ids)
        hits = expected.intersection(retrieved)
        recall = len(hits) / len(expected) if expected else 1.0
        first_rank = next(
            (
                rank
                for rank, source_id in enumerate(retrieved, start=1)
                if source_id in expected
            ),
            None,
        )
        reciprocal_rank = 1.0 / first_rank if first_rank else 0.0

        retrieved_rules = {
            rule_key for source in response.sources for rule_key in source.rule_keys
        }
        rules_hit = set(case.expected_rule_keys).issubset(retrieved_rules)
        hit = (not expected or bool(hits)) and rules_hit

        return RagCaseResult(
            case_id=case.case_id,
            retrieved_source_ids=retrieved,
            recall_at_k=recall,
            reciprocal_rank=reciprocal_rank,
            hit=hit,
            status=response.status,
        )
