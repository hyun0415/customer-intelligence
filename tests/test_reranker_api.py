import pytest

pytest.importorskip("fastapi")

from backend import reranker_main


class FakeReranker:
    def score(self, query, passages):
        assert query == "환불 조건"
        assert passages == ["첫 번째", "두 번째"]
        return [0.25, 0.75]

    def embed(self, texts):
        assert texts == ["환불 조건", "재배송 조건"]
        return [[0.1] * 1024, [0.2] * 1024]


def test_reranker_health():
    assert reranker_main.health() == {"status": "ok"}


def test_reranker_endpoint_uses_shared_model(monkeypatch):
    monkeypatch.setattr(reranker_main, "get_reranker", lambda: FakeReranker())

    response = reranker_main.rerank(
        reranker_main.RerankRequest(
            query="환불 조건",
            passages=["첫 번째", "두 번째"],
        )
    )

    assert response.scores == [0.25, 0.75]


def test_embedding_endpoint_uses_shared_bge_model(monkeypatch):
    monkeypatch.setattr(reranker_main, "get_reranker", lambda: FakeReranker())

    response = reranker_main.embed(
        reranker_main.EmbedRequest(texts=["환불 조건", "재배송 조건"])
    )

    assert len(response.vectors) == 2
    assert len(response.vectors[0]) == 1024
