# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY requirements-backend.txt ./
RUN --mount=type=cache,id=ci-pip-core-v2,target=/root/.cache/pip \
    pip install \
    --default-timeout=600 \
    --retries=10 \
    --prefer-binary \
    -r requirements-backend.txt

COPY src ./src
COPY backend ./backend

FROM base AS runtime
ENV RAG_RERANKER_ENABLED=false

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS runtime-reranker
COPY requirements-rag-rerank.txt ./
RUN --mount=type=cache,id=ci-pip-reranker-v2,target=/root/.cache/pip \
    pip install \
    --default-timeout=600 \
    --retries=10 \
    --prefer-binary \
    -r requirements-rag-rerank.txt
ENV RAG_RERANKER_ENABLED=true

EXPOSE 8000
CMD ["uvicorn", "backend.reranker_main:app", "--host", "0.0.0.0", "--port", "8000"]
