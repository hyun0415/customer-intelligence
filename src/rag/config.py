import os
from dataclasses import dataclass, field

from src.model_config import ModelRoutingSettings

ALL_JURISDICTIONS = "ALL_JURISDICTIONS"
ALL_DEPARTMENTS = "ALL_DEPARTMENTS"
DEFAULT_COLLECTIONS = (
    "compensation_policy",
    "promotion_policy",
    "product_operation_guides",
    "cs_sop",
    "exception_policy",
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RagSettings:
    embedding_model: str = field(
        default_factory=lambda: os.getenv(
            "RAG_EMBEDDING_MODEL", "text-embedding-3-small"
        )
    )
    embedding_dimensions: int = field(
        default_factory=lambda: int(os.getenv("RAG_EMBEDDING_DIMENSIONS", "1536"))
    )
    embedding_version: str = field(
        default_factory=lambda: os.getenv("RAG_EMBEDDING_VERSION", "1")
    )
    parent_min_tokens: int = field(
        default_factory=lambda: int(os.getenv("RAG_PARENT_MIN_TOKENS", "800"))
    )
    parent_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("RAG_PARENT_MAX_TOKENS", "1200"))
    )
    child_min_tokens: int = field(
        default_factory=lambda: int(os.getenv("RAG_CHILD_MIN_TOKENS", "300"))
    )
    child_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("RAG_CHILD_MAX_TOKENS", "450"))
    )
    overlap_tokens: int = field(
        default_factory=lambda: int(os.getenv("RAG_CHUNK_OVERLAP_TOKENS", "50"))
    )
    rrf_k: int = field(default_factory=lambda: int(os.getenv("RAG_RRF_K", "60")))
    candidate_limit: int = field(
        default_factory=lambda: int(os.getenv("RAG_CANDIDATE_LIMIT", "10"))
    )
    minimum_relevance_similarity: float = field(
        default_factory=lambda: float(
            os.getenv("RAG_MINIMUM_RELEVANCE_SIMILARITY", "0.33")
        )
    )
    reranker_enabled: bool = field(
        default_factory=lambda: _env_bool("RAG_RERANKER_ENABLED", True)
    )
    reranker_model: str = field(
        default_factory=lambda: os.getenv("RAG_RERANKER_MODEL", "BAAI/bge-m3")
    )
    reranker_device: str = field(
        default_factory=lambda: os.getenv("RAG_RERANKER_DEVICE", "cpu")
    )
    reranker_base_url: str | None = field(
        default_factory=lambda: os.getenv("RAG_RERANKER_BASE_URL") or None
    )
    reranker_timeout_seconds: float = field(
        default_factory=lambda: float(
            os.getenv("RAG_RERANKER_TIMEOUT_SECONDS", "60")
        )
    )
    reranker_batch_size: int = field(
        default_factory=lambda: int(os.getenv("RAG_RERANKER_BATCH_SIZE", "2"))
    )
    reranker_query_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("RAG_RERANKER_QUERY_MAX_TOKENS", "256"))
    )
    reranker_passage_max_tokens: int = field(
        default_factory=lambda: int(
            os.getenv("RAG_RERANKER_PASSAGE_MAX_TOKENS", "2048")
        )
    )
    reranker_fallback_to_rrf: bool = field(
        default_factory=lambda: _env_bool("RAG_RERANKER_FALLBACK_TO_RRF", True)
    )
    evidence_validation_enabled: bool = field(
        default_factory=lambda: _env_bool("RAG_EVIDENCE_VALIDATION_ENABLED", True)
    )
    evidence_model: str = field(
        default_factory=lambda: ModelRoutingSettings.from_env().evidence_model
    )
    evidence_timeout_seconds: float = field(
        default_factory=lambda: float(
            os.getenv("RAG_EVIDENCE_TIMEOUT_SECONDS", "15")
        )
    )
    evidence_max_retries: int = field(
        default_factory=lambda: int(os.getenv("RAG_EVIDENCE_MAX_RETRIES", "1"))
    )

    def validate(self) -> None:
        if not 0 <= self.overlap_tokens < self.child_max_tokens:
            raise ValueError(
                "overlap_tokens는 0 이상 child_max_tokens 미만이어야 합니다."
            )
        if not self.child_min_tokens <= self.child_max_tokens:
            raise ValueError("child token 범위가 올바르지 않습니다.")
        if not self.parent_min_tokens <= self.parent_max_tokens:
            raise ValueError("parent token 범위가 올바르지 않습니다.")
        if self.embedding_dimensions != 1536:
            raise ValueError("현재 DB vector column은 1536차원으로 고정되어 있습니다.")
        if self.rrf_k <= 0 or self.candidate_limit <= 0:
            raise ValueError("RRF와 candidate 설정은 양수여야 합니다.")
        if not 0.0 <= self.minimum_relevance_similarity <= 1.0:
            raise ValueError("최소 관련성 cosine similarity는 0~1 사이여야 합니다.")
        if self.reranker_batch_size <= 0:
            raise ValueError("reranker batch size는 양수여야 합니다.")
        if self.reranker_timeout_seconds <= 0:
            raise ValueError("reranker timeout은 양수여야 합니다.")
        if self.reranker_query_max_tokens <= 0 or self.reranker_passage_max_tokens <= 0:
            raise ValueError("reranker token 제한은 양수여야 합니다.")
        if self.evidence_timeout_seconds <= 0 or self.evidence_max_retries < 0:
            raise ValueError("근거 판정 timeout/retry 설정이 올바르지 않습니다.")
