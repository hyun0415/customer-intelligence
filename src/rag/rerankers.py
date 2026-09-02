from collections.abc import Sequence
from typing import Any, Protocol

from .config import RagSettings


class Reranker(Protocol):
    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


class BGEM3ColbertReranker:
    """BGE-M3의 multi-vector(ColBERT) 점수만 사용하는 지연 로딩 reranker."""

    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings = settings or RagSettings()
        self.settings.validate()
        self._model: Any | None = None

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:
            raise RuntimeError(
                "BGE-M3 reranker를 사용하려면 requirements-rag-rerank.txt를 "
                "설치해야 합니다."
            ) from exc

        self._model = BGEM3FlagModel(
            self.settings.reranker_model,
            devices=self.settings.reranker_device,
        )
        return self._model

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        model = self._get_model()
        scores = model.compute_score(
            [(query, passage) for passage in passages],
            batch_size=self.settings.reranker_batch_size,
            max_query_length=self.settings.reranker_query_max_tokens,
            max_passage_length=self.settings.reranker_passage_max_tokens,
            weights_for_different_modes=[0.0, 0.0, 1.0],
        )["colbert"]
        if isinstance(scores, (int, float)):
            scores = [scores]
        result = [float(score) for score in scores]
        if len(result) != len(passages):
            raise ValueError("ColBERT 점수 수와 후보 문서 수가 다릅니다.")
        return result
