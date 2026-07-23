
/* 업로드 데이터 개수 */

SELECT
    (SELECT COUNT(*) FROM products) AS products,
    (SELECT COUNT(*) FROM reviews) AS reviews,
    (SELECT COUNT(*) FROM reviews r LEFT JOIN products p ON p.parent_asin = r.parent_asin WHERE p.parent_asin IS NULL) AS orphan_reviews;

/* 통계 일치 여부 */

SELECT COUNT(*) AS mismatched_products
FROM products p
LEFT JOIN (
    SELECT parent_asin, COUNT(*) AS actual_count
    FROM reviews
    GROUP BY parent_asin
) r ON r.parent_asin = p.parent_asin
WHERE p.review_count <> COALESCE(r.actual_count, 0);

/* 단일 ASIN 조건 검증*/

SELECT COUNT(*) AS multiple_asin_products
FROM (
    SELECT parent_asin
    FROM reviews
    GROUP BY parent_asin
    HAVING COUNT(DISTINCT asin) <> 1
) t;

/* 제품에 저장된 analyzed_asin과 리뷰 ASIN 불일치 검증 */

SELECT COUNT(*) AS asin_mismatches
FROM reviews r
JOIN products p ON p.parent_asin = r.parent_asin
WHERE r.asin IS DISTINCT FROM p.analyzed_asin;

/* 부정 리뷰 수와 검증 구매 리뷰 수 불일치 확인 */
WITH actual AS (
    SELECT parent_asin,
           COUNT(*) FILTER (WHERE rating <= 3) AS negative_count,
           COUNT(*) FILTER (WHERE verified_purchase IS TRUE) AS verified_count
    FROM reviews
    GROUP BY parent_asin
)
SELECT
    COUNT(*) FILTER (WHERE p.negative_count <> a.negative_count) AS negative_mismatches,
    COUNT(*) FILTER (WHERE p.verified_count <> a.verified_count) AS verified_mismatches
FROM products p
JOIN actual a ON a.parent_asin = p.parent_asin;

