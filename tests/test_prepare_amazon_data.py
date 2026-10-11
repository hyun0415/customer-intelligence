import pandas as pd
import pytest

from scripts.prepare_amazon_data import (
    filter_single_asin_products,
    prepare_reviews,
    validate_data,
)


def test_prepare_reviews_deduplicates_and_normalizes_values():
    reviews = pd.DataFrame(
        [
            {
                "parent_asin": "P1",
                "asin": "A1",
                "user_id": "U1",
                "rating": "2",
                "review_text": "dry",
                "timestamp": "1000",
                "helpful_vote": None,
                "verified_purchase": "true",
            },
            {
                "parent_asin": "P1",
                "asin": "A1",
                "user_id": "U1",
                "rating": "2",
                "review_text": "dry",
                "timestamp": "1000",
                "helpful_vote": None,
                "verified_purchase": "true",
            },
        ]
    )

    result = prepare_reviews(reviews)

    assert len(result) == 1
    assert result.loc[0, "helpful_vote"] == 0
    assert bool(result.loc[0, "verified_purchase"]) is True


def test_single_asin_filter_keeps_tracking_column():
    products = pd.DataFrame(
        [
            {"parent_asin": "P1"},
            {"parent_asin": "P2"},
        ]
    )
    reviews = pd.DataFrame(
        [
            {"parent_asin": "P1", "asin": "A1"},
            {"parent_asin": "P2", "asin": "A2"},
            {"parent_asin": "P2", "asin": "A3"},
        ]
    )

    filtered_products, filtered_reviews = filter_single_asin_products(products, reviews)

    assert filtered_products.to_dict("records") == [
        {"parent_asin": "P1", "analyzed_asin": "A1"}
    ]
    assert filtered_reviews["asin"].tolist() == ["A1"]


def test_validate_data_rejects_analyzed_asin_mismatch():
    products = pd.DataFrame(
        [
            {
                "parent_asin": "P1",
                "review_count": 1,
                "negative_count": 1,
                "verified_count": 1,
            }
        ]
    )
    reviews = pd.DataFrame(
        [
            {
                "parent_asin": "P1",
                "asin": "A2",
                "analyzed_asin": "A1",
                "rating": 2,
                "verified_purchase": True,
            }
        ]
    )

    with pytest.raises(RuntimeError, match="wrong_asin_reviews"):
        validate_data(products, reviews)
