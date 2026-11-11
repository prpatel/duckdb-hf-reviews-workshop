# app.py: Voice of the Customer pipeline as a gr.Workflow
import os
from datetime import date

import duckdb
import gradio as gr
from huggingface_hub import InferenceClient

DATA = os.environ.get("VOC_DATA", "/data")          # bucket mount path in the Space
LLM = os.environ.get("VOC_MODEL", "Qwen/Qwen3-Next-80B-A3B-Instruct")

DECLINE_SQL = """
WITH bounds AS (SELECT max(reviewed_at) AS as_of FROM reviews),
scored AS (
  SELECT r.parent_asin,
         r.reviewed_at >= b.as_of - INTERVAL 6 MONTH AS is_recent,
         r.rating
  FROM reviews r, bounds b
  WHERE r.verified_purchase
)
SELECT s.parent_asin, p.product, p.store,
       count(*) FILTER (WHERE is_recent)                  AS recent_reviews,
       round(avg(rating) FILTER (WHERE NOT is_recent), 2) AS before_avg,
       round(avg(rating) FILTER (WHERE is_recent), 2)     AS recent_avg,
       round(avg(rating) FILTER (WHERE is_recent)
           - avg(rating) FILTER (WHERE NOT is_recent), 2) AS change
FROM scored s JOIN products p USING (parent_asin)
GROUP BY ALL
HAVING count(*) FILTER (WHERE is_recent) >= $min_recent
   AND count(*) FILTER (WHERE NOT is_recent) >= 50
ORDER BY change, recent_reviews DESC
LIMIT $top_n
"""

COMPLAINTS_SQL = """
SELECT rating, helpful_vote, title, text
FROM reviews
WHERE parent_asin = $asin AND verified_purchase AND rating <= 2
  AND reviewed_at >= (SELECT max(reviewed_at) FROM reviews) - INTERVAL 6 MONTH
QUALIFY row_number() OVER (ORDER BY helpful_vote DESC, reviewed_at DESC) <= $limit
"""


def _con():
    con = duckdb.connect()
    con.sql("SET TimeZone = 'UTC'")
    con.sql(f"CREATE VIEW reviews AS FROM '{DATA}/clean/reviews.parquet'")
    con.sql(f"CREATE VIEW products AS FROM '{DATA}/clean/products.parquet'")
    return con


def products_in_trouble(min_recent_reviews: int = 20, top_n: int = 5) -> str:
    """Products whose average rating fell most in the last six months, as a table."""
    rows = _con().execute(DECLINE_SQL, {"min_recent": min_recent_reviews, "top_n": top_n}).fetchall()
    lines = ["| ASIN | Product | Store | Recent n | Before | Recent | Change |",
             "| --- | --- | --- | ---: | ---: | ---: | ---: |"]
    for asin, product, store, n, before, recent, change in rows:
        name = product if len(product or "") <= 40 else product[:39] + "…"   # titles run to 200 chars
        lines.append(f"| {asin} | {name} | {store} | {n} | {before} | {recent} | {change} |")
    return "\n".join(lines)


def worst_product(min_recent_reviews: int = 20) -> str:
    """The ASIN with the steepest decline."""
    row = _con().execute(DECLINE_SQL, {"min_recent": min_recent_reviews, "top_n": 1}).fetchone()
    return row[0] if row else ""


def complaints(asin: str, limit: int = 40) -> str:
    """The most-helpful recent 1-2 star verified reviews for one product."""
    rows = _con().execute(COMPLAINTS_SQL, {"asin": asin, "limit": limit}).fetchall()
    return "\n\n".join(f"[{r[0]} stars, {r[1]} helpful] {r[2]}: {r[3]}" for r in rows)


def complaint_themes(complaints: str) -> str:
    """Group complaints into themes with an LLM on Inference Providers."""
    if not complaints.strip():
        raise gr.Error("No complaints to summarise. Is there a product ID in Complaints?")
    prompt = (
        "You are a product quality analyst. Below are recent 1-2 star reviews of one appliance.\n"
        "Start with a 'Safety' section. List a hazard (fire, smoke, electric shock, water damage, "
        "injury, debris in food or ice) only if a review describes it actually happening; "
        "otherwise write 'No safety issues reported.'\n"
        "Then group the reviews into 3-5 complaint themes. For each theme give: a short name, "
        "how many reviews mention it, and one short quote copied exactly from a review.\n"
        "Answer in plain Markdown, not inside a code block, in under 300 words.\n\n" + complaints
    )
    reply = InferenceClient(model=LLM).chat.completions.create(
        messages=[{"role": "user", "content": prompt}], max_tokens=1000
    )
    text = (reply.choices[0].message.content or "").strip()
    text = text.removeprefix("```markdown").removeprefix("```").removesuffix("```").strip()
    if not text:
        raise gr.Error(f"{LLM} returned no text. Use an instruct model, not a reasoning model.")
    return text


def save_report(asin: str, themes: str) -> str:
    """Write the report to the bucket's reports/ folder and return its path."""
    os.makedirs(f"{DATA}/reports", exist_ok=True)
    path = f"{DATA}/reports/{date.today():%Y-%m-%d}-{asin}.md"
    with open(path, "w") as f:
        f.write(f"# Complaint themes for {asin}\n\n{themes}\n")
    return path


gr.Workflow(bind={
    "Products in trouble": products_in_trouble,
    "Worst product": worst_product,
    "Complaints": complaints,
    "Complaint themes": complaint_themes,
    "Save report": save_report,
}).launch()
