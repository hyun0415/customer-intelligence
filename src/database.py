import os
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import load_dotenv
from psycopg.rows import dict_row


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def connect():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row,
    )


def get_product(parent_asin):
    sql = """
        SELECT parent_asin, analyzed_asin, title, store, rating_number,
               average_rating, features, description, details, price,
               review_count, negative_count, verified_count,
               min_review_at, max_review_at
        FROM products
        WHERE parent_asin = %s
    """

    with connect() as conn:
        return conn.execute(sql, (parent_asin,)).fetchone()


def get_products(limit=20, offset=0):
    sql = """
        SELECT parent_asin, analyzed_asin, title, store, average_rating,
               price, review_count, negative_count, verified_count
        FROM products
        ORDER BY review_count DESC
        LIMIT %s OFFSET %s
    """

    with connect() as conn:
        return conn.execute(sql, (limit, offset)).fetchall()


def get_recent_reviews(parent_asin, limit=20):
    sql = """
        SELECT asin, user_id, rating, review_title, review_text,
               reviewed_at, helpful_vote, verified_purchase
        FROM reviews
        WHERE parent_asin = %s
        ORDER BY reviewed_at DESC
        LIMIT %s
    """

    with connect() as conn:
        return conn.execute(sql, (parent_asin, limit)).fetchall()


def get_negative_reviews(parent_asin, limit=20):
    sql = """
        SELECT asin, user_id, rating, review_title, review_text,
               reviewed_at, helpful_vote, verified_purchase
        FROM reviews
        WHERE parent_asin = %s AND rating <= 3
        ORDER BY reviewed_at DESC
        LIMIT %s
    """

    with connect() as conn:
        return conn.execute(sql, (parent_asin, limit)).fetchall()


def get_rating_distribution(parent_asin):
    sql = """
        SELECT rating, COUNT(*) AS review_count
        FROM reviews
        WHERE parent_asin = %s
        GROUP BY rating
        ORDER BY rating
    """

    with connect() as conn:
        return conn.execute(sql, (parent_asin,)).fetchall()


def validate_limit(limit, maximum=100):
    limit = int(limit)

    if limit < 1 or limit > maximum:
        raise ValueError(f"limit은 1~{maximum} 사이여야 합니다.")

    return limit


def get_reviews_by_date(
    parent_asin,
    start_at,
    end_at,
    rating_max=None,
    verified_only=False,
    limit=100,
):
    limit = validate_limit(limit)

    query = """
        SELECT asin, user_id, rating, review_title, review_text,
               reviewed_at, helpful_vote, verified_purchase
        FROM reviews
        WHERE parent_asin = %s
          AND reviewed_at >= %s
          AND reviewed_at < %s
    """

    params = [parent_asin, start_at, end_at]

    if rating_max is not None:
        query += " AND rating <= %s"
        params.append(rating_max)

    if verified_only:
        query += " AND verified_purchase IS TRUE"

    query += " ORDER BY reviewed_at DESC LIMIT %s"
    params.append(limit)

    with connect() as conn:
        return conn.execute(query, params).fetchall()


def get_monthly_review_trend(parent_asin, start_at=None, end_at=None):
    query = """
        SELECT
            DATE_TRUNC('month', reviewed_at)::date AS month,
            COUNT(*) AS review_count,
            ROUND(AVG(rating)::numeric, 2) AS average_rating,
            COUNT(*) FILTER (WHERE rating <= 3) AS negative_count,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE rating <= 3)
                / NULLIF(COUNT(*), 0),
                2
            ) AS negative_ratio,
            COUNT(*) FILTER (
                WHERE verified_purchase IS TRUE
            ) AS verified_count
        FROM reviews
        WHERE parent_asin = %s
    """

    params = [parent_asin]

    if start_at is not None:
        query += " AND reviewed_at >= %s"
        params.append(start_at)

    if end_at is not None:
        query += " AND reviewed_at < %s"
        params.append(end_at)

    query += """
        GROUP BY DATE_TRUNC('month', reviewed_at)
        ORDER BY month
    """

    with connect() as conn:
        return conn.execute(query, params).fetchall()


MAX_LIMIT = 100

def validate_limit(limit):

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit은 정수여야 합니다.")

    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit은 1 이상 {MAX_LIMIT} 이하여야 합니다.")

    return limit


def get_helpful_reviews(
    parent_asin,
    limit=20,
    rating_max=None,
    min_helpful_votes=1,
):
    limit = validate_limit(limit)

    query = """
        SELECT parent_asin, asin, user_id, rating,
               review_title, review_text, reviewed_at,
               helpful_vote, verified_purchase
        FROM reviews
        WHERE parent_asin = %s
          AND helpful_vote >= %s
    """

    params = [parent_asin, min_helpful_votes]

    if rating_max is not None:
        query += " AND rating <= %s"
        params.append(rating_max)

    query += """
        ORDER BY helpful_vote DESC, reviewed_at DESC
        LIMIT %s
    """
    params.append(limit)

    with connect() as conn:
        return conn.execute(query, params).fetchall()


def search_products(keyword, limit=20):
    limit = validate_limit(limit)

    keyword = keyword.strip()

    if not keyword:
        return []

    query = """
        SELECT parent_asin, analyzed_asin, title, store,
               average_rating, price, review_count,
               negative_count, verified_count,
               ROUND(
                   100.0 * negative_count / NULLIF(review_count, 0),
                   2
               ) AS negative_ratio
        FROM products
        WHERE title ILIKE %s
           OR store ILIKE %s
        ORDER BY
            CASE
                WHEN store ILIKE %s THEN 0
                WHEN title ILIKE %s THEN 1
                ELSE 2
            END,
            review_count DESC
        LIMIT %s
    """

    contains = f"%{keyword}%"
    exact = keyword

    params = [contains, contains, exact, exact, limit]

    with connect() as conn:
        return conn.execute(query, params).fetchall()


def compare_products(parent_asins):
    parent_asins = list(dict.fromkeys(parent_asins))

    if not parent_asins:
        return []

    if len(parent_asins) > 20:
        raise ValueError("한 번에 비교할 수 있는 제품은 최대 20개입니다.")

    query = """
        SELECT
            parent_asin,
            analyzed_asin,
            title,
            store,
            average_rating,
            price,
            review_count,
            negative_count,
            ROUND(
                100.0 * negative_count / NULLIF(review_count, 0),
                2
            ) AS negative_ratio,
            verified_count,
            ROUND(
                100.0 * verified_count / NULLIF(review_count, 0),
                2
            ) AS verified_ratio,
            min_review_at,
            max_review_at
        FROM products
        WHERE parent_asin = ANY(%s)
        ORDER BY review_count DESC
    """

    with connect() as conn:
        return conn.execute(query, (parent_asins,)).fetchall()

if __name__ == "__main__":
    product_id = "B005IHT8KI"

    print("기간별 리뷰")
    print(
        get_reviews_by_date(
            parent_asin=product_id,
            start_at="2023-01-01",
            end_at="2024-01-01",
            rating_max=3,
            limit=3,
        )
    )

    print("\n월별 추세")
    print(
        get_monthly_review_trend(
            parent_asin=product_id,
            start_at="2022-01-01",
            end_at="2024-01-01",
        )
    )

    print("\n도움이 많이 된 부정 리뷰")
    print(
        get_helpful_reviews(
            parent_asin=product_id,
            rating_max=3,
            min_helpful_votes=1,
            limit=3,
        )
    )

    print("\n제품 검색")
    products = search_products("Neutrogena", limit=5)
    print(products)

    print("\n제품 비교")
    product_ids = [product["parent_asin"] for product in products[:3]]
    print(compare_products(product_ids))