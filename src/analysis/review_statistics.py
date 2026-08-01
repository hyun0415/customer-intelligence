from collections import defaultdict

from src.analysis.schemas import (
    ClassifiedReview,
    Evidence,
    ReviewPattern,
    ReviewPatternResult,
)
from src.analysis.taxonomy import REVIEW_TOPICS

MIN_CONFIDENCE = 0.8

def aggregate_review_topics(
    classified_reviews: list[ClassifiedReview],
    min_confidence: float = MIN_CONFIDENCE,
) -> ReviewPatternResult:
    sample_size = len(classified_reviews)
    topic_reviews: dict[str, set[int]] = defaultdict(set)
    topic_confidences: dict[str, list[float]] = defaultdict(list)
    topic_evidence: dict[str, list[dict]] = defaultdict(list)

    for review in classified_reviews:
        seen_topics = set()

        for topic in review.topics:
            if not topic.is_direct_experience:
                continue

            if topic.sentiment not in {"negative", "mixed"}:
                continue

            if topic.confidence < min_confidence:
                continue

            if topic.topic in seen_topics:
                continue

            seen_topics.add(topic.topic)
            topic_reviews[topic.topic].add(
                review.source_index
            )
            topic_confidences[topic.topic].append(
                topic.confidence
            )
            topic_evidence[topic.topic].append(
                {
                    "source_index": review.source_index,
                    "evidence": topic.evidence,
                    "confidence": topic.confidence,
                    "review_summary": review.summary,
                }
            )

    patterns = []

    for topic, review_indexes in topic_reviews.items():
        count = len(review_indexes)

        patterns.append(
            {
                "topic": topic,
                "count": count,
                "ratio": (
                    round(count / sample_size, 4)
                    if sample_size
                    else 0.0
                ),
                "review_indexes": sorted(
                    review_indexes
                ),
                "average_confidence": round(
                    sum(topic_confidences[topic])
                    / len(topic_confidences[topic]),
                    4,
                ),
                "evidence": topic_evidence[topic],
            }
        )

    patterns.sort(
        key=lambda item: (
            -item["count"],
            -item["average_confidence"],
            item["topic"],
        )
    )

    return ReviewPatternResult(
        sample_size=sample_size,
        classified_review_count=sum(
            bool(review.topics)
            for review in classified_reviews
        ),
       patterns=[
            ReviewPattern(
                topic=item["topic"],
                label=REVIEW_TOPICS[item["topic"]]["label"],
                description=REVIEW_TOPICS[item["topic"]]["description"],
                count=item["count"],
                ratio=item["ratio"],
                average_confidence=item["average_confidence"],
                review_indexes=item["review_indexes"],
                evidence=[
                    Evidence(**e)
                    for e in item["evidence"]
                ],
            )
            for item in patterns
        ],
    )