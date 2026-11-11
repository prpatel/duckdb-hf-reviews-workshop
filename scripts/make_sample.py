"""Build the 24 MB local-development sample (prpatel/voc-appliances-sample) from the full data.

A random sample of reviews would break the workshop: most products would have only
a handful of reviews, so the decline ranking (which needs >= 20 recent and >= 50
earlier verified reviews per product) would return nothing. Instead this picks
WHOLE products:

  1. the N steepest decliners from a full run, so the local results are interesting
  2. random other products with a moderate number of reviews, until the target count

It copies their raw JSONL lines byte for byte, in the dataset's raw/ layout, so
scripts/ingest.py runs on the sample exactly as it does on the full data.

Usage (needs a full clean/ from scripts/ingest.py and local copies of the raw files):
    hf download McAuley-Lab/Amazon-Reviews-2023 raw/review_categories/Appliances.jsonl \\
        raw/meta_categories/meta_Appliances.jsonl --repo-type dataset --local-dir full-raw
    python scripts/make_sample.py --clean clean --raw full-raw/raw --out raw-sample
    hf upload prpatel/voc-appliances-sample raw-sample . --repo-type dataset
"""
import argparse
import json
import os

import duckdb

p = argparse.ArgumentParser()
p.add_argument("--clean", default="clean", help="folder with the FULL reviews/products Parquet")
p.add_argument("--raw", required=True, help="local raw/ folder with the full JSONL files")
p.add_argument("--out", default="raw-sample")
p.add_argument("--category", default="Appliances")
p.add_argument("--target-reviews", type=int, default=50_000)
p.add_argument("--decliners", type=int, default=10)
p.add_argument("--max-reviews-per-product", type=int, default=2_000,
               help="skip giant products so one item can't eat the budget")
p.add_argument("--seed", type=float, default=0.42)
args = p.parse_args()

con = duckdb.connect()
con.sql("SET TimeZone = 'UTC'")
con.sql(f"CREATE VIEW reviews AS FROM '{args.clean}/reviews.parquet'")

# Same decline ranking as the workshop (sql/analysis.sql, 2c), without the product join.
decliners = con.execute("""
WITH bounds AS (SELECT max(reviewed_at) AS as_of FROM reviews),
scored AS (
  SELECT r.parent_asin, r.reviewed_at >= b.as_of - INTERVAL 6 MONTH AS is_recent, r.rating
  FROM reviews r, bounds b WHERE r.verified_purchase
)
SELECT parent_asin
FROM scored
GROUP BY parent_asin
HAVING count(*) FILTER (WHERE is_recent) >= 20
   AND count(*) FILTER (WHERE NOT is_recent) >= 50
ORDER BY avg(rating) FILTER (WHERE is_recent) - avg(rating) FILTER (WHERE NOT is_recent),
         count(*) FILTER (WHERE is_recent) DESC
LIMIT $n
""", {"n": args.decliners}).fetchall()
chosen = [r[0] for r in decliners]

counts = dict(con.execute("SELECT parent_asin, count(*) FROM reviews GROUP BY ALL").fetchall())
total = sum(counts[a] for a in chosen)

con.execute("SELECT setseed($s)", {"s": args.seed})
others = con.execute("""
SELECT parent_asin, count(*) AS n
FROM reviews
GROUP BY parent_asin
HAVING count(*) BETWEEN 70 AND $cap
ORDER BY random()
""", {"cap": args.max_reviews_per_product}).fetchall()
for asin, n in others:
    if total >= args.target_reviews:
        break
    if asin not in chosen:
        chosen.append(asin)
        total += n
keep = set(chosen)

def copy_lines(src, dst):
    kept = 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(src, encoding="utf-8") as fin, open(dst, "w", encoding="utf-8") as fout:
        for line in fin:
            if json.loads(line).get("parent_asin") in keep:
                fout.write(line)
                kept += 1
    return kept

r = copy_lines(f"{args.raw}/review_categories/{args.category}.jsonl",
               f"{args.out}/review_categories/{args.category}.jsonl")
m = copy_lines(f"{args.raw}/meta_categories/meta_{args.category}.jsonl",
               f"{args.out}/meta_categories/meta_{args.category}.jsonl")

size_mb = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(args.out) for f in fs) / 1e6
print(f"{len(keep)} products ({len(decliners)} decliners), {r} reviews, {m} metadata rows, {size_mb:.1f} MB")
print("decliners:", ", ".join(a for (a,) in decliners))
