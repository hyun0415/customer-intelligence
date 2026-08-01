from typing import Literal

from pydantic import BaseModel, Field


ReviewTopic = Literal[
    "hair_dryness",
    "hair_damage",
    "uneven_color",
    "staining",
    "odor",
    "packaging",
    "ineffective",
    "authenticity",
    "skin_reaction",
]


class ExtractedTopic(BaseModel):
    topic: ReviewTopic
    sentiment: Literal["positive", "negative", "mixed"]
    is_direct_experience: bool
    evidence: str
    confidence: float = Field(ge=0, le=1)


class ClassifiedReview(BaseModel):
    source_index: int
    topics: list[ExtractedTopic] = Field(default_factory=list)
    summary: str

class Evidence(BaseModel):
    source_index: int
    evidence: str
    confidence: float = Field(ge=0, le=1)
    review_summary: str

class ReviewPattern(BaseModel):
    topic: ReviewTopic
    label: str
    description: str
    count: int = Field(ge=1)
    ratio: float = Field(ge=0, le=1)
    average_confidence: float = Field(ge=0, le=1)
    review_indexes: list[int]
    evidence: list[Evidence]


class ReviewPatternResult(BaseModel):
    sample_size: int
    extracted_review_count: int
    pattern_review_count: int
    patterns: list[ReviewPattern]
