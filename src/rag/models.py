from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .config import ALL_DEPARTMENTS, ALL_JURISDICTIONS, DEFAULT_COLLECTIONS


class PolicyMetadata(BaseModel):
    source_id: str
    collection: str
    source_type: str
    authority_tier: int = Field(ge=1, le=4)
    publisher: str
    title: str
    source_url: str | None = None
    language: str
    jurisdiction: str
    department: str
    policy_key: str
    approval_status: str
    version_number: int = Field(ge=1)
    valid_from: datetime
    valid_to: datetime | None = None
    supersedes_version: int | None = None
    parent_asins: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("jurisdiction", "department")
    @classmethod
    def reject_empty_scope(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("적용 범위는 명시적으로 입력해야 합니다.")
        return value

    def model_post_init(self, __context: Any, /) -> None:
        if self.collection not in DEFAULT_COLLECTIONS:
            raise ValueError(f"지원하지 않는 collection입니다: {self.collection}")
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to는 valid_from보다 뒤여야 합니다.")
        if (
            self.supersedes_version is not None
            and self.supersedes_version >= self.version_number
        ):
            raise ValueError("supersedes_version은 현재 버전보다 작아야 합니다.")


class LoadedPolicyDocument(BaseModel):
    path: Path
    metadata: PolicyMetadata
    raw_content: str
    cleaned_content: str


class ChunkDraft(BaseModel):
    chunk_level: Literal["parent", "child"]
    chunk_index: int = Field(ge=0)
    parent_index: int | None = None
    section_path: str
    section_title: str
    chunk_text: str
    embedding_text: str
    token_count: int = Field(gt=0)
    rule_key: str | None = None
    rule_effect: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    collections: list[str] | None = None
    parent_asin: str | None = None
    department: str | None = None
    jurisdiction: str | None = None
    effective_at: datetime | None = None
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("collections")
    @classmethod
    def validate_collections(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unknown = sorted(set(value) - set(DEFAULT_COLLECTIONS))
        if unknown:
            raise ValueError(f"지원하지 않는 collection입니다: {unknown}")
        return list(dict.fromkeys(value))


class KnowledgeSource(BaseModel):
    document_id: int
    document_version_id: int
    parent_chunk_id: int
    matched_child_ids: list[int]
    source_id: str
    title: str
    collection: str
    authority_tier: int
    version_number: int
    valid_from: datetime
    valid_to: datetime | None = None
    jurisdiction: str
    department: str
    parent_asins: list[str]
    policy_key: str
    rule_keys: list[str] = Field(default_factory=list)
    section_path: str
    section_title: str
    content: str
    source_url: str | None = None
    fts_rank: int | None = None
    vector_rank: int | None = None
    rrf_score: float
    colbert_score: float | None = None
    product_specific: bool = False


class PolicyConflict(BaseModel):
    rule_key: str
    reason: str
    source_ids: list[str]


class EvidenceAssessment(BaseModel):
    status: Literal["sufficient", "insufficient", "conflict"]
    reason: str = Field(min_length=1)
    supported_source_ids: list[str] = Field(default_factory=list)
    supported_parent_chunk_ids: list[int] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class KnowledgeSearchResponse(BaseModel):
    status: Literal["ok", "no_evidence", "policy_conflict"]
    query: str
    effective_at: datetime
    sources: list[KnowledgeSource] = Field(default_factory=list)
    conflicts: list[PolicyConflict] = Field(default_factory=list)
    evidence_assessment: EvidenceAssessment | None = None
    retrieval: dict[str, Any] = Field(default_factory=dict)


GLOBAL_SCOPE_EXAMPLES = {
    "jurisdiction": ALL_JURISDICTIONS,
    "department": ALL_DEPARTMENTS,
}
