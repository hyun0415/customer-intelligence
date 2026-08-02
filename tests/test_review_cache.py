from src.analysis import review_extractor
from src.analysis.schemas import ClassifiedReview


def test_cache_hit_skips_llm(monkeypatch):
    cached_result = ClassifiedReview(
        source_index=0,
        topics=[],
        summary="cached result",
    )

    monkeypatch.setattr(
        review_extractor,
        "get_cached_review",
        lambda cache_key: cached_result,
    )

    def fail_if_llm_called():
        raise AssertionError("LLM이 호출되면 안 됩니다.")

    monkeypatch.setattr(
        review_extractor,
        "get_extractor_model",
        fail_if_llm_called,
    )

    result = review_extractor.extract_review_topics(
        source_index=3,
        review_title="Test",
        review_text="The smell was terrible.",
    )

    assert result.summary == "cached result"


def test_cache_hit_replaces_source_index(monkeypatch):
    cached_result = ClassifiedReview(
        source_index=0,
        topics=[],
        summary="cached result",
    )

    monkeypatch.setattr(
        review_extractor,
        "get_cached_review",
        lambda cache_key: cached_result,
    )

    result = review_extractor.extract_review_topics(
        source_index=7,
        review_title="Test",
        review_text="The smell was terrible.",
    )

    assert result.source_index == 7
    assert cached_result.source_index == 0