# Attendee Guide: AI-Powered Review Analysis with DuckDB and Hugging Face

**Wednesday 11 November 2026, 12:00–17:00 CET**, at AWS Amsterdam (Mr. Treublaan 7). Hosted by the DuckDB User Group.

You'll build a pipeline that finds which products' ratings are falling in 2.1 million Amazon reviews and explains why, then ship it as a live Hugging Face Space with an API.

---

## Before you arrive

Please do these at home; the venue Wi-Fi is shared by the whole room. Setup takes about 15 minutes.

1. **Create a Hugging Face account** at [huggingface.co/join](https://huggingface.co/join), if you don't have one.
2. **Create an access token with write access** under [Settings → Access Tokens](https://huggingface.co/settings/tokens).
3. **Make sure your account has a positive credit balance** under [Settings → Billing](https://huggingface.co/settings/billing). Cloud Jobs need it. It pays for one small Job (the hardware costs $0.01 an hour and the Job takes about a minute) and a few LLM calls (under $0.001 each).
4. **Install Python 3.10 or later.**
5. **Install the DuckDB 2.0 command-line tool** for your system, following [duckdb.org/docs/2.0/installation](https://duckdb.org/docs/2.0/installation?platform=macos&environment=cli) (pick your platform on that page). Check it:

   ```bash
   duckdb --version        # v2.0.0
   ```

6. **Get the workshop code:**

   ```bash
   git clone https://github.com/prpatel/duckdb-hf-reviews-workshop.git
   cd duckdb-hf-reviews-workshop
   ```

   No git? Download the ZIP from the [repository page](https://github.com/prpatel/duckdb-hf-reviews-workshop) (Code → Download ZIP) and unzip it.

7. **Install the Python packages** (a virtual environment is a good idea):

   ```bash
   python -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

8. **Log in from the terminal**, in your browser when it asks, or by pasting your write token:

   ```bash
   hf auth login
   hf auth whoami          # should print your username
   ```

9. **Download the 24 MB practice dataset** into the workshop folder:

   ```bash
   hf download prpatel/voc-appliances-sample --repo-type dataset --local-dir raw-sample
   ```

10. **Run the check:**

    ```bash
    python -c "import duckdb, gradio, huggingface_hub, pytz; duckdb.sql('INSTALL httpfs'); print('ok', duckdb.__version__, hasattr(gradio, 'Workflow'))"
    ```

    It should print `ok 2.0.0 True`. `True` means your Gradio is new enough for `gr.Workflow`. If anything fails, see [Troubleshooting](#troubleshooting) or come 15 minutes early.

---

## On the day

**Bring:** your laptop and charger, with everything above already done. No ML experience needed; you should be comfortable with SQL and able to read basic Python.

| Module | Where it runs | What you do | Roughly |
| --- | --- | --- | --- |
| Kickoff | Laptop | Check your setup | 15 min |
| 0. DuckDB primer | Laptop | Get comfortable in the DuckDB shell | 30 min |
| 1. Build locally | Laptop | Turn the practice data into fast Parquet tables | 25 min |
| 2. Find the trouble | Laptop | Write the SQL that finds declining products | 35 min |
| 3. Run it for real | Hugging Face | Run the same code on all 2.1M reviews as a cloud Job | 10 min |
| Break | | | 10 min |
| 4. Workflow | Laptop | Connect the SQL to an LLM in a visual pipeline | 50 min |
| 5. Ship it | Hugging Face | Deploy it as a Space and call it as an API | 30 min |

---

## What you'll build

A pipeline that finds the appliances whose ratings fell most in the last six months of the data, pulls their most helpful recent 1–2 star reviews, has an LLM group those reviews into complaint themes, and saves a report. **DuckDB picks the product and the 40 reviews; the LLM only ever sees those 40.**

```
YOUR LAPTOP (Modules 0, 1, 2, 4)
  raw-sample/ (24 MB) ─► ingest.py ─► clean/*.parquet ─► sql/analysis.sql ─► app.py (canvas)
                         │ same script                                        │ same app
HUGGING FACE (Modules 3, 5)
  full dataset (2.1M) ─► Job: ingest.py ─► your bucket ─────────────────────► Space: app.py ─► LLM
```

You build and test everything on your laptop against the sample. Then the same two files run on Hugging Face against all 2.1 million reviews, so the 1.2 GB of raw data never crosses the venue Wi-Fi.

The data is the **Appliances** category of [Amazon Reviews 2023](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023) from the McAuley Lab at UC San Diego. Reviews run to 12 September 2023, so "the last six months" means **12 March to 12 September 2023**, not the six months before today.

---

## Step by step

Run every command from the workshop folder. Wherever you see `<you>`, type your Hugging Face username.

### Module 0: DuckDB primer

Open the DuckDB shell and follow along, pasting one statement at a time from `sql/primer.sql`:

```bash
duckdb
```

Or run it all at once: `duckdb < sql/primer.sql`.

It works straight on the raw JSON lines you downloaded. You'll see dot commands (`.timer on`, `.mode line`, `.tables`), query a file without loading it, profile every column with `SUMMARIZE`, and use `FILTER`, `GROUP BY ALL`, `QUALIFY`, `::` casts and variables. At the end you write the data to Parquet twice, sorted and shuffled, and `EXPLAIN ANALYZE` shows why sorting matters: `Row Groups Scanned: 1 / 9` versus `9 / 9`.

Three exercises are marked in the file if you finish early.

### Module 1: Build locally

Turn the sample's raw JSON lines into two Parquet tables:

```bash
python scripts/ingest.py --src raw-sample
```

This writes `clean/reviews.parquet` and `clean/products.parquet`, then prints the number of reviews and products, the first and last review dates, and the share of verified purchases. You should see **50,430 reviews, 195 products and 96.7% verified**. It takes seconds, so rerun it as often as you like. Try changing a column in `scripts/ingest.py` and running it again; that quick loop is why we start with a sample.

### Module 2: Find the trouble

Run all the analysis queries:

```bash
duckdb < sql/analysis.sql
```

Or open `duckdb` and type `.read sql/analysis.sql` to stay in the shell and keep exploring. The file has four queries:

- **2a** shows the rating mix: lots of 5s, a bump at 1. That's why a plain average hides change.
- **2b** tracks one product's average rating month by month.
- **2c** ranks products by how much their rating fell in the last six months of the data, compared with before.
- **2d** pulls the most helpful recent 1–2 star reviews for one product.

2b and 2d need a product ID, so they start commented out. Pick a `parent_asin` from 2c's results, set it as a variable, uncomment the query, and change `$asin` to `getvariable('asin')`:

```sql
SET VARIABLE asin = 'B09MVV717N';
-- ... WHERE parent_asin = getvariable('asin') ...
```

On the sample, 2c should lead with `B01FF4ASTS`, a dryer duct connector, at **−1.97**.

The knobs to play with are the two thresholds in 2c: a product needs at least 20 recent and 50 earlier verified reviews to be ranked. Change them and see how the list moves. If you finish early, break the ranking down by `store`, or compare against the same months a year earlier to rule out seasonal dips.

### Module 3: Run it for real

Create a private storage bucket, then run the same ingest script as a cloud Job on all 2.1 million reviews. The Job reads the data inside Hugging Face's network and writes the Parquet into your bucket.

```bash
hf buckets create voc-workshop --private --exist-ok
hf jobs uv run -v hf://buckets/<you>/voc-workshop:/bucket scripts/ingest.py --out /bucket/clean
```

Mount the bucket at `/bucket` exactly as shown: `/data` is reserved inside Jobs. Don't add `--region` to the bucket command. The Job prints its log as it runs and finishes in about a minute; the first line says `duckdb 2.0.0: reading hf://datasets/...`. To check on Jobs from another terminal:

```bash
hf jobs ps                  # your jobs and their status
hf jobs logs <job id>       # its output so far
```

When it's finished, check that both files are in your bucket:

```bash
hf buckets list <you>/voc-workshop/clean -h
```

You should see `products.parquet` (about 4 MB) and `reviews.parquet` (about 200 MB).

**If the Job failed or wouldn't start**, don't wait for a rerun. Copy the instructor's finished tables into your bucket instead; the copy happens on Hugging Face's side, not over the Wi-Fi:

```bash
hf cp hf://datasets/prpatel/voc-appliances-clean/ hf://buckets/<you>/voc-workshop/clean/
```

That also copies the dataset's `README.md`, so your `clean/` folder will show three files. That's fine.

### Module 4: Build the workflow

Start the app on your laptop, pointed at the sample tables you built in Module 1:

```bash
export VOC_DATA=.
export VOC_MODEL=Qwen/Qwen3-Next-80B-A3B-Instruct
python app.py
```

On Windows PowerShell, use `$env:VOC_DATA="."` and `$env:VOC_MODEL="Qwen/Qwen3-Next-80B-A3B-Instruct"` instead of the two `export` lines.

Gradio prints two addresses. **Open the write-access link** (the one ending in `?write_token=…`; it usually opens by itself). The plain address opens the canvas read-only, and you won't be able to connect anything.

The canvas has five nodes, one per Python function in `app.py`:

1. **Products in trouble** shows the decline ranking as a table, for you to look at.
2. **Worst product** returns the ID of the product with the steepest fall.
3. **Complaints** returns that product's most helpful recent 1–2 star reviews.
4. **Complaint themes** sends those reviews to an LLM, which lists any real safety issue first and then groups the complaints into themes with counts and quotes.
5. **Save report** writes the themes to a Markdown file in `reports/`.

Connect **Worst product → Complaints → Complaint themes → Save report**, and also connect **Worst product** to the product-ID input on **Save report**. Type values into the number inputs (20 for the review threshold, 5 for top N, 40 for the complaint limit). Run the nodes one at a time and read each output before moving on. Drag a node's bottom-right corner to make it bigger; the ranking table needs the room.

**To make it an API** (you'll need this in Module 5), each pipeline needs an **output** node at its end, and **number input** nodes for the values a caller should be able to pass. For example, two number inputs feeding **Products in trouble**, and an output node labelled "Products in trouble" after it.

Your wiring saves automatically to `workflow.json` next to `app.py`. Stuck, or short of time? A finished one is in `solutions/`:

```bash
cp solutions/workflow.json workflow.json      # then restart python app.py
```

### Module 5: Ship it

1. **Put the three files in their own folder.** Only these get uploaded, not your virtual environment or the data:

   ```bash
   mkdir space
   cp app.py workflow.json requirements.txt space/
   ```

   No `workflow.json` of your own? Use `cp solutions/workflow.json space/workflow.json` instead. On Windows PowerShell: `mkdir space; copy app.py, workflow.json, requirements.txt space\`.

2. **Create the Space** with your bucket mounted at `/data` (read-write), your token as the secret `HF_TOKEN`, and the model as the variable `VOC_MODEL`, all in one command:

   ```bash
   export HF_TOKEN=$(hf auth token)
   hf repos create <you>/voc-workshop --type space --sdk gradio --private \
     -v hf://buckets/<you>/voc-workshop:/data \
     --env VOC_MODEL=Qwen/Qwen3-Next-80B-A3B-Instruct --secrets HF_TOKEN
   ```

   On Windows PowerShell, use `$env:HF_TOKEN = hf auth token` for the first line, and put the second command on one line without the `\`. The app reads `/data` by default, so it sees the full tables from Module 3.

3. **Upload the app:**

   ```bash
   hf upload <you>/voc-workshop space . --type space
   hf spaces wait <you>/voc-workshop        # about a minute while it builds
   ```

4. **Run it on the full data** at `https://huggingface.co/spaces/<you>/voc-workshop`. The first query takes about 15 seconds while the bucket warms up; after that it's fast. Then check the report landed in your bucket:

   ```bash
   hf buckets list <you>/voc-workshop/reports
   hf buckets cp hf://buckets/<you>/voc-workshop/reports/<file>.md -
   ```

5. **Compare with your laptop.** Does **Products in trouble** on 2.1 million reviews lead with the same products you found on the sample in Module 2? We'll discuss why it should, and when a sample can mislead you.
6. **Call it as an API.** Every pipeline that ends in an output node is an endpoint:

   ```python
   from gradio_client import Client

   client = Client("<you>/voc-workshop", token="<your token>")
   client.view_api()                                           # lists the endpoints
   client.predict(20, 5, api_name="/products_in_trouble")      # with solutions/workflow.json
   ```

   The endpoint's name comes from the output node's label. With `solutions/workflow.json` there are two: `/products_in_trouble` and `/complaint_report`, which runs the whole chain and returns the themes and the report's path.

---

## Troubleshooting

| What you see | What to do |
| --- | --- |
| The setup check prints `False` | Your Gradio is too old for `gr.Workflow`. Run `pip install -r requirements.txt` again, or `pip install -U gradio`. |
| The setup check prints a DuckDB version other than `2.0.0` | Run `pip install -r requirements.txt` inside your virtual environment. |
| `ModuleNotFoundError: No module named 'pytz'` | Run `pip install pytz`. DuckDB needs it to hand dates with time zones to Python. |
| `hf: command not found` | Run `pip install -U huggingface_hub`, then open a new terminal (and reactivate your virtual environment). |
| `duckdb: command not found` | Install the DuckDB command-line tool (see [Before you arrive](#before-you-arrive)). |
| `401`, `Unauthorized` or "not logged in" | Run `hf auth whoami`. If it doesn't show your username, run `hf auth login` again with a token that has write access. |
| `No files found that match the pattern "clean/..."` | Run commands from the workshop folder, and run Module 1 before Module 2. |
| Query 2c returns no rows | Lower the two thresholds in 2c until products appear. |
| `Mount path '/data' is reserved for Jobs artifacts` | Mount the bucket at `/bucket` and use `--out /bucket/clean`, as in Module 3. |
| The cloud Job won't start, or mentions billing | Add credit under Settings → Billing and run it again, or use the `hf cp` copy at the end of Module 3. |
| The `hf cp` copy fails | You may have created the bucket in a different region. Delete it, create it again without `--region`, and copy again. |
| You can't connect nodes on the canvas | You opened the read-only address. Use the write-access link Gradio printed. |
| `client.view_api()` lists no useful endpoints | Your pipelines need output nodes (Module 4), or copy `solutions/workflow.json`. |
| The Space can't find its data | Run `hf spaces volumes list <you>/voc-workshop`: the bucket must be mounted at exactly `/data`. And `hf buckets list <you>/voc-workshop/clean` must show the two Parquet files. |
| **Save report** fails in the Space | The bucket is mounted read-only. Mount it again read-write: `hf spaces volumes set <you>/voc-workshop -v hf://buckets/<you>/voc-workshop:/data`, then restart the Space. |
| `hf repos create` says the Space already exists | Settings on the command aren't applied to an existing Space. Set them separately: `hf spaces volumes set <you>/voc-workshop -v hf://buckets/<you>/voc-workshop:/data`, `hf spaces variables add <you>/voc-workshop -e VOC_MODEL=Qwen/Qwen3-Next-80B-A3B-Instruct`, and `hf spaces secrets add <you>/voc-workshop -s HF_TOKEN` (after `export HF_TOKEN=$(hf auth token)`). Then upload as in step 3. |
| **Complaint themes** fails | In the Space, check `HF_TOKEN` is set as a secret: `hf spaces secrets list <you>/voc-workshop`. "returned no text" means `VOC_MODEL` names a reasoning model; use `Qwen/Qwen3-Next-80B-A3B-Instruct`. "No complaints to summarise" means Complaints got no product ID. |

Stuck on something else? Put your hand up; helpers will be walking around.

---

## After the workshop

Your bucket and Space stay in your Hugging Face account, so you can keep using them. Both are private; to share your Space, run `hf repos settings <you>/voc-workshop --type space --public` (anyone can then run it on your credits). Delete them from your account settings when you're done. The first `hf jobs uv run` also created a bucket called `<you>/jobs-artifacts` to hold the uploaded script; you can delete that too.

Ways to take it further:

- **Another product category.** The dataset has 33; rerun the ingest with `--category All_Beauty`, for example.
- **Your own reviews.** Load them into the same columns (`parent_asin`, `rating`, `text`, `reviewed_at`, `helpful_vote`, `verified_purchase`) and the SQL and workflow run unchanged.
- **Run it every week.** Have a scheduled Job (`hf jobs scheduled uv run …`) call your Space's API and send the report wherever your product team reads it.

## Links

- [Amazon Reviews 2023 dataset](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023) · [the workshop sample](https://huggingface.co/datasets/prpatel/voc-appliances-sample) · [the full tables](https://huggingface.co/datasets/prpatel/voc-appliances-clean)
- [DuckDB 2.0 documentation](https://duckdb.org/docs/2.0/) · [DuckDB and Hugging Face](https://duckdb.org/docs/2.0/core_extensions/httpfs/hugging_face)
- [Hugging Face Jobs](https://huggingface.co/docs/huggingface_hub/guides/jobs) · [Storage Buckets](https://huggingface.co/docs/hub/storage-buckets)
- [Gradio workflows](https://www.gradio.app/guides/workflows)
- [Meetup event page](https://www.meetup.com/duckdb/events/317045246/)
