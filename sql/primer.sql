-- DuckDB primer: a first hour with DuckDB, on the raw sample you downloaded.
--
-- Run it all at once:      duckdb < sql/primer.sql
-- Or step by step (better): open `duckdb`, then copy each statement in, one at a time.
-- Run from the workshop folder; it reads raw-sample/ and writes two small
-- primer_*.parquet files there.

-- ===========================================================================
-- P0. Dot commands: shell settings, not SQL. They start with "." and have no ";"
-- ===========================================================================
-- .help              list every dot command
-- .tables            list tables and views
-- .schema            show CREATE statements
-- .read file.sql     run a SQL file
-- .output file.txt   send results to a file (.output alone sends them back to the screen)
-- .quit              exit (or Ctrl-D)
.timer on
.maxrows 20

-- ===========================================================================
-- P1. Hello, DuckDB
-- ===========================================================================
SELECT 42 AS answer, version() AS duckdb_version;

-- Integer division gives a decimal here. SQLite says 0. Try it.
SELECT 1 / 2 AS half, 7 // 2 AS integer_division;

-- Postgres-style casts with ::
SELECT '42'::INTEGER         AS int_from_text,
       '2023-09-12'::DATE    AS a_date,
       4.0::TINYINT          AS tiny,
       true::INT             AS one;

-- ===========================================================================
-- P2. Query a file directly. The file IS the table.
-- ===========================================================================
-- FROM-first: "SELECT *" is implied.
.mode line
FROM 'raw-sample/review_categories/Appliances.jsonl' LIMIT 2;
.mode duckbox

-- What did DuckDB work out about the file's structure?
DESCRIBE FROM 'raw-sample/review_categories/Appliances.jsonl';

-- ===========================================================================
-- P3. SUMMARIZE: a profile of every column in one command
-- ===========================================================================
SUMMARIZE FROM 'raw-sample/review_categories/Appliances.jsonl';

-- ===========================================================================
-- P4. Load a table, with casts and timestamps
-- ===========================================================================
-- Always UTC, so everyone in the room gets the same months.
SET TimeZone = 'UTC';

-- `timestamp` is Unix milliseconds; to_timestamp() wants seconds.
-- A TABLE copies the data into memory (fast to query); a VIEW would re-read the file.
CREATE OR REPLACE TABLE reviews AS
SELECT parent_asin,
       rating::TINYINT                 AS rating,
       title,
       text,
       to_timestamp(timestamp / 1000)  AS reviewed_at,
       helpful_vote,
       verified_purchase
FROM 'raw-sample/review_categories/Appliances.jsonl';

.tables
SELECT count(*)                                     AS reviews,
       count(DISTINCT parent_asin)                  AS products,
       min(reviewed_at)::DATE                       AS first_day,
       max(reviewed_at)::DATE                       AS last_day,
       round(avg(verified_purchase::INT) * 100, 1)  AS pct_verified   -- bool -> 0/1 -> share
FROM reviews;

-- ===========================================================================
-- P5. GROUP BY ALL and FILTER
-- ===========================================================================
-- GROUP BY ALL groups by every column that isn't an aggregate. No repeating yourself.
SELECT year(reviewed_at) AS year, count(*) AS reviews, round(avg(rating), 2) AS avg_rating
FROM reviews
GROUP BY ALL
ORDER BY year DESC
LIMIT 5;

-- FILTER: aggregate over a subset of each group's rows. Two averages, one pass.
-- Do verified buyers rate differently from unverified ones?
SELECT parent_asin,
       count(*)                                                  AS reviews,
       round(avg(rating) FILTER (WHERE verified_purchase), 2)    AS verified_avg,
       round(avg(rating) FILTER (WHERE NOT verified_purchase), 2) AS unverified_avg
FROM reviews
GROUP BY ALL
HAVING count(*) FILTER (WHERE NOT verified_purchase) >= 20
ORDER BY reviews DESC
LIMIT 5;

-- Exercise 1: write the same query with CASE WHEN instead of FILTER:
--   avg(CASE WHEN verified_purchase THEN rating END)
-- Which is easier to read?

-- ===========================================================================
-- P6. QUALIFY: top N per group without a subquery
-- ===========================================================================
-- The single most helpful review of each of the 5 most-reviewed products.
SELECT parent_asin, helpful_vote, rating, left(title, 50) AS title
FROM reviews
WHERE parent_asin IN (SELECT parent_asin FROM reviews GROUP BY ALL ORDER BY count(*) DESC LIMIT 5)
QUALIFY row_number() OVER (PARTITION BY parent_asin ORDER BY helpful_vote DESC) = 1
ORDER BY helpful_vote DESC;

-- Exercise 2: rewrite it without QUALIFY. You'll need a subquery that computes
-- row_number() AS rn, and an outer WHERE rn = 1.

-- ===========================================================================
-- P7. Variables: give a value a name, then reuse it
-- ===========================================================================
SET VARIABLE asin = 'B09MVV717N';      -- a countertop ice maker

SELECT date_trunc('month', reviewed_at)::DATE AS month,
       count(*)                               AS reviews,
       round(avg(rating), 2)                  AS avg_rating
FROM reviews
WHERE parent_asin = getvariable('asin')
GROUP BY ALL
ORDER BY month DESC
LIMIT 6;

-- Exercise 3: time zones. Run this, then SET TimeZone = 'America/Los_Angeles';
-- and run it again. Why do the counts move? Set it back to 'UTC' afterwards.
SELECT date_trunc('month', reviewed_at)::DATE AS month, count(*) AS reviews
FROM reviews
WHERE reviewed_at >= '2023-01-01'
GROUP BY ALL
ORDER BY month;

-- ===========================================================================
-- P8. Parquet: why we convert the JSON once
-- ===========================================================================
-- COPY writes a query's result to a file. Sorting by product keeps each
-- product's reviews together. ROW_GROUP_SIZE is small only so a 50K-row
-- sample gets several row groups to look at; the default is about 122,880 rows.
COPY (FROM reviews ORDER BY parent_asin)
TO 'primer_sorted.parquet' (FORMAT parquet, ROW_GROUP_SIZE 5000);

-- The same rows, shuffled.
COPY (FROM reviews ORDER BY random())
TO 'primer_random.parquet' (FORMAT parquet, ROW_GROUP_SIZE 5000);

-- Same question, three sources. Watch the Run Time lines.
SELECT count(*) FROM 'raw-sample/review_categories/Appliances.jsonl' WHERE parent_asin = getvariable('asin');
SELECT count(*) FROM 'primer_sorted.parquet'                          WHERE parent_asin = getvariable('asin');

-- Each row group stores min and max per column. Sorted: narrow, non-overlapping ranges.
SELECT row_group_id, stats_min, stats_max
FROM parquet_metadata('primer_sorted.parquet')
WHERE path_in_schema = 'parent_asin';

-- Shuffled: every row group spans almost everything.
SELECT row_group_id, stats_min, stats_max
FROM parquet_metadata('primer_random.parquet')
WHERE path_in_schema = 'parent_asin';

-- ===========================================================================
-- P9. EXPLAIN ANALYZE: what DuckDB actually did
-- ===========================================================================
-- Look for "Row Groups Scanned" in the TABLE_SCAN box.
EXPLAIN ANALYZE SELECT count(*) FROM 'primer_sorted.parquet' WHERE parent_asin = getvariable('asin');
EXPLAIN ANALYZE SELECT count(*) FROM 'primer_random.parquet' WHERE parent_asin = getvariable('asin');

-- Sorted skips all but one row group; shuffled reads them all. On 2.1M reviews
-- over a network, that's the difference between fetching one chunk and fetching
-- the whole file. scripts/ingest.py does this sort for real in Module 1.
