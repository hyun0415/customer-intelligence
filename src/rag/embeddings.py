from collections.abc import Sequence
from typing import Protocol

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
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.client.embed_query(text)


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
