from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.rag.config import RagSettings
from src.rag.rerankers import BGEM3ColbertReranker


class RerankRequest(BaseModel):
    query: str = Field(min_length=1)
    passages: list[str] = Field(min_length=1, max_length=50)


class RerankResponse(BaseModel):
    scores: list[float]


@lru_cache(maxsize=1)
def get_reranker() -> BGEM3ColbertReranker:
    return BGEM3ColbertReranker(
        RagSettings(reranker_enabled=True, reranker_base_url=None)
    )


app = FastAPI(title="Customer Intelligence BGE-M3 Reranker")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/rerank", response_model=RerankResponse)
def rerank(request: RerankRequest) -> RerankResponse:
    return RerankResponse(scores=get_reranker().score(request.query, request.passages))
