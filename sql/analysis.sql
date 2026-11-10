-- Module 2: find the products in trouble.
-- Run from the project root with the DuckDB CLI:  duckdb < sql/analysis.sql
-- Queries 2b and 2d take $asin, so they are commented out. To run one in the CLI,
-- pick a parent_asin from 2c, set it once:
--     SET VARIABLE asin = 'B09MVV717N';
-- then uncomment the query and change $asin to getvariable('asin').
-- In Python, pass asin as a named parameter instead.

SET TimeZone = 'UTC';
CREATE OR REPLACE VIEW reviews  AS FROM 'clean/reviews.parquet';
CREATE OR REPLACE VIEW products AS FROM 'clean/products.parquet';

-- 2-0. Sanity check after ingest
SELECT count(*)                                     AS reviews,
       min(reviewed_at)                             AS first_review,
       max(reviewed_at)                             AS last_review,
       round(avg(verified_purchase::INT) * 100, 1)  AS pct_verified
FROM reviews;

-- 2a. What does "normal" look like? (the J-shaped rating mix)
SELECT rating, count(*) AS n,
       round(100 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM reviews
GROUP BY rating
ORDER BY rating;

-- 2b. One product over time
-- SELECT date_trunc('month', reviewed_at) AS month,
--        count(*)                         AS reviews,
--        round(avg(rating), 2)            AS avg_rating
-- FROM reviews
-- WHERE parent_asin = $asin AND verified_purchase
-- GROUP BY month
-- ORDER BY month DESC
-- LIMIT 12;

-- 2c. The decline ranking (the core query)
--     Tune the two HAVING thresholds on real data until 5-10 credible products come back.
WITH bounds AS (
  SELECT max(reviewed_at) AS as_of FROM reviews
),
scored AS (
  SELECT r.parent_asin,
         r.reviewed_at >= b.as_of - INTERVAL 6 MONTH AS is_recent,
         r.rating
  FROM reviews r, bounds b
  WHERE r.verified_purchase
)
SELECT
  s.parent_asin,
  p.product,
  p.store,
  count(*) FILTER (WHERE is_recent)                   AS recent_reviews,
  round(avg(rating) FILTER (WHERE NOT is_recent), 2)  AS before_avg,
  round(avg(rating) FILTER (WHERE is_recent), 2)      AS recent_avg,
  round(avg(rating) FILTER (WHERE is_recent)
      - avg(rating) FILTER (WHERE NOT is_recent), 2)  AS change
FROM scored s
JOIN products p USING (parent_asin)
GROUP BY ALL
HAVING count(*) FILTER (WHERE is_recent) >= 20
   AND count(*) FILTER (WHERE NOT is_recent) >= 50
ORDER BY change, recent_reviews DESC
LIMIT 10;

-- 2d. The complaints worth reading (feeds the LLM)
-- SELECT rating, helpful_vote, title, text
-- FROM reviews
-- WHERE parent_asin = $asin
--   AND verified_purchase
--   AND rating <= 2
--   AND reviewed_at >= (SELECT max(reviewed_at) FROM reviews) - INTERVAL 6 MONTH
-- QUALIFY row_number() OVER (ORDER BY helpful_vote DESC, reviewed_at DESC) <= 40;
