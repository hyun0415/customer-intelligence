import json
from collections.abc import Callable, Sequence
from typing import Any, Protocol
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .config import RagSettings


class Reranker(Protocol):
    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


class RemoteColbertReranker:
    """GPU 호스트의 BGE-M3 API를 호출하는 Reranker 어댑터."""

    def __init__(
        self,
        settings: RagSettings | None = None,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.settings = settings or RagSettings()
        self.settings.validate()
        if not self.settings.reranker_base_url:
            raise ValueError("원격 reranker에는 RAG_RERANKER_BASE_URL이 필요합니다.")
        self._opener = opener

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        request = Request(
            urljoin(self.settings.reranker_base_url.rstrip("/") + "/", "rerank"),
            data=json.dumps(
                {"query": query, "passages": list(passages)},
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with self._opener(
            request,
            timeout=self.settings.reranker_timeout_seconds,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        scores = [float(score) for score in payload.get("scores", [])]
        if len(scores) != len(passages):
            raise ValueError("원격 ColBERT 점수 수와 후보 문서 수가 다릅니다.")
        return scores


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
            use_fp16=self.settings.reranker_device.startswith("cuda"),
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

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """같은 BGE-M3 가중치에서 dense vector만 반환한다."""
        if not texts:
            return []
        encoded = self._get_model().encode(
            list(texts),
            batch_size=self.settings.reranker_batch_size,
            max_length=self.settings.reranker_passage_max_tokens,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return [
            [float(value) for value in vector]
            for vector in encoded["dense_vecs"]
        ]
