from src.analysis.review_extractor import extract_reviews_topics
from src.analysis.review_statistics import aggregate_review_topics
from src.analysis.schemas import (
    ReviewPatternResult,
    ReviewSelectionCriteria,
)

DEFAULT_MIN_CONFIDENCE = 0.8

def build_review_patterns(
    reviews: list[dict],
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    selection_criteria: (
        ReviewSelectionCriteria | None
    ) = None,
) -> ReviewPatternResult:
    """
    리뷰 목록을 Aspect Pattern으로 변환한다.

    Pipeline

    Reviews
        ↓
    Review Extractor (LLM)
        ↓
    Structured Reviews
        ↓
    Statistics (Python)
        ↓
    Pattern JSON
    """

    if not 0 <= min_confidence <= 1:
        raise ValueError(
            "min_confidence는 0 이상 1 이하여야 합니다."
        )
    
    classified_reviews = extract_reviews_topics(reviews)

    return aggregate_review_topics(
        classified_reviews=classified_reviews,
        min_confidence=min_confidence,
        selection_criteria=selection_criteria,
    )