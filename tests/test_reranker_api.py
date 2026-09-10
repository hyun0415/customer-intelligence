import pytest

pytest.importorskip("fastapi")

from backend import reranker_main


class FakeReranker:
    def score(self, query, passages):
        assert query == "환불 조건"
        assert passages == ["첫 번째", "두 번째"]
        return [0.25, 0.75]


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
