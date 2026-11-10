# AI-Powered Review Analysis with DuckDB and Hugging Face

Code for the hands-on workshop *Build an Automated Customer Feedback Pipeline* (DuckDB User Group, Amsterdam, 11 November 2026).

You build a pipeline that finds the appliances whose ratings fell most in 2.1 million Amazon reviews, pulls their most helpful recent 1–2 star reviews, has an LLM group them into complaint themes, and saves a report. Then you ship it as a Hugging Face Space with an API.

- **DuckDB picks the product and the 40 reviews; the LLM only ever sees those 40.**
- **Develop on a sample, run for real next to the data.** You build on a 24 MB sample on your laptop. The same `ingest.py` then runs as a Hugging Face Job on the full data, and the same `app.py` runs in a Space. Only a path changes.

**Start here: [docs/attendee-guide.md](docs/attendee-guide.md)**. It has the setup to do before the workshop and every step on the day.

## Quick start

```bash
git clone https://github.com/prpatel/duckdb-hf-reviews-workshop.git
cd duckdb-hf-reviews-workshop
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
hf auth login
hf download prpatel/voc-appliances-sample --repo-type dataset --local-dir raw-sample

duckdb < sql/primer.sql                      # Module 0: DuckDB primer (needs the DuckDB 2.0 CLI)
python scripts/ingest.py --src raw-sample    # Module 1: JSON lines -> Parquet
duckdb < sql/analysis.sql                    # Module 2: find the declining products
```

## What's here

| Path | What it is | Module |
| --- | --- | --- |
| `sql/primer.sql` | A first half hour with DuckDB, on the raw sample | 0 |
| `scripts/ingest.py` | Raw JSON lines → `clean/reviews.parquet` + `clean/products.parquet`. Runs locally and as a Hugging Face Job | 1, 3 |
| `sql/analysis.sql` | Rating mix, one product over time, the decline ranking, the complaints worth reading | 2 |
| `app.py` | Five functions bound to a `gr.Workflow` canvas: Products in trouble → Worst product → Complaints → Complaint themes (LLM) → Save report | 4, 5 |
| `solutions/workflow.json` | A finished canvas, wired, with two API endpoints | 4, 5 |
| `scripts/make_sample.py` | How the 24 MB sample was built from the full data | |
| `tests/` | Synthetic-data tests for the SQL and the sample flow | |
| `requirements.txt` | Python packages; DuckDB is pinned to 2.0.0 | |

## Data

The **Appliances** category of [Amazon Reviews 2023](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023) by the McAuley Lab at UC San Diego (Hou et al., 2024, [arXiv:2403.03952](https://arxiv.org/abs/2403.03952)):

- [`prpatel/voc-appliances-sample`](https://huggingface.co/datasets/prpatel/voc-appliances-sample): the 24 MB sample, 50,430 reviews of 195 products, in the original raw layout.
- [`prpatel/voc-appliances-clean`](https://huggingface.co/datasets/prpatel/voc-appliances-clean): the full category as two Parquet tables, the fallback if your Job doesn't run.
