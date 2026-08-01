from eval.rules.tool_checker import evaluate_required_tool_execution
from src.analysis.review_statistics import aggregate_review_topics

from src.analysis.schemas import (
    ClassifiedReview,
    ExtractedTopic,
    ReviewSelectionCriteria,
)

selection_criteria = ReviewSelectionCriteria(
    rating_max=3,
    min_helpful_votes=1,
    sort_by="helpful_vote_desc",
    requested_limit=3,
)


def test_aggregate_review_topics_schema():
    reviews = [
        ClassifiedReview(
            source_index=0,
            summary=(
                "손 착색과 냄새를 직접 경험했다."
            ),
            topics=[
                ExtractedTopic(
                    topic="staining",
                    sentiment="negative",
                    is_direct_experience=True,
                    evidence="stained my hands",
                    confidence=0.95,
                ),
                ExtractedTopic(
                    topic="odor",
                    sentiment="negative",
                    is_direct_experience=True,
                    evidence="smells awful",
                    confidence=0.90,
                ),
            ],
        ),
        ClassifiedReview(
            source_index=1,
            summary="손에 색소가 남았다.",
            topics=[
                ExtractedTopic(
                    topic="staining",
                    sentiment="negative",
                    is_direct_experience=True,
                    evidence="purple hands",
                    confidence=0.85,
                ),
            ],
        ),
        ClassifiedReview(
            source_index=2,
            summary="향이 마음에 들었다.",
            topics=[
                ExtractedTopic(
                    topic="odor",
                    sentiment="positive",
                    is_direct_experience=True,
                    evidence="smells good",
                    confidence=0.99,
                ),
            ],
        ),
    ]

    result = aggregate_review_topics(
        classified_reviews=reviews,
        selection_criteria=selection_criteria,
    )

    assert result.sample_size == 3
    assert result.extracted_review_count == 3
    assert result.pattern_review_count == 2
    
    assert len(result.patterns) == 2

    first_pattern = result.patterns[0]

    assert first_pattern.topic == "staining"
    assert first_pattern.count == 2
    assert first_pattern.ratio == 0.6667
    assert first_pattern.label
    assert first_pattern.evidence

    assert result.ratio_denominator == 3
    assert result.selection_criteria is not None
    assert result.selection_criteria.rating_max == 3        
    assert result.selection_criteria.min_helpful_votes == 1

    assert result.selection_criteria.sort_by == "helpful_vote_desc"
    assert result.selection_criteria.requested_limit == 3

    first_pattern = result.patterns[0]
    assert first_pattern.count == 2
    assert first_pattern.ratio == 0.6667
    assert (first_pattern.ratio == round(first_pattern.count / result.ratio_denominator,4,))


def test_required_tool_execution_failure():
    tool_outputs = [
        {
            "tool_name": (
                "get_review_patterns_tool"
            ),
            "output": (
                "Error invoking tool "
                "'get_review_patterns_tool' "
                "with error: Field required"
            ),
        }
    ]

    result = (
        evaluate_required_tool_execution(
            tool_outputs=tool_outputs,
            required_tools=[
                "get_review_patterns_tool"
            ],
        )
    )

    assert result[
        "tool_execution_pass"
    ] is False

    assert result[
        "missing_successful_tools"
    ] == [
        "get_review_patterns_tool"
    ]


def test_required_tool_execution_success():
    tool_outputs = [
        {
            "tool_name": (
                "get_review_patterns_tool"
            ),
            "output": {
                "sample_size": 20,
                "patterns": [],
            },
        }
    ]

    result = (
        evaluate_required_tool_execution(
            tool_outputs=tool_outputs,
            required_tools=[
                "get_review_patterns_tool"
            ],
        )
    )

    assert result[
        "tool_execution_pass"
    ] is True

    assert result[
        "missing_successful_tools"
    ] == []