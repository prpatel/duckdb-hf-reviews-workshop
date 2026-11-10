# /// script
# requires-python = ">=3.10"
# dependencies = ["duckdb==2.0.0"]
# ///
"""Module 1 and Module 3: turn raw Amazon Reviews JSONL into two Parquet tables.

The same script runs in both places; only --src and --out change.

  Local development, on the 24 MB sample (Module 1):
      hf download prpatel/voc-appliances-sample --repo-type dataset --local-dir raw-sample
      python scripts/ingest.py --src raw-sample

  For real, on the full 1.2 GB, as a Hugging Face Job next to the data (Module 3):
      hf jobs uv run -v hf://buckets/<you>/voc-workshop:/bucket scripts/ingest.py --out /bucket/clean

  (Mount at /bucket: Jobs reserve /data for the uploaded script. The Space mounts the
  same bucket at /data, and app.py reads /data/clean.)

--src is a folder (or hf:// prefix) laid out like the dataset's raw/ folder:
  <src>/review_categories/<Category>.jsonl
  <src>/meta_categories/meta_<Category>.jsonl
"""
import argparse
import os
import time

import duckdb

FULL = "hf://datasets/McAuley-Lab/Amazon-Reviews-2023/raw"

p = argparse.ArgumentParser()
p.add_argument("--src", default=FULL, help="raw/ folder: a local path or hf:// prefix")
p.add_argument("--out", default="clean", help="output folder for the Parquet files")
p.add_argument("--category", default="Appliances")
args = p.parse_args()

reviews_src = f"{args.src}/review_categories/{args.category}.jsonl"
meta_src = f"{args.src}/meta_categories/meta_{args.category}.jsonl"
os.makedirs(args.out, exist_ok=True)

con = duckdb.connect()
con.sql("SET TimeZone = 'UTC'")
print(f"duckdb {duckdb.__version__}: reading {args.src}  ->  writing {args.out}")

t0 = time.time()
con.sql(f"""
COPY (
  SELECT
    parent_asin,
    rating::TINYINT                 AS rating,
    title,
    text,
    to_timestamp(timestamp / 1000)  AS reviewed_at,
    helpful_vote,
    verified_purchase,
    user_id
  FROM read_json('{reviews_src}',
    format = 'newline_delimited',
    columns = {{
      rating: 'DOUBLE', title: 'VARCHAR', text: 'VARCHAR',
      asin: 'VARCHAR', parent_asin: 'VARCHAR', user_id: 'VARCHAR',
      timestamp: 'BIGINT', helpful_vote: 'INTEGER', verified_purchase: 'BOOLEAN'
    }})
  ORDER BY parent_asin, reviewed_at   -- one product's reviews sit together, so DuckDB skips the rest
) TO '{args.out}/reviews.parquet' (FORMAT parquet, COMPRESSION zstd)
""")
print(f"reviews.parquet written in {time.time() - t0:.1f}s")

t0 = time.time()
con.sql(f"""
COPY (
  SELECT
    parent_asin,
    title                      AS product,
    store,
    TRY_CAST(price AS DOUBLE)  AS price_usd,
    rating_number
  FROM read_json('{meta_src}',
    format = 'newline_delimited',
    columns = {{
      parent_asin: 'VARCHAR', title: 'VARCHAR', store: 'VARCHAR',
      price: 'VARCHAR', rating_number: 'INTEGER'
    }})
) TO '{args.out}/products.parquet' (FORMAT parquet, COMPRESSION zstd)
""")
print(f"products.parquet written in {time.time() - t0:.1f}s")

con.sql(f"""
SELECT count(*)                                     AS reviews,
       count(DISTINCT parent_asin)                  AS products,
       min(reviewed_at)                             AS first_review,
       max(reviewed_at)                             AS last_review,
       round(avg(verified_purchase::INT) * 100, 1)  AS pct_verified
FROM '{args.out}/reviews.parquet'
""").show()
