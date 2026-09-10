import json

import pytest

from src.rag.config import RagSettings
from src.rag.embeddings import (
    OpenAIEmbeddingProvider,
    RemoteBGEEmbeddingProvider,
    build_embedding_provider,
)


def test_openai_embedding_skips_runtime_tokenizer_download(monkeypatch):
    monkeypatch.delenv("MODEL_PROFILE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    provider = OpenAIEmbeddingProvider(RagSettings())

    assert provider.client.check_embedding_ctx_length is False


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_remote_bge_embedding_calls_embed_endpoint():
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse({"vectors": [[0.25] * 1024]})

    settings = RagSettings(
        embedding_provider="remote_bge_m3",
        embedding_model="BAAI/bge-m3",
        embedding_dimensions=1024,
        embedding_base_url="http://bge.test:8000",
    )
    provider = RemoteBGEEmbeddingProvider(settings, opener=opener)

    assert provider.embed_query("환불 조건") == [0.25] * 1024
    assert captured == {
        "url": "http://bge.test:8000/embed",
        "body": {"texts": ["환불 조건"]},
        "timeout": 60.0,
    }


def test_local_profile_selects_remote_bge_embedding(monkeypatch):
    monkeypatch.setenv("MODEL_PROFILE", "local")
    monkeypatch.setenv("RAG_EMBEDDING_BASE_URL", "http://bge.test:8000")
    monkeypatch.delenv("RAG_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("RAG_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("RAG_EMBEDDING_DIMENSIONS", raising=False)

    settings = RagSettings()

    assert settings.embedding_provider == "remote_bge_m3"
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.embedding_dimensions == 1024
    assert isinstance(build_embedding_provider(settings), RemoteBGEEmbeddingProvider)


def test_remote_bge_rejects_wrong_dimensions():
    settings = RagSettings(
        embedding_provider="remote_bge_m3",
        embedding_model="BAAI/bge-m3",
        embedding_dimensions=1024,
        embedding_base_url="http://bge.test:8000",
    )
    provider = RemoteBGEEmbeddingProvider(
        settings,
        opener=lambda *_args, **_kwargs: FakeResponse({"vectors": [[0.1] * 10]}),
    )

    with pytest.raises(ValueError, match="차원"):
        provider.embed_query("질문")
