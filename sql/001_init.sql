CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS products (
    parent_asin        TEXT PRIMARY KEY,
    title              TEXT NOT NULL,
    store              TEXT,
    rating_number      BIGINT NOT NULL DEFAULT 0,
    average_rating     DOUBLE PRECISION,
    features           TEXT,
    description        TEXT,
    details            JSONB,
    price              DOUBLE PRECISION,
    review_count       BIGINT NOT NULL DEFAULT 0,
    negative_count     BIGINT NOT NULL DEFAULT 0,
    verified_count     BIGINT NOT NULL DEFAULT 0,
    min_review_at      TIMESTAMPTZ,
    max_review_at      TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id           BIGSERIAL PRIMARY KEY,
    parent_asin         TEXT NOT NULL
                        REFERENCES products(parent_asin)
                        ON DELETE CASCADE,
    asin                TEXT,
    user_id             TEXT,
    rating              DOUBLE PRECISION NOT NULL,
    review_title        TEXT,
    review_text         TEXT,
    reviewed_at         TIMESTAMPTZ NOT NULL,
    helpful_vote        BIGINT NOT NULL DEFAULT 0,
    verified_purchase   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_reviews_product_date
ON reviews(parent_asin, reviewed_at DESC);

CREATE INDEX IF NOT EXISTS idx_reviews_product_rating
ON reviews(parent_asin, rating);

CREATE INDEX IF NOT EXISTS idx_reviews_negative
ON reviews(parent_asin, reviewed_at DESC)
WHERE rating <= 3;

CREATE INDEX IF NOT EXISTS idx_reviews_product_helpful
ON reviews(parent_asin, helpful_vote DESC, reviewed_at DESC);

ANALYZE products;
ANALYZE reviews;
