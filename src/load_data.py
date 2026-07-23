import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb


BASE_DIR = Path(__file__).resolve().parent.parent
PRODUCTS_PATH = BASE_DIR / "data" / "products_rds.parquet"
REVIEWS_PATH = BASE_DIR / "data" / "reviews_rds.parquet"

load_dotenv(BASE_DIR / ".env")


def null_to_none(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    return value


def to_datetime(timestamp_ms):
    timestamp_ms = null_to_none(timestamp_ms)

    if timestamp_ms is None:
        return None

    return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)


def to_jsonb(value):
    value = null_to_none(value)

    if value is None:
        return None

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {"raw": value}

    return Jsonb(value)


def connect():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def load_products(conn, products):
    sql = """
        COPY products (
            parent_asin, title, store, rating_number, average_rating,
            features, description, details, price, review_count,
            negative_count, verified_count, min_review_at, max_review_at
        ) FROM STDIN
    """

    with conn.cursor() as cur:
        with cur.copy(sql) as copy:
            for row in products.itertuples(index=False):
                copy.write_row((
                    row.parent_asin,
                    row.title,
                    null_to_none(row.store),
                    int(row.rating_number),
                    null_to_none(row.average_rating),
                    null_to_none(row.features),
                    null_to_none(row.description),
                    to_jsonb(row.details),
                    null_to_none(row.price),
                    int(row.review_count),
                    int(row.negative_count),
                    int(row.verified_count),
                    to_datetime(row.min_timestamp),
                    to_datetime(row.max_timestamp),
                ))

    print(f"products 적재 완료: {len(products):,}건")


def load_reviews(conn, reviews):
    sql = """
        COPY reviews (
            parent_asin, asin, user_id, rating, review_title,
            review_text, reviewed_at, helpful_vote, verified_purchase
        ) FROM STDIN
    """

    with conn.cursor() as cur:
        with cur.copy(sql) as copy:
            for row in reviews.itertuples(index=False):
                copy.write_row((
                    row.parent_asin,
                    null_to_none(row.asin),
                    null_to_none(row.user_id),
                    float(row.rating),
                    null_to_none(row.review_title),
                    null_to_none(row.review_text),
                    to_datetime(row.timestamp),
                    int(row.helpful_vote),
                    bool(row.verified_purchase),
                ))

    print(f"reviews 적재 완료: {len(reviews):,}건")


def verify_empty_tables(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM products),
                (SELECT COUNT(*) FROM reviews)
        """)
        product_count, review_count = cur.fetchone()

    if product_count or review_count:
        raise RuntimeError(
            f"테이블이 비어 있지 않습니다: "
            f"products={product_count:,}, reviews={review_count:,}"
        )


def verify_result(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM products),
                (SELECT COUNT(*) FROM reviews),
                (SELECT COUNT(*) FROM reviews r
                 LEFT JOIN products p ON p.parent_asin = r.parent_asin
                 WHERE p.parent_asin IS NULL)
        """)
        product_count, review_count, orphan_count = cur.fetchone()

    print("\n적재 결과")
    print(f"- products: {product_count:,}건")
    print(f"- reviews: {review_count:,}건")
    print(f"- 연결되지 않은 리뷰: {orphan_count:,}건")


def main():
    products = pd.read_parquet(PRODUCTS_PATH)
    reviews = pd.read_parquet(REVIEWS_PATH)

    print(f"Parquet products: {len(products):,}건")
    print(f"Parquet reviews: {len(reviews):,}건")

    with connect() as conn:
        verify_empty_tables(conn)
        load_products(conn, products)
        load_reviews(conn, reviews)
        verify_result(conn)

    print("\n모든 데이터가 정상적으로 적재되었습니다.")


if __name__ == "__main__":
    main()