import json
from collections.abc import Callable, Sequence
from typing import Any, Protocol
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from langchain_openai import OpenAIEmbeddings

from .config import RagSettings
from .models import ChunkDraft


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class OpenAIEmbeddingProvider:
    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings = settings or RagSettings()
        self.settings.validate()
        self.client = OpenAIEmbeddings(
            model=self.settings.embedding_model,
            dimensions=self.settings.embedding_dimensions,
            # Child chunk 길이는 ingestion 단계에서 이미 제한한다. LangChain의
            # 추가 길이 검사를 끄면 런타임에 tiktoken 파일을 내려받지 않는다.
            check_embedding_ctx_length=False,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.client.embed_query(text)


class RemoteBGEEmbeddingProvider:
    def __init__(
        self,
        settings: RagSettings | None = None,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.settings = settings or RagSettings()
        self.settings.validate()
        if not self.settings.embedding_base_url:
            raise ValueError("원격 embedding에는 RAG_EMBEDDING_BASE_URL이 필요합니다.")
        self._opener = opener

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        request = Request(
            urljoin(self.settings.embedding_base_url.rstrip("/") + "/", "embed"),
            data=json.dumps({"texts": texts}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with self._opener(
            request,
            timeout=self.settings.embedding_timeout_seconds,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        vectors = [[float(value) for value in vector] for vector in payload["vectors"]]
        if len(vectors) != len(texts):
            raise ValueError("원격 embedding 수와 입력 문서 수가 다릅니다.")
        if any(len(vector) != self.settings.embedding_dimensions for vector in vectors):
            raise ValueError("원격 embedding 차원이 설정과 다릅니다.")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def build_embedding_provider(settings: RagSettings) -> EmbeddingProvider:
    if settings.embedding_provider == "remote_bge_m3":
        return RemoteBGEEmbeddingProvider(settings)
    return OpenAIEmbeddingProvider(settings)


def attach_embeddings(
    chunks: Sequence[ChunkDraft],
    provider: EmbeddingProvider,
    expected_dimensions: int = 1536,
) -> list[ChunkDraft]:
    children = [chunk for chunk in chunks if chunk.chunk_level == "child"]
    vectors = provider.embed_documents([chunk.embedding_text for chunk in children])
    if len(vectors) != len(children):
        raise ValueError("embedding 응답 수와 child chunk 수가 다릅니다.")

    vector_iter = iter(vectors)
    completed = []
    for chunk in chunks:
        if chunk.chunk_level == "parent":
            completed.append(chunk)
            continue
        vector = next(vector_iter)
        if len(vector) != expected_dimensions:
            raise ValueError(
                f"embedding 차원이 {expected_dimensions}이 아닙니다: {len(vector)}"
            )
        completed.append(chunk.model_copy(update={"embedding": vector}))
    return completed
