import argparse
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import orjson
import pandas as pd
from tqdm import tqdm

INCLUDE = re.compile(r"\bshampoos?\b", re.IGNORECASE)
EXCLUDE = re.compile(
    r"\b(pet|dog|cat|brush|bowl|cape|dispenser|conditioner|dry shampoo)\b",
    re.IGNORECASE,
)
EXPECTED_PRODUCTS = 547
EXPECTED_REVIEWS = 105_060


def select_shampoo_products(metadata_path, minimum_ratings=300):
    products = []

    with gzip.open(metadata_path, "rb") as source:
        for line in tqdm(source, desc="상품 후보 검색", unit="행"):
            product = orjson.loads(line)
            title = product.get("title") or ""
            rating_number = product.get("rating_number") or 0

            if (
                not INCLUDE.search(title)
                or EXCLUDE.search(title)
                or rating_number < minimum_ratings
            ):
                continue
            if not product.get("features") and not product.get("description"):
                continue

            products.append(
                {
                    "parent_asin": product["parent_asin"],
                    "title": title,
                    "store": product.get("store"),
                    "rating_number": rating_number,
                    "average_rating": product.get("average_rating"),
                    "features": product.get("features"),
                    "description": product.get("description"),
                    "details": product.get("details"),
                    "price": product.get("price"),
                }
            )

    return pd.DataFrame(products)


def aggregate_review_stats(review_path, candidate_parent_asin):
    candidate_parent_asin = set(candidate_parent_asin)
    review_count = Counter()
    negative_count = Counter()
    verified_count = Counter()
    min_timestamp = {}
    max_timestamp = {}

    with gzip.open(review_path, "rb") as source:
        for line in tqdm(source, desc="리뷰 통계 집계", unit="행"):
            review = orjson.loads(line)
            parent_asin = review.get("parent_asin")
            if parent_asin not in candidate_parent_asin:
                continue

            review_count[parent_asin] += 1
            rating = review.get("rating")
            if rating is not None and rating <= 3:
                negative_count[parent_asin] += 1
            if review.get("verified_purchase") is True:
                verified_count[parent_asin] += 1

            timestamp = review.get("timestamp")
            if timestamp is not None:
                min_timestamp[parent_asin] = min(
                    timestamp, min_timestamp.get(parent_asin, timestamp)
                )
                max_timestamp[parent_asin] = max(
                    timestamp, max_timestamp.get(parent_asin, timestamp)
                )

    return {
        "review_count": review_count,
        "negative_count": negative_count,
        "verified_count": verified_count,
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
    }


def attach_stats(products, stats):
    products = products.copy()

    for column, mapping in stats.items():
        products[column] = products["parent_asin"].map(mapping)
        if column.endswith("_count"):
            products[column] = products[column].fillna(0).astype("int64")

    return products


def select_eligible_products(products, minimum_reviews=50, minimum_negative=10):
    has_text = products["features"].str.len().gt(0) | products[
        "description"
    ].str.len().gt(0)
    eligible = products[
        (products["review_count"] >= minimum_reviews)
        & (products["negative_count"] >= minimum_negative)
        & has_text
    ].copy()

    for column in ["features", "description"]:
        eligible[column] = eligible[column].apply(
            lambda value: (
                " ".join(map(str, value)) if isinstance(value, list) else value
            )
        )

    return eligible.drop_duplicates("parent_asin")


def load_eligible_reviews(review_path, parent_asins):
    parent_asins = set(parent_asins)
    reviews = []

    with gzip.open(review_path, "rb") as source:
        for line in tqdm(source, desc="선정 상품 리뷰 적재", unit="행"):
            review = orjson.loads(line)
            if review.get("parent_asin") not in parent_asins:
                continue

            reviews.append(
                {
                    "parent_asin": review.get("parent_asin"),
                    "asin": review.get("asin"),
                    "user_id": review.get("user_id"),
                    "rating": review.get("rating"),
                    "review_title": review.get("title"),
                    "review_text": review.get("text"),
                    "timestamp": review.get("timestamp"),
                    "helpful_vote": review.get("helpful_vote"),
                    "verified_purchase": review.get("verified_purchase"),
                }
            )

    return pd.DataFrame(reviews)


def prepare_reviews(reviews):
    reviews = reviews.copy()
    reviews["rating"] = pd.to_numeric(reviews["rating"], errors="coerce")
    reviews["timestamp"] = pd.to_numeric(reviews["timestamp"], errors="coerce")
    reviews["helpful_vote"] = (
        pd.to_numeric(reviews["helpful_vote"], errors="coerce")
        .fillna(0)
        .astype("int64")
    )
    reviews["verified_purchase"] = (
        reviews["verified_purchase"]
        .astype(str)
        .str.lower()
        .map({"true": True, "false": False})
        .fillna(False)
    )
    return reviews.drop_duplicates(
        subset=["parent_asin", "asin", "user_id", "timestamp", "review_text"]
    ).reset_index(drop=True)


def filter_single_asin_products(products, reviews):
    asin_stats = (
        reviews.groupby("parent_asin")
        .agg(asin_count=("asin", "nunique"), analyzed_asin=("asin", "first"))
        .reset_index()
    )
    single_asin = asin_stats.loc[
        asin_stats["asin_count"] == 1, ["parent_asin", "analyzed_asin"]
    ]
    products = products.merge(
        single_asin, on="parent_asin", how="inner", validate="one_to_one"
    )
    reviews = reviews.merge(
        single_asin,
        left_on=["parent_asin", "asin"],
        right_on=["parent_asin", "analyzed_asin"],
        how="inner",
        validate="many_to_one",
    )
    return products.reset_index(drop=True), reviews.reset_index(drop=True)


def rebuild_product_stats(products, reviews):
    stats = (
        reviews.groupby("parent_asin")
        .agg(
            review_count=("parent_asin", "size"),
            negative_count=("rating", lambda values: values.le(3).sum()),
            verified_count=("verified_purchase", "sum"),
            min_timestamp=("timestamp", "min"),
            max_timestamp=("timestamp", "max"),
        )
        .reset_index()
    )
    stat_columns = [
        "review_count",
        "negative_count",
        "verified_count",
        "min_timestamp",
        "max_timestamp",
    ]
    return products.drop(columns=stat_columns, errors="ignore").merge(
        stats, on="parent_asin", how="inner", validate="one_to_one"
    )


def validate_data(products, reviews):
    actual = (
        reviews.groupby("parent_asin")
        .agg(
            actual_review_count=("parent_asin", "size"),
            actual_negative_count=("rating", lambda values: values.le(3).sum()),
            actual_verified_count=("verified_purchase", "sum"),
            actual_asin_count=("asin", "nunique"),
        )
        .reset_index()
    )
    check = products.merge(actual, on="parent_asin", how="left", validate="one_to_one")
    failures = {
        "review_count_mismatch": check["review_count"]
        .ne(check["actual_review_count"])
        .sum(),
        "negative_count_mismatch": check["negative_count"]
        .ne(check["actual_negative_count"])
        .sum(),
        "verified_count_mismatch": check["verified_count"]
        .ne(check["actual_verified_count"])
        .sum(),
        "multiple_asin_products": check["actual_asin_count"].ne(1).sum(),
        "wrong_asin_reviews": reviews["asin"].ne(reviews["analyzed_asin"]).sum(),
    }
    if any(failures.values()):
        raise RuntimeError(f"데이터 검증 실패: {failures}")


def build_dataset(metadata_path, review_path):
    products = select_shampoo_products(metadata_path)
    stats = aggregate_review_stats(review_path, products["parent_asin"])
    products = select_eligible_products(attach_stats(products, stats))
    reviews = prepare_reviews(
        load_eligible_reviews(review_path, products["parent_asin"])
    )
    products, reviews = filter_single_asin_products(products, reviews)
    products = rebuild_product_stats(products, reviews)

    has_text = products["features"].fillna("").astype(str).str.strip().ne(
        ""
    ) | products["description"].fillna("").astype(str).str.strip().ne("")
    products = products[
        (products["review_count"] >= 50) & (products["negative_count"] >= 10) & has_text
    ].copy()
    reviews = reviews[reviews["parent_asin"].isin(products["parent_asin"])].copy()
    products = rebuild_product_stats(products, reviews).reset_index(drop=True)
    reviews = reviews.reset_index(drop=True)
    validate_data(products, reviews)
    return products, reviews


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_outputs(products, reviews, output_dir, metadata_path, review_path):
    output_dir.mkdir(parents=True, exist_ok=True)
    products_path = output_dir / "products_rds.parquet"
    reviews_path = output_dir / "reviews_rds.parquet"
    manifest_path = output_dir / "dataset_manifest.json"

    products.to_parquet(products_path, index=False)
    reviews.to_parquet(reviews_path, index=False)
    manifest = {
        "dataset": "Amazon Reviews 2023 / Beauty_and_Personal_Care",
        "source_files": [metadata_path.name, review_path.name],
        "filters": {
            "title_include": INCLUDE.pattern,
            "title_exclude": EXCLUDE.pattern,
            "minimum_ratings": 300,
            "minimum_reviews": 50,
            "minimum_negative_reviews": 10,
            "single_review_asin_per_parent_asin": True,
        },
        "outputs": {
            products_path.name: {
                "rows": len(products),
                "sha256": sha256(products_path),
                "columns": list(products.columns),
            },
            reviews_path.name: {
                "rows": len(reviews),
                "sha256": sha256(reviews_path),
                "columns": list(reviews.columns),
            },
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return products_path, reviews_path, manifest_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Amazon Reviews 2023에서 프로젝트용 샴푸 리뷰 데이터를 생성합니다."
    )
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--skip-count-check", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    products, reviews = build_dataset(args.metadata, args.reviews)

    if not args.skip_count_check:
        counts = (len(products), len(reviews))
        expected = (EXPECTED_PRODUCTS, EXPECTED_REVIEWS)
        if counts != expected:
            raise RuntimeError(
                f"예상 행 수와 다릅니다: products={counts[0]:,}, "
                f"reviews={counts[1]:,}; expected={expected}"
            )

    paths = write_outputs(
        products, reviews, args.output_dir, args.metadata, args.reviews
    )
    print(f"완료: products={len(products):,}, reviews={len(reviews):,}")
    for path in paths:
        print(f"- {path}")


if __name__ == "__main__":
    main()
