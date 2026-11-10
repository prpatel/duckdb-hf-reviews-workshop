"""Test the workshop SQL against synthetic data shaped like Amazon Reviews 2023.

Network access to the Hub is blocked here, so this writes local JSONL files with
the same field names and types (including the 'None' price strings seen in the
item metadata) and runs every query from the workshop against them.
"""
import json, random, sys, os
import duckdb

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
random.seed(7)

# --- synthetic raw files -------------------------------------------------
products = [f"B0{n:08d}" for n in range(60)]
start_ms = 1_420_070_400_000   # 2015-01-01
end_ms = 1_694_000_000_000     # 2023-09-06, the dataset's end
troubled = set(products[:5])   # these decline sharply in the last 6 months

with open(f"{out}/Appliances.jsonl", "w") as f:
    for i in range(40_000):
        p = random.choice(products)
        ts = random.randint(start_ms, end_ms)
        recent = ts > end_ms - 183 * 86_400_000
        if p in troubled and recent:
            rating = random.choice([1.0, 1.0, 2.0, 2.0, 3.0, 5.0])
        else:
            rating = random.choice([5.0, 5.0, 5.0, 4.0, 4.0, 3.0, 2.0, 1.0])
        f.write(json.dumps({
            "rating": rating,
            "title": "Stopped working" if rating <= 2 else "Works great",
            "text": "Leaks after two weeks" if rating <= 2 else "Does the job",
            "images": [],
            "asin": p, "parent_asin": p,
            "user_id": f"U{random.randint(0, 9000)}",
            "timestamp": ts,
            "helpful_vote": random.choice([0, 0, 0, 1, 2, 5, 12]),
            "verified_purchase": random.random() < 0.85,
        }) + "\n")

with open(f"{out}/meta_Appliances.jsonl", "w") as f:
    for p in products:
        f.write(json.dumps({
            "main_category": "Appliances",
            "title": f"Ice maker {p[-3:]}",
            "average_rating": 4.1, "rating_number": 120,
            "features": ["x"], "description": ["y"],
            "price": random.choice([None, "None", 39.99, 129.0]),
            "images": [], "videos": [],
            "store": random.choice(["Frigidaire", "GE", "Whirlpool"]),
            "categories": ["Appliances", "Ice Makers"],
            "details": json.dumps({"Brand": "X"}),
            "parent_asin": p, "bought_together": None,
        }) + "\n")

# --- the workshop SQL ----------------------------------------------------
REVIEWS_SRC = f"{out}/Appliances.jsonl"
META_SRC = f"{out}/meta_Appliances.jsonl"
con = duckdb.connect()

def run(label, sql):
    print(f"\n== {label}")
    r = con.sql(sql)
    if r is not None:
        r.show(max_rows=8, max_width=160)

run("module 1: reviews to parquet", f"""
COPY (
  SELECT
    parent_asin,
    rating::TINYINT                         AS rating,
    title,
    text,
    to_timestamp(timestamp / 1000)          AS reviewed_at,
    helpful_vote,
    verified_purchase,
    user_id
  FROM read_json('{REVIEWS_SRC}',
    format = 'newline_delimited',
    columns = {{
      rating: 'DOUBLE', title: 'VARCHAR', text: 'VARCHAR',
      asin: 'VARCHAR', parent_asin: 'VARCHAR', user_id: 'VARCHAR',
      timestamp: 'BIGINT', helpful_vote: 'INTEGER', verified_purchase: 'BOOLEAN'
    }})
) TO '{out}/reviews.parquet' (FORMAT parquet, COMPRESSION zstd)
""")

run("module 1: products to parquet", f"""
COPY (
  SELECT
    parent_asin,
    title                                   AS product,
    store,
    TRY_CAST(price AS DOUBLE)               AS price_usd,
    rating_number
  FROM read_json('{META_SRC}',
    format = 'newline_delimited',
    columns = {{
      parent_asin: 'VARCHAR', title: 'VARCHAR', store: 'VARCHAR',
      price: 'VARCHAR', rating_number: 'INTEGER'
    }})
) TO '{out}/products.parquet' (FORMAT parquet, COMPRESSION zstd)
""")

con.sql(f"CREATE VIEW reviews AS FROM '{out}/reviews.parquet'")
con.sql(f"CREATE VIEW products AS FROM '{out}/products.parquet'")

run("module 1: sanity check", """
SELECT count(*) AS reviews,
       min(reviewed_at) AS first_review,
       max(reviewed_at) AS last_review,
       round(avg(verified_purchase::INT) * 100, 1) AS pct_verified
FROM reviews
""")

run("module 2a: rating mix", """
SELECT rating, count(*) AS n,
       round(100 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM reviews GROUP BY rating ORDER BY rating
""")

run("module 2b: monthly trend for one product", """
SELECT date_trunc('month', reviewed_at) AS month,
       count(*) AS reviews,
       round(avg(rating), 2) AS avg_rating
FROM reviews
WHERE parent_asin = 'B000000001' AND verified_purchase
GROUP BY month ORDER BY month DESC LIMIT 6
""")

run("module 2c: products in trouble", """
WITH bounds AS (
  SELECT max(reviewed_at) AS as_of FROM reviews
),
scored AS (
  SELECT
    r.parent_asin,
    r.reviewed_at >= b.as_of - INTERVAL 6 MONTH        AS is_recent,
    r.rating
  FROM reviews r, bounds b
  WHERE r.verified_purchase
)
SELECT
  s.parent_asin,
  p.product,
  p.store,
  count(*) FILTER (WHERE is_recent)                       AS recent_reviews,
  round(avg(rating) FILTER (WHERE NOT is_recent), 2)      AS before_avg,
  round(avg(rating) FILTER (WHERE is_recent), 2)          AS recent_avg,
  round(avg(rating) FILTER (WHERE is_recent)
      - avg(rating) FILTER (WHERE NOT is_recent), 2)      AS change
FROM scored s
JOIN products p USING (parent_asin)
GROUP BY ALL
HAVING count(*) FILTER (WHERE is_recent) >= 20
   AND count(*) FILTER (WHERE NOT is_recent) >= 50
ORDER BY change
LIMIT 10
""")

run("module 2d: the complaints to read", """
SELECT parent_asin, rating, helpful_vote, title, left(text, 80) AS text
FROM reviews
WHERE parent_asin = 'B000000001'
  AND verified_purchase
  AND rating <= 2
  AND reviewed_at >= (SELECT max(reviewed_at) FROM reviews) - INTERVAL 6 MONTH
QUALIFY row_number() OVER (ORDER BY helpful_vote DESC, reviewed_at DESC) <= 40
""")
print("\nALL QUERIES RAN")
