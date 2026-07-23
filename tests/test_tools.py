# tests/test_tools.py

import json
import pytest

from tools import (
    get_helpful_reviews_tool,
    get_product_tool,
    get_rating_distribution_tool,
)


VALID_ASIN = "B005IHT8KI"
INVALID_ASIN = "ZZZZZZZZZZ"


def normalize_result(result):
    """JSON 문자열로 반환된 도구 결과를 Python 객체로 변환한다."""
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result

    return result


@pytest.fixture(scope="module")
def product():
    result = get_product_tool.invoke({
        "parent_asin": VALID_ASIN,
    })
    return normalize_result(result)


@pytest.fixture(scope="module")
def negative_reviews():
    result = get_helpful_reviews_tool.invoke({
        "parent_asin": VALID_ASIN,
        "limit": 20,
        "rating_max": 3,
        "min_helpful_votes": 1,
    })
    return normalize_result(result)


@pytest.fixture(scope="module")
def rating_distribution():
    result = get_rating_distribution_tool.invoke({
        "parent_asin": VALID_ASIN,
    })
    return normalize_result(result)


def test_product_asin_matches_requested_asin(product):
    """조회된 제품의 ASIN이 요청한 ASIN과 같아야 한다."""
    assert product
    assert product["parent_asin"] == VALID_ASIN
    assert product["analyzed_asin"] == VALID_ASIN


def test_returns_exactly_20_reviews(negative_reviews):
    """조건을 만족하는 데이터가 충분하면 리뷰 20개가 반환되어야 한다."""
    assert isinstance(negative_reviews, list)
    assert len(negative_reviews) == 20


def test_all_reviews_are_rating_3_or_lower(negative_reviews):
    """반환된 리뷰는 모두 평점 3점 이하여야 한다."""
    invalid_reviews = [
        review
        for review in negative_reviews
        if float(review["rating"]) > 3
    ]

    assert not invalid_reviews, (
        f"3점 초과 리뷰가 반환됐습니다: {invalid_reviews}"
    )


def test_all_reviews_belong_to_requested_parent_asin(negative_reviews):
    """모든 리뷰가 요청한 parent_asin에 속해야 한다."""
    missing_parent_asin = [
        review
        for review in negative_reviews
        if "parent_asin" not in review
    ]

    assert not missing_parent_asin, (
        "리뷰 반환값에 parent_asin이 없습니다. "
        "get_helpful_reviews_tool의 SELECT 항목에 "
        "parent_asin을 추가하세요."
    )

    other_product_reviews = [
        review
        for review in negative_reviews
        if review["parent_asin"] != VALID_ASIN
    ]

    assert not other_product_reviews, (
        f"다른 제품의 리뷰가 섞였습니다: {other_product_reviews}"
    )


def test_reviews_sorted_by_helpful_vote_descending(negative_reviews):
    """helpful_vote가 내림차순으로 정렬되어야 한다."""
    helpful_votes = [
        int(review.get("helpful_vote") or 0)
        for review in negative_reviews
    ]

    assert helpful_votes == sorted(helpful_votes, reverse=True), (
        f"helpful_vote가 내림차순이 아닙니다: {helpful_votes}"
    )


def test_rating_counts_sum_to_total_reviews(
    product,
    rating_distribution,
):
    """평점별 리뷰 수의 합이 제품의 전체 리뷰 수와 같아야 한다."""
    rating_total = sum(
        int(row["review_count"])
        for row in rating_distribution
    )

    product_total = int(product["review_count"])

    assert rating_total == product_total, (
        f"평점별 합계({rating_total})와 "
        f"전체 리뷰 수({product_total})가 다릅니다."
    )


@pytest.mark.parametrize(
    ("tool", "arguments", "expected_empty"),
    [
        (
            get_product_tool,
            {"parent_asin": INVALID_ASIN},
            (None, {}),
        ),
        (
            get_helpful_reviews_tool,
            {
                "parent_asin": INVALID_ASIN,
                "limit": 20,
                "rating_max": 3,
                "min_helpful_votes": 1,
            },
            (None, []),
        ),
        (
            get_rating_distribution_tool,
            {"parent_asin": INVALID_ASIN},
            (None, []),
        ),
    ],
)
def test_invalid_asin_returns_empty_without_error(
    tool,
    arguments,
    expected_empty,
):
    """존재하지 않는 ASIN은 예외 대신 빈 결과를 반환해야 한다."""
    result = tool.invoke(arguments)
    result = normalize_result(result)

    assert result in expected_empty, (
        f"{tool.name}이 빈 결과 대신 다음을 반환했습니다: {result}"
    )

@pytest.mark.parametrize("invalid_limit", [0, -1, 101])
def test_helpful_reviews_rejects_invalid_limit(invalid_limit):
    """limit은 허용 범위를 벗어나면 ValueError가 발생해야 한다."""
    with pytest.raises(ValueError):
        get_helpful_reviews_tool.invoke({
            "parent_asin": VALID_ASIN,
            "limit": invalid_limit,
            "rating_max": 3,
            "min_helpful_votes": 1,
        })

@pytest.mark.parametrize("valid_limit", [1, 100])
def test_helpful_reviews_accepts_valid_limit(valid_limit):
    reviews = normalize_result(
        get_helpful_reviews_tool.invoke({
            "parent_asin": VALID_ASIN,
            "limit": valid_limit,
            "rating_max": 3,
            "min_helpful_votes": 1,
        })
    )

    assert len(reviews) <= valid_limit