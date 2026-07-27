from src.analysis.review_extractor import extract_reviews_topics
from src.analysis.review_statistics import aggregate_review_topics
from src.analysis.schemas import ReviewPatternResult

DEFAULT_MIN_CONFIDENCE = 0.8

def build_review_patterns(
    reviews: list[dict],
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
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

    classified_reviews = extract_reviews_topics(reviews)

    return aggregate_review_topics(
        classified_reviews,
        min_confidence,
    )