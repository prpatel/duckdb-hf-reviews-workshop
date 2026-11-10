"""End-to-end test of the sample-first flow on synthetic data.

Builds a fake raw/ folder in the real dataset layout, then runs the real scripts:
  1. scripts/ingest.py on the "full" data
  2. scripts/make_sample.py to pick whole products, decliners first
  3. scripts/ingest.py on the sample
and checks that the sample's decline ranking leads with the planted decliners and
that every sample line is byte-identical to a line in the full file.

Usage: python tests/test_sample_flow.py [work_dir]
"""
import json
import os
import random
import subprocess
import sys
import tempfile

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
work = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="voc-flow-")
os.makedirs(f"{work}/full-raw/review_categories", exist_ok=True)
os.makedirs(f"{work}/full-raw/meta_categories", exist_ok=True)

random.seed(7)
products = [f"B0{n:08d}" for n in range(200)]
troubled = set(products[:5])
start_ms, end_ms = 1_420_070_400_000, 1_694_000_000_000
six_months = 183 * 86_400_000

with open(f"{work}/full-raw/review_categories/Appliances.jsonl", "w") as f:
    # Planted decliners get 4x the reviews, so they clear the >= 20 recent-review threshold.
    weights = [4 if p in troubled else 1 for p in products]
    for _ in range(80_000):
        p = random.choices(products, weights)[0]
        ts = random.randint(start_ms, end_ms)
        if p in troubled and ts > end_ms - six_months:
            rating = random.choice([1.0, 1.0, 2.0, 2.0, 3.0, 5.0])
        else:
            rating = random.choice([5.0, 5.0, 5.0, 4.0, 4.0, 3.0, 2.0, 1.0])
        f.write(json.dumps({
            "rating": rating, "title": "t", "text": "x" * random.randint(50, 400),
            "images": [], "asin": p, "parent_asin": p, "user_id": f"U{random.randint(0, 9999)}",
            "timestamp": ts, "helpful_vote": random.choice([0, 0, 1, 3, 9]),
            "verified_purchase": random.random() < 0.85,
        }) + "\n")

with open(f"{work}/full-raw/meta_categories/meta_Appliances.jsonl", "w") as f:
    for p in products:
        f.write(json.dumps({
            "main_category": "Appliances", "title": f"Product {p[-3:]}", "average_rating": 4.0,
            "rating_number": 100, "features": [], "description": [],
            "price": random.choice([None, "None", 49.99]), "images": [], "videos": [],
            "store": "Brand", "categories": [], "details": "{}", "parent_asin": p,
            "bought_together": None,
        }) + "\n")

def run(*args):
    subprocess.run([sys.executable, *args], cwd=work, check=True)

run(f"{ROOT}/scripts/ingest.py", "--src", "full-raw", "--out", "full-clean")
run(f"{ROOT}/scripts/make_sample.py", "--clean", "full-clean", "--raw", "full-raw",
    "--out", "raw-sample", "--target-reviews", "10000", "--decliners", "5")
run(f"{ROOT}/scripts/ingest.py", "--src", "raw-sample", "--out", "clean")

con = duckdb.connect()
con.sql("SET TimeZone = 'UTC'")
con.sql(f"CREATE VIEW reviews AS FROM '{work}/clean/reviews.parquet'")
top = [r[0] for r in con.sql("""
WITH bounds AS (SELECT max(reviewed_at) AS as_of FROM reviews),
scored AS (SELECT r.parent_asin, r.reviewed_at >= b.as_of - INTERVAL 6 MONTH AS is_recent, r.rating
           FROM reviews r, bounds b WHERE r.verified_purchase)
SELECT parent_asin FROM scored GROUP BY ALL
HAVING count(*) FILTER (WHERE is_recent) >= 20 AND count(*) FILTER (WHERE NOT is_recent) >= 50
ORDER BY avg(rating) FILTER (WHERE is_recent) - avg(rating) FILTER (WHERE NOT is_recent)
LIMIT 5
""").fetchall()]
assert set(top) == troubled, f"sample's top decliners {top} != planted {sorted(troubled)}"

full_lines = set(open(f"{work}/full-raw/review_categories/Appliances.jsonl"))
sample_lines = open(f"{work}/raw-sample/review_categories/Appliances.jsonl").readlines()
assert sample_lines and all(l in full_lines for l in sample_lines), "sample lines differ from full"

print(f"SAMPLE FLOW OK ({len(sample_lines)} sample reviews, work dir {work})")
