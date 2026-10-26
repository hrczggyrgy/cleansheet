# Streamlit and Polars 2.0: A Practical, Research-Based User Guide

Research date: 26 October 2026  
Audience: Python users and data analysts building interactive analytics applications  
Target: Python Polars 2.0.0 and Streamlit 1.66.0  
Suggested development runtime: Python 3.12

## How to use this guide

Start with Sections 1–5 for the mental model and a first app. Sections 6–12 develop practical Polars skills. Sections 13–18 cover Streamlit integration, caching, uploads, tables, and application structure. Section 19 provides a complete multi-file sales dashboard. Sections 20–25 cover tests, performance, security, deployment, migration, and troubleshooting.

The central design principle is **separation**: Polars owns data transformations; Streamlit owns interactions and presentation; explicit contracts connect the two.

This is an original synthesis of the official documentation, release announcement, API references, and migration guide. Inline source markers identify the supporting material. It is not an official vendor manual. Suggestions about architecture, limits, and project structure are engineering recommendations rather than vendor guarantees.

### Version and validation scope

- Polars 2.0 was released on 6 October 2026. This guide deliberately targets that major release and its migration changes, rather than silently adopting later feature releases. [web:2]
- Streamlit's release notes identify 1.66.0, released 14 October 2026, as the latest release at the research date. Streamlit 1.66 drops Python 3.10 support; Python 3.12 is the chosen baseline for this guide. [web:38]
- Official documentation pages can evolve independently of a pinned package. Resolve and lock dependencies in a clean environment, then run the included tests against that exact environment.
- Python code blocks were syntax-checked during document creation. The dashboard was not launched in a browser, and a compatible Polars 2.0/Streamlit environment was not provisioned for end-to-end execution. Treat the supplied tests as required verification, not as already-passed certification.

## Contents

1. What each library does
2. Installation and reproducibility
3. A first Streamlit–Polars app
4. Streamlit's execution model
5. Polars' execution model
6. DataFrame fundamentals and schemas
7. Expressions, filtering, and derived columns
8. Missing values, validation, and numerical correctness
9. Aggregations, windows, and ranking
10. Joins and reshaping
11. Dates, time zones, and time series
12. Lazy queries, streaming, SQL, and storage
13. Caching and data freshness
14. Interactive tables, selections, and editing
15. Safe uploads and downloads
16. Forms, Session State, and fragments
17. Multipage apps and project design
18. Databases and external data
19. Complete sales dashboard project
20. Testing strategy
21. Performance and observability
22. Security and multiuser correctness
23. Deployment
24. Polars 1.x to 2.0 migration checklist
25. Troubleshooting and quick reference
26. Suggested learning path

---

## 1. What each library does

Streamlit is a Python framework for interactive data applications. Polars is a dataframe/query engine. They solve different parts of the same problem: Streamlit gathers user choices and renders results, while Polars reads, transforms, joins, and aggregates structured data. Streamlit accepts Polars DataFrames and LazyFrames in `st.dataframe`. [web:3][web:7][web:33]

A useful architecture is:

```text
Files / database / object storage
              |
              v
Schema validation and access control
              |
              v
Polars query plan: select -> filter -> transform -> aggregate
              |
              v
Small result tables / chart series / bounded detail views
              |
              v
Streamlit: widgets, metrics, tables, charts, downloads
```

### Where this combination fits

Use this design for analyst-facing dashboards, operational exploration, internal reporting, and controlled data-quality tools. Prefer keeping transformations in plain Python functions so they can also run in notebooks, batch jobs, and unit tests.

Do not assume that a fast dataframe engine makes every web interaction cheap. Total latency includes storage access, query execution, cache overhead, serialization, network transfer, and browser rendering. Lazy scans and bounded UI results address different portions of that path. [web:32][web:5][web:33]

## 2. Installation and reproducibility

### 2.1 Create an isolated environment

Run these commands in a terminal from a new project directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "streamlit==1.66.0" "polars==2.0.0" pyarrow pytest
```

On Windows PowerShell, replace the activation command with:

```powershell
.venv\Scripts\Activate.ps1
```

The explicit application-level pins target this guide's baseline. `pyarrow` supports the explicit Arrow presentation boundary used in the project. Optional database drivers are separate dependencies and should be installed only when needed. Polars supports Arrow interoperability; its database reader supports optional ConnectorX and ADBC engines. [web:4][web:59]

### 2.2 Record the environment

```bash
python -c "import sys, streamlit, polars; print(sys.version); print(streamlit.__version__); print(polars.__version__)"
python -m pip freeze > requirements.lock.txt
python -m streamlit hello
```

Commit a reviewed lock file. A lock file produced by `pip freeze` records the current environment; it is not automatically portable across operating systems, CPU architectures, or Python versions. Rebuild and test for your deployment platform.

A minimal `requirements.txt` for the complete project is:

```text
streamlit==1.66.0
polars==2.0.0
pyarrow
pytest
```

For deployment, use the tested, fully resolved lock file instead of leaving transitive versions unbounded. Keep test dependencies separate if your packaging workflow supports development groups.

### 2.3 Run applications correctly

```bash
python -m streamlit run app.py
```

Use the Streamlit runner rather than treating the app as an ordinary one-shot script. Docker deployment likewise invokes `streamlit run` and listens on port 8501 in the official example. [web:53]

## 3. A first Streamlit–Polars app

Save the following as `app.py`:

```python
import polars as pl
import streamlit as st

st.set_page_config(page_title="First Polars dashboard", layout="wide")
st.title("Sales by city")

sales = pl.DataFrame({
    "city": ["Debrecen", "Budapest", "Debrecen", "Szeged"],
    "quantity": [2, 1, 3, 2],
    "unit_price_huf": [1500, 4000, 1200, 2000],
})

cities = st.multiselect(
    "Cities",
    options=sorted(sales["city"].unique().to_list()),
    default=sorted(sales["city"].unique().to_list()),
)

result = (
    sales.lazy()
    .filter(pl.col("city").is_in(cities))
    .with_columns(
        (pl.col("quantity") * pl.col("unit_price_huf")).alias("revenue_huf")
    )
    .group_by("city")
    .agg(pl.col("revenue_huf").sum())
    .sort(["revenue_huf", "city"], descending=[True, False])
    .collect()
)

st.metric("Revenue (HUF)", f"{result['revenue_huf'].sum():,}")
st.dataframe(result.to_arrow(), hide_index=True, width="stretch")
st.bar_chart(result.to_arrow(), x="city", y="revenue_huf")
```

Here, selecting no cities intentionally produces no matching rows. The explicit sort makes the output presentation deterministic. Polars 2.0's streaming default does not preserve incidental order through grouping and joins. [web:4]

The calculation is performed in Polars expressions, and conversion happens only at the presentation boundary. Streamlit also accepts the Polars DataFrame directly; explicit Arrow conversion is an interoperability choice, not a requirement for every app. [web:46][web:33]

## 4. Streamlit's execution model

### 4.1 Think in reruns

A typical widget interaction triggers a script rerun from top to bottom. Plain variables are recreated; values in Session State survive across reruns of the same session. Forms batch inputs, and fragments can rerun a smaller portion of the app. Some current widgets also support `on_change="ignore"`, which defers the backend update until a later rerun. [web:31][web:38]

This common pattern does not retain a counter:

```python
import streamlit as st

count = 0
if st.button("Add"):
    count += 1
st.write(count)
```

The script initializes `count` on every run. Use Session State instead:

```python
import streamlit as st

if "count" not in st.session_state:
    st.session_state["count"] = 0

if st.button("Add"):
    st.session_state["count"] += 1
st.write(st.session_state["count"])
```

This follows Streamlit's documented state model. Each browser tab establishes a separate session; Session State is not a durable database. [web:31]

### 4.2 Three different persistence mechanisms

| Mechanism | Scope and behavior | Appropriate use |
|---|---|---|
| Ordinary local variable | Recreated on script rerun | Temporary computation |
| `st.session_state` | User-session state across reruns | Applied filters, edit drafts, selected identifiers |
| `st.cache_data` | Shared cached results; returns copies | Trusted, reusable query results |
| `st.cache_resource` | Shared object instance | Thread-safe connections, models, resource pools |

Cached values are available across users; Session State is scoped to the session. Resource-cache objects can be mutated and must be safe for concurrent access. These scopes are correctness and security decisions, not merely speed settings. [web:5][web:31]

### 4.3 Do not put uncontrolled side effects in the rerun path

A write to a database, an email send, or an export job should require an explicit action and server-side validation. Design writes to be idempotent where possible: repeated execution with the same operation identifier should not duplicate the business action.

Keep rendering separate from persistence. A table editor changes a returned object; it does not itself create an audited database transaction. Its supported return types also differ from the display API. [web:34]

## 5. Polars' execution model

### 5.1 Eager DataFrame versus lazy query

A `DataFrame` contains materialized data. A `LazyFrame` describes a query that Polars can optimize before execution. `scan_*` creates a lazy source; calling `.lazy()` on an already-read DataFrame does not undo that earlier read. [web:19][web:32]

```python
import polars as pl

# Data is read before the later lazy plan is constructed.
eager_source = pl.read_parquet("sales.parquet")
late_lazy = eager_source.lazy().filter(pl.col("quantity") > 0)

# The scan participates in lazy optimization.
early_lazy = (
    pl.scan_parquet("sales.parquet")
    .filter(pl.col("quantity") > 0)
    .select("order_id", "quantity")
)
```

Prefer the second pattern for storage-backed analytics. The optimizer can push filters and selected columns toward the source and avoid unnecessary work where the format and query allow it. [web:32]

### 5.2 The major Polars 2.0 change

`LazyFrame.collect()` still defaults to `engine="auto"`, but in 2.0 that resolves to the streaming engine for lazy queries. Eager DataFrame operations continue to use the in-memory engine internally. You can select an engine explicitly per query. [web:4]

```python
# q is a LazyFrame.
# default_result = q.collect()
# explicit_streaming = q.collect(engine="streaming")
# compatibility_result = q.collect(engine="in-memory")
```

Streaming processes the query in batches where supported. It does not mean every operation has constant memory, every query spills to disk, or that the final collected result is absent from memory. Use sinks when the output itself is too large to materialize. [web:6][web:32][web:2]

### 5.3 Ordering must be intentional

Choose an ordering policy for each result:

- A chart series: sort by the plotted time column.
- A leaderboard: sort by measure, then a deterministic tie-break key.
- A left join whose input order is semantically required: use `maintain_order="left"` where supported.
- An unordered aggregate used only for reconciliation: compare rows without requiring incidental order.

The migration guide explicitly warns about changed order after `group_by`, joins, and `unpivot`. `maintain_order` is not a universal Boolean parameter: the documented join example uses a string. [web:4]

## 6. DataFrame fundamentals and schemas

### 6.1 Construct typed data

```python
from datetime import date
import polars as pl

sales = pl.DataFrame(
    {
        "order_id": [1001, 1002, 1003],
        "order_date": [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)],
        "city": ["Debrecen", "Budapest", "Szeged"],
        "quantity": [2, 1, 4],
        "unit_price_huf": [1500, 4000, 900],
    },
    schema_overrides={
        "order_id": pl.Int64,
        "quantity": pl.Int64,
        "unit_price_huf": pl.Int64,
    },
)
```

Use explicit types for identifiers, money, timestamps, and join keys. Check schema compatibility early with `collect_schema()` on a lazy query. Schema checks cannot prove all row-level constraints; malformed values or business-rule violations can still require execution to discover. [web:2][web:4]

```python
schema = sales.lazy().collect_schema()
required = {"order_id", "order_date", "city", "quantity", "unit_price_huf"}
missing = required - set(schema.names())
if missing:
    raise ValueError(f"Missing required columns: {sorted(missing)}")
```

### 6.2 Useful inspection methods

```python
shape = sales.shape
schema = sales.schema
preview = sales.head(5)
nulls = sales.null_count()
summary = sales.describe()
```

Use a small preview for inspection, but do not treat a preview as proof that the full dataset is valid. Polars' validity metadata makes null counting efficient, while numerical `NaN` checks are a different operation. [web:54]

### 6.3 From pandas habits to Polars habits

| Familiar intention | Polars pattern |
|---|---|
| Select columns | `df.select("a", "b")` |
| Add or replace a column | `df.with_columns(expression.alias("name"))` |
| Filter rows | `df.filter(predicate)` |
| Group and summarize | `df.group_by("key").agg(...)` |
| Parse date strings | `pl.col("s").str.to_date(...)` |
| Execute a lazy query | `lf.collect()` |
| Write a large lazy result | `lf.sink_parquet(...)` |

Expressions execute in contexts such as `select`, `with_columns`, `filter`, and `group_by`. Do not translate an index-alignment-oriented pandas workflow line by line without reconsidering the data model. [web:46][web:4][web:32]

## 7. Expressions, filtering, and derived columns

### 7.1 Build expressions, not Python row loops

```python
import polars as pl

sales = pl.DataFrame({
    "city": [" Debrecen ", "Budapest", "Szeged"],
    "quantity": [2, 1, 4],
    "unit_price_huf": [1500, 4000, 900],
})

clean = sales.with_columns(
    pl.col("city").str.strip_chars().alias("city"),
    (pl.col("quantity") * pl.col("unit_price_huf")).alias("revenue_huf"),
)

filtered = clean.filter(
    (pl.col("quantity") > 0) & (pl.col("revenue_huf") >= 3000)
)
```

Use `&`, `|`, and `~` with parenthesized comparisons rather than Python's scalar `and`, `or`, and `not`. Expressions describe column computations that Polars can optimize and evaluate in parallel. [web:46]

### 7.2 Chain dependent transformations

Expressions within one context are independent; do not assume a newly created alias is available to a sibling expression. Put dependent calculations in consecutive steps. [web:46]

```python
with_margin = (
    clean.with_columns((pl.col("revenue_huf") * 0.7).alias("cost_estimate_huf"))
    .with_columns(
        (pl.col("revenue_huf") - pl.col("cost_estimate_huf"))
        .alias("margin_estimate_huf")
    )
)
```

The floating-point cost estimate above is illustrative, not an accounting policy. Production money calculations need an explicit precision, rounding, and overflow policy.

### 7.3 Conditional expressions and literals

```python
classified = clean.with_columns(
    pl.when(pl.col("revenue_huf") >= 4000)
    .then(pl.lit("high"))
    .otherwise(pl.lit("standard"))
    .alias("value_band")
)
```

Use `pl.lit` when you mean a literal string rather than a column expression. Keep branch computations valid for the input types; do not treat a vectorized conditional as an excuse to hide invalid parsing or casting rules. Polars 2.0 emphasizes strict, explicit behavior. [web:46][web:2]

### 7.4 Selectors in Polars 2.0

Selectors choose sets of columns; expressions compute values. Mixing the two with set-like operators changed in 2.0. For a selector intersection by column name, use another selector rather than `pl.col`. [web:4]

```python
import polars.selectors as cs

numeric_measure = clean.select(cs.integer() & cs.by_name("quantity"))
```

## 8. Missing values, validation, and numerical correctness

### 8.1 `null` and `NaN` are not interchangeable

Polars uses `null` for missing values across dtypes. `NaN` is a floating-point value, not a missing-value marker. `fill_null` does not replace `NaN`, and `null_count` does not count it. Aggregations normally skip nulls, while NaN can propagate into numerical results. [web:54]

```python
import polars as pl

measurements = pl.DataFrame({"reading": [1.0, None, float("nan"), 3.0]})
normalized = measurements.with_columns(
    pl.col("reading").fill_nan(None).alias("reading")
)
null_report = normalized.null_count()
```

Replacing NaN with null is a domain decision. Keep invalid measurements distinguishable if analysts need to investigate their cause.

### 8.2 Validate before summarizing

A practical validation sequence is:

1. Verify required columns and expected types.
2. Verify required values are not null.
3. Detect duplicate business keys.
4. Validate allowed categories and numerical ranges.
5. Check referential integrity before joins.
6. Reconcile row counts and totals after transformations.

Schema resolution provides early feedback, but value-dependent errors still require data evaluation. [web:2]

```python
bad_quantities = clean.filter(
    pl.col("quantity").is_null() | (pl.col("quantity") <= 0)
)
duplicates = (
    pl.DataFrame({"line_id": [1, 1, 2]})
    .group_by("line_id")
    .agg(pl.len().alias("n"))
    .filter(pl.col("n") > 1)
)
```

Do not silently discard bad rows unless that behavior is explicitly part of the data contract. Quarantine them or show a bounded diagnostic with an accountable exclusion count.

### 8.3 Money, ratios, and counting semantics

For the sample dashboard, all prices are whole Hungarian forints and revenue is integer multiplication. This avoids introducing floating-point rounding into line-level revenue, but integers still need an overflow policy. Decimal types are an alternative when fractional currency units or decimal rules matter; Polars 2.0 changes several Decimal result precisions and SQL arithmetic rules. [web:4]

Distinguish:

- `pl.len()`: number of rows in the current context.
- `pl.col("x").count()`: number of non-null values in `x`.
- `pl.col("order_id").n_unique()`: distinct order identifiers, not line count.

These are expression-context operations; use explicit names such as `line_count` and `order_count` to prevent analytical ambiguity. [web:46][web:54]

For ratios, state both the numerator and denominator. In a filtered line-item view, “average order value” calculated from visible revenue divided by visible distinct orders is the average contribution of the selected lines per represented order, not necessarily the full basket value of those orders.

## 9. Aggregations, windows, and ranking

### 9.1 Grouped summaries

```python
summary = (
    clean.group_by("city")
    .agg(
        pl.len().alias("line_count"),
        pl.col("quantity").sum().alias("units"),
        pl.col("revenue_huf").sum().alias("revenue_huf"),
        pl.col("revenue_huf").mean().alias("mean_line_revenue_huf"),
    )
    .sort(["revenue_huf", "city"], descending=[True, False])
)
```

`group_by().agg()` changes the result's grain to one row per group. A non-aggregated expression in an aggregation context can produce list-valued cells, so choose aggregators deliberately. [web:46]

### 9.2 Window expressions retain row-level detail

```python
with_shares = clean.with_columns(
    pl.col("revenue_huf").sum().over("city").alias("city_revenue_huf")
).with_columns(
    (pl.col("revenue_huf") / pl.col("city_revenue_huf"))
    .alias("share_of_city_revenue")
)
```

This retains line-level rows while adding a city-level denominator. Explain the grain of both the input and result when reviewing a transformation; it is a powerful defense against accidentally duplicated totals.

### 9.3 Stable top-N results

```python
top_cities = summary.sort(
    ["revenue_huf", "city"], descending=[True, False]
).head(10)
```

A deterministic tie-break key matters for stable tables, screenshots, tests, and selections. In Polars 2.0, relying on incidental group order is specifically unsafe. [web:4]

## 10. Joins and reshaping

### 10.1 Choose the join for the question

| Join | Typical analytical question |
|---|---|
| Inner | Which records have a match on both sides? |
| Left | Keep all facts and enrich from a dimension |
| Full | Reconcile records from either system |
| Semi | Keep facts with an eligible related record |
| Anti | Find unmatched or invalid foreign keys |
| Asof | Find the nearest qualifying event by time or key |
| Cross | Produce all combinations; use with strict size controls |

These strategies differ in both row inclusion and column output. A cross join returns a Cartesian product, and asof joins need an appropriate ordering and matching policy. [web:55]

```python
import polars as pl

facts = pl.DataFrame({"customer_id": [1, 2, 3], "revenue_huf": [1000, 2000, 3000]})
customers = pl.DataFrame({"customer_id": [1, 2], "segment": ["Retail", "Business"]})

unmatched = facts.join(customers, on="customer_id", how="anti")
enriched = facts.join(
    customers, on="customer_id", how="left", maintain_order="left"
)
```

Before a fact-to-dimension join, verify that the dimension key is unique. If it is not, a line can match multiple dimension rows and inflate revenue. A left join preserves unmatched left records, not necessarily the original number of rows when right-side keys repeat. [web:55]

### 10.2 Long-form data is often easier to chart

```python
wide = pl.DataFrame({
    "city": ["Debrecen", "Budapest"],
    "online_huf": [1000, 2000],
    "store_huf": [1500, 1800],
})
long = wide.unpivot(
    on=["online_huf", "store_huf"],
    index="city",
    variable_name="channel",
    value_name="revenue_huf",
).sort(["city", "channel"])
```

Sort the reshaped output if its order matters. Polars 2.0 specifically identifies `unpivot` as an operation whose incidental order can differ under streaming. [web:4]

### 10.3 Exploding lists changes counts in 2.0

```python
nested = pl.DataFrame({"tags": [["priority", "online"], [], None]})
new_default = nested.explode("tags")
legacy_empty_row = nested.explode("tags", empty_as_null=True)
```

The new default expands an empty list into zero rows rather than a single null row. A null list still produces a null row under the unchanged null-list policy. Reconcile counts after exploding list columns. [web:4]

## 11. Dates, time zones, and time series

### 11.1 Parse strings explicitly

Direct string-to-temporal casts were removed in Polars 2.0. Use string parsing methods such as `str.to_date`, `str.to_datetime`, and `str.to_time`. [web:4]

```python
raw = pl.DataFrame({"date_text": ["2026-10-01", "2026-10-02"]})
parsed = raw.with_columns(
    pl.col("date_text").str.to_date(format="%Y-%m-%d", strict=True)
    .alias("order_date")
)
```

Choose a source contract for ambiguous formats. A value such as `03/04/2026` cannot be interpreted safely without knowing whether the source uses day-first or month-first dates.

For timestamp filters, prefer a half-open interval: include the start instant and exclude the next interval's start. A calendar-date picker does not itself establish the timezone or precise timestamp boundary of a dataset.

### 11.2 Localization is different from conversion

Assigning a timezone to a naive local clock reading is not the same as converting an existing instant to another timezone. Polars documents that `replace_time_zone` changes the underlying timestamp and ignores the old zone; parsing naive strings with `time_zone` localizes them. [web:47][web:49]

```python
local_times = pl.DataFrame({"local_time": ["2026-10-20 12:00:00"]})
localized = local_times.with_columns(
    pl.col("local_time").str.to_datetime(
        format="%Y-%m-%d %H:%M:%S",
        time_zone="Europe/Budapest",
    ).alias("event_time")
)
```

Use a documented policy for ambiguous and nonexistent local times around daylight-saving transitions. Keep a canonical event-time representation and a separate display-time policy when reporting across regions.

### 11.3 Dynamic time windows require sorted time keys

```python
from datetime import date

series = pl.DataFrame({
    "order_date": [date(2026, 10, 1), date(2026, 10, 8), date(2026, 10, 9)],
    "revenue_huf": [1000, 2000, 1500],
})
weekly = (
    series.sort("order_date")
    .group_by_dynamic("order_date", every="1w")
    .agg(pl.col("revenue_huf").sum())
    .sort("order_date")
)
```

The index must be ascending, or ascending within each group when additional grouping keys are supplied. `every` defines the window cadence and `period` its duration; overlapping windows can assign a row to multiple groups. Choose labels and closed boundaries intentionally. [web:37][web:42]

An absent date is not automatically equivalent to zero revenue. Decide whether the chart needs a complete calendar spine and distinguish “no records,” “not loaded,” and “known zero.”

## 12. Lazy queries, streaming, SQL, and storage

### 12.1 Scan first and collect only the answer

```python
from datetime import date

q = (
    pl.scan_parquet("data/sales/*.parquet")
    .filter(pl.col("order_date") >= date(2026, 10, 1))
    .select("city", "quantity", "unit_price_huf")
    .with_columns(
        (pl.col("quantity") * pl.col("unit_price_huf")).alias("revenue_huf")
    )
    .group_by("city")
    .agg(pl.col("revenue_huf").sum())
    .sort(["revenue_huf", "city"], descending=[True, False])
)

plan_text = q.explain()
result = q.collect()
```

A scan allows the optimizer to move eligible filters and projections into the reader. The actual savings depend on the file format, storage layout, available metadata, and the query. Do not promise that any arbitrary CSV predicate can skip the same physical I/O as a well-partitioned Parquet dataset. [web:32]

### 12.2 Stream to a sink when output is large

```python
q = (
    pl.scan_parquet("data/sales/*.parquet")
    .filter(pl.col("quantity") > 0)
)
# Run in a controlled batch/export context, not on every UI rerun.
# q.sink_parquet("exports/validated_sales.parquet")
```

Sinks execute a query and stream its results to storage without necessarily retaining the full output in RAM. In a web app, submit large exports as controlled jobs with app-owned destinations, quotas, and authorization. [web:32]

### 12.3 Understand out-of-core limits

The 2.0 announcement says spill-to-disk is enabled by default, starts at roughly 80% of RAM, and has a 64 GB default disk budget. It names sort, window functions, and many expressions as supported initial workloads, and states that out-of-core joins and group-bys are planned for later. [web:2]

Therefore:

- Streaming does not guarantee that a high-cardinality join or aggregation will complete under any memory limit.
- Provide scratch-disk capacity and monitor disk pressure.
- Avoid treating the announcement's thresholds as an application memory reservation or a hard safety limit for a container.
- Benchmark the exact workload, concurrency, resource limits, and package version.

### 12.4 Inspect plans without relying on removed APIs

`LazyFrame.profile()` was removed in 2.0 because its old per-node timings were inappropriate for the concurrent streaming engine. Use query-plan inspection plus end-to-end timing and process/container telemetry. [web:4]

```python
# For a LazyFrame q:
# plan = q.explain()
# q.show_graph(engine="streaming", plan_stage="physical")
# q.show_graph(plan_stage="ir")
```

The migration page contains inconsistent general wording about whether a bare `show_graph()` renders a streaming plan; its specific breaking-change section says the default `plan_stage` changes to `"physical"`. Supplying both the engine and stage explicitly avoids depending on that ambiguity. [web:4]

### 12.5 SQL is another interface to the engine

```python
sales = pl.DataFrame({"city": ["Debrecen", "Debrecen", "Budapest"],
                      "revenue_huf": [1000, 2000, 4000]})
context = pl.SQLContext(sales=sales.lazy())
sql_query = context.execute("""
    SELECT city, SUM(revenue_huf) AS revenue_huf
    FROM sales
    GROUP BY city
    ORDER BY revenue_huf DESC, city ASC
""")
sql_schema = sql_query.collect_schema()
sql_result = sql_query.collect()
```

Polars 2.0 elevates SQL support and defers parsing/resolution for lazy SQL plans until optimization, collection, or schema resolution. Calling `execute` does not necessarily validate the query immediately. SQL's Decimal literals, arithmetic scales, division, remainder, and rounding have significant migration changes. Do not assume Python-expression and SQL arithmetic semantics are identical. [web:2][web:4]

Do not offer unrestricted user SQL over sensitive registered tables. Prefer allowlisted report templates and controlled parameters; a lazy query engine is not an authorization boundary.

### 12.6 New Map dtype

```python
attributes = pl.DataFrame({
    "customer_id": [1, 2],
    "scores": pl.Series(
        [{"loyalty": 90, "service": 80}, {}],
        dtype=pl.Map(pl.String, pl.Int64),
    ),
})
loyalty = attributes.select(
    "customer_id",
    pl.col("scores").map.get("loyalty").alias("loyalty_score"),
)
```

Arrow/Parquet map columns now load as Polars `Map`, not the older list-of-key/value-struct representation. Ordinary Python dictionaries still infer as Struct unless a Map dtype or an appropriate source specifies otherwise. For UI use, project selected keys into scalar columns rather than assuming arbitrary nested values are editable. [web:2][web:4][web:34]

## 13. Caching and data freshness

### 13.1 Cache materialized results, not merely query plans

`st.cache_data` is designed for serializable data results and returns copies. Streamlit's cache documentation lists lazy computations separately and specifically notes that caching collected results may be preferable. A cached LazyFrame plan is not a cached result of its execution. [web:5]

```python
from pathlib import Path
import polars as pl
import streamlit as st

@st.cache_data(ttl=300, max_entries=32)
def regional_summary(path: str, version: str, city: str) -> pl.DataFrame:
    return (
        pl.scan_parquet(path)
        .filter(pl.col("city") == city)
        .select("city", "revenue_huf")
        .group_by("city")
        .agg(pl.col("revenue_huf").sum())
        .sort("city")
        .collect()
    )

# Supply an actual content/snapshot version for mutable sources.
# stat = Path("data/sales.parquet").stat()
# version = f"{stat.st_mtime_ns}:{stat.st_size}"
# result = regional_summary("data/sales.parquet", version, "Debrecen")
```

Here, `version` deliberately participates in the cache key even though the query body does not use its value. The version represents the data snapshot. Timestamp-plus-size is a local-development heuristic, not a cryptographic guarantee of content identity. Immutable object versions or manifest identifiers are stronger production choices.

### 13.2 Design a complete cache key

Include every result-affecting dimension:

- Data source and immutable snapshot/version.
- Applied filters and aggregation grain.
- Currency, time zone, or other business-semantic choices.
- Tenant, authorization scope, and policy version when results are access-controlled.
- A transformation version when changes to imported helper functions must invalidate cached results.

Streamlit hashes function inputs and the decorated function's code. It cannot infer that an unchanged path refers to newly replaced data, nor should you assume that edits to every external dependency trigger invalidation. [web:5]

### 13.3 Excluding a parameter can create incorrect cache hits

A leading underscore excludes that parameter from hashing. Only do this if other key fields completely represent its effect. Excluding a DataFrame, connection, user, or tenant without an equivalent semantic key can return the wrong cached result. [web:5]

### 13.4 Manage cache size and trust

`ttl` controls freshness and `max_entries` bounds entry count, not byte usage. Cached results use pickle serialization; preserve cache integrity and never deserialize user-supplied pickle files. Shared resource objects require explicit thread-safety review. [web:5]

Avoid global caching of private uploads by default. Session State is a clearer starting point for private, per-session materialized data; it also avoids long-lived cross-session cache entries. For production, define the retention policy rather than relying on an accidental lifetime. [web:31][web:5]

## 14. Interactive tables, selections, and editing

### 14.1 Displaying Polars data

```python
import polars as pl
import streamlit as st

df = pl.DataFrame({"city": ["Debrecen", "Budapest"], "revenue_huf": [3000, 4000]})
st.dataframe(df, hide_index=True, width="stretch")
st.dataframe(df.to_arrow(), hide_index=True, width="stretch")
```

Both Polars DataFrames and LazyFrames are accepted by the display API. Explicit Arrow conversion is useful as a controlled interoperability boundary, but conversion does not make unlimited output cheap. [web:33]

### 14.2 Current lazy table support

Streamlit 1.66's `st.dataframe` documentation describes a `lazy` parameter. `lazy=True` loads rows from the server as needed; for Polars LazyFrame sources, Streamlit can read through the unevaluated source. With `lazy=None`, the documented automatic thresholds are above 150,000 rows for supported in-memory data and above 10,000 rows for supported unevaluated sources. Small datasets of at most 1,000 rows may still be loaded eagerly. [web:33]

```python
# These are alternative presentation modes for an existing LazyFrame q.
# Browse a large query without enabling selection:
# st.dataframe(q, lazy=True, width="stretch")

# Enable selection on a deliberately bounded materialized preview:
# preview = q.limit(1000).collect()
# event = st.dataframe(preview, lazy=False, on_select="rerun")
```

Lazy-loaded tables do not support search, built-in CSV download, selections, or pandas Styler styling in the documented version. Server-side sorting is supported. Use explicit `lazy=False` for selection-enabled bounded tables. This UI feature is different from Polars' streaming execution engine. [web:33]

### 14.3 Map selections back to stable records

```python
preview = df.sort("city")
event = st.dataframe(
    preview.to_arrow(),
    lazy=False,
    on_select="rerun",
    selection_mode="multi-row",
    hide_index=True,
)
positions = event.selection.rows
if positions:
    selected_cities = preview[positions, "city"].to_list()
    st.write(selected_cities)
```

Row positions refer to the original input table even after browser-side sorting. Resolve positions against the exact preview supplied to that widget, then retain business identifiers rather than positions across changed datasets. [web:33]

### 14.4 Do not assume editing returns Polars

The documented editor return types include pandas and Arrow tables but not Polars. Unsupported input types are returned as pandas DataFrames. Use an explicit supported boundary and then convert back. [web:34]

```python
editable_source = pl.DataFrame({"item_id": [1, 2], "target": [10, 20]})
edited_arrow = st.data_editor(
    editable_source.to_arrow(),
    disabled=["item_id"],
    num_rows="fixed",
    hide_index=True,
    key="targets_editor",
)
edited_polars = pl.from_arrow(edited_arrow)
```

Validate edited types, nullability, ranges, and identifiers on the server. Persist only after an explicit save action with transaction and concurrency controls. Complex nested/dictionary-like values are not generally editable. [web:34]

### 14.5 Hiding columns does not protect them

Columns omitted with `column_order` or hidden with column configuration may remain available from the table toolbar. Remove sensitive columns from the actual data before passing it to Streamlit. [web:33][web:34]

## 15. Safe uploads and downloads

### 15.1 A small, session-local CSV workflow

```python
import hashlib
import io
import polars as pl
import streamlit as st

upload = st.file_uploader("Upload a CSV", type=["csv"])
if upload is not None:
    if upload.size > 10 * 1024 * 1024:
        st.error("This example accepts files up to 10 MiB.")
        st.stop()
    raw = upload.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    if st.session_state.get("upload_digest") != digest:
        try:
            parsed = pl.read_csv(io.BytesIO(raw), infer_schema_length=1000)
        except pl.exceptions.PolarsError:
            st.error("The file could not be parsed as CSV.")
            st.stop()
        st.session_state["uploaded_data"] = parsed
        st.session_state["upload_digest"] = digest
    st.dataframe(st.session_state["uploaded_data"].head(1000).to_arrow())
```

The byte limit is an example policy, not a safe maximum for every host. A small compressed or compact file can expand into much more memory. Add row, column, schema, parser-time, and resource limits appropriate to the deployment.

Streamlit's uploader returns a file-like `UploadedFile`; `getvalue()` reads the complete contents without consuming the current position. Extension filtering is best-effort, not a security guarantee. Its documented default is 200 MB per file, configurable globally or per widget. [web:35]

### 15.2 Polars 2.0 buffer-position trap

```python
import io
import polars as pl

buffer = io.BytesIO()
pl.DataFrame({"x": [1, 2, 3]}).write_parquet(buffer)
buffer.seek(0)
roundtrip = pl.read_parquet(buffer)
```

Polars 2.0 no longer implicitly rewinds file-like inputs. Always reset the position before reuse, or create a fresh `BytesIO` from immutable bytes. [web:4]

### 15.3 European CSV conventions

For sources that explicitly use a semicolon separator and decimal commas:

```python
# Configure these options only when they match the source contract.
# df = pl.read_csv("regional_export.csv", separator=";", decimal_comma=True)
```

Do not guess decimal or thousands separators from the user's locale. Document encoding, null markers, date format, decimal conventions, and expected column types in the import contract. Polars 2.0 changes CSV reader behavior and removes several legacy read parameters; check the migration section before copying older recipes. [web:4]

### 15.4 Bound downloads

```python
# summary is a small, authorized, flat DataFrame.
# st.download_button(
#     "Download summary",
#     data=summary.write_csv().encode("utf-8"),
#     file_name="sales_summary.csv",
#     mime="text/csv",
# )
```

Create downloads from the same authorized snapshot and filters as the visible report. For large exports, prefer an asynchronous export job to a bounded browser download. Treat text opened in spreadsheet software as untrusted: implement a tested formula-injection policy for text fields rather than assuming CSV quoting alone is a security boundary.

## 16. Forms, Session State, and fragments

### 16.1 Forms batch expensive filter changes

```python
import streamlit as st

with st.form("filters"):
    city = st.selectbox("City", ["Debrecen", "Budapest"])
    minimum = st.number_input("Minimum revenue", min_value=0, value=0)
    apply = st.form_submit_button("Apply")

if apply:
    st.session_state["applied_filters"] = {"city": city, "minimum": minimum}

st.write(st.session_state.get("applied_filters", {}))
```

Form values are sent to Python when the form is submitted. Every form needs a submit button; forms cannot be nested, and ordinary buttons/download buttons do not belong inside them. Within a form, only the submit button can have a callback. [web:30]

Use a separate `applied_filters` value to distinguish draft settings from the report that is currently shown. This makes export behavior and filter captions much easier to explain.

### 16.2 Use callbacks for state transitions

A callback executes before the ensuing script rerun. Read freshly submitted keyed widget values from Session State rather than assuming callback arguments captured during an earlier render are current. [web:30][web:31]

### 16.3 Fragments limit rerun scope

```python
import polars as pl
import streamlit as st

small = pl.DataFrame({"x": [1, 2, 3], "value": [5, 7, 6]})

@st.fragment
def local_preview():
    n = st.slider("Preview rows", min_value=1, max_value=3, value=2)
    st.dataframe(small.head(n).to_arrow())

local_preview()
```

Widgets inside a fragment normally rerun only that fragment. Share outputs through Session State when needed; fragment return values are ignored during fragment-only reruns. Do not combine fragment and cache decorators on the same function. [web:16]

For a live display, `run_every="10s"` can trigger periodic fragment reruns, but it is not a durable background scheduler. Keep long-running ETL and export jobs outside the page-render lifecycle. [web:16]

### 16.4 Parallel fragments are a concurrency choice

The current documentation supports `parallel=True` during full-app reruns. Do not add it merely because Polars is fast: several concurrent heavy queries can compete for memory and CPU. Shared state, connections, and resources need thread-safety controls; some commands and writes to externally created containers are restricted in parallel fragments. [web:16]

## 17. Multipage apps and project design

### 17.1 Keep the entrypoint small

Streamlit recommends `st.Page` and `st.navigation` for multipage applications. The entrypoint runs on each app rerun, returns a selected page from navigation, and must call its `.run()` method. [web:58]

```python
import streamlit as st

st.set_page_config(page_title="Analytics workspace", layout="wide")
page = st.navigation([
    st.Page("views/overview.py", title="Overview"),
    st.Page("views/quality.py", title="Data quality"),
])
page.run()
```

Create the referenced view files before launching this snippet.

### 17.2 Recommended responsibilities

```text
project/
  app.py                 # page routing or top-level presentation
  analytics.py           # pure Polars transformations
  data_access.py         # storage, credentials, source versions
  views/                 # Streamlit pages
  tests/                 # transformation and UI tests
  .streamlit/config.toml # non-secret application configuration
```

Keep reusable query construction free of Streamlit calls. Pass explicit filter values into functions instead of reading hidden global widgets from inside the data layer.

For multipage filters, retain domain state under dedicated Session State keys instead of making the widget's existence the only owner of the selected value. Session State persists across pages, but individual widget lifecycle behavior still needs testing. [web:31][web:58]

## 18. Databases and external data

### 18.1 Two common Polars database entry points

- `pl.read_database`: read through a connection object; behavior depends on the driver.
- `pl.read_database_uri`: read using a URI, with ConnectorX or ADBC engines and the appropriate optional dependencies.

Arrow-native result transfer can be more efficient than constructing data from row-wise Python results. Benchmark your actual driver and workload. These readers return materialized DataFrames; they are not equivalent to a lazy database scan with arbitrary later pushdown. [web:59][web:60]

```python
# Requires the corresponding optional driver and a real configured URI.
# uri = st.secrets["database"]["uri"]
# df = pl.read_database_uri(
#     query="SELECT order_date, city, revenue_huf FROM reporting.daily_sales",
#     uri=uri,
#     engine="adbc",
# )
```

### 18.2 Push source-side work into controlled queries

Select only necessary columns and apply authorized filters in the database where appropriate. Use the driver's parameterized-query facilities for values rather than string interpolation. Allowlist selectable identifiers; bound query duration and result size.

For cached database queries, keep authentication/authorization scope in the key and select a freshness policy consistent with the reporting SLA. Use `st.cache_resource` only for genuinely thread-safe connection resources or pools, not an arbitrary connection that might be shared unsafely between sessions. [web:5]

Store credentials using `st.secrets` or deployment-managed secrets rather than source code. `st.secrets` provides a dictionary-like interface to TOML-managed secrets. [web:63]

## 19. Complete sales dashboard project

This project uses a generated, public demo dataset. It does not require a database, private files, or external network requests after package installation. Its architecture intentionally differs from the private-upload workflow: shared caching is appropriate for this non-sensitive demo source.

### 19.1 What the project demonstrates

- Generate reproducible sales lines into Parquet.
- Validate schema and row-level constraints.
- Build lazy Polars queries from applied filters.
- Cache bounded, materialized query results with a source version.
- Show metrics, city/category summaries, a daily trend, and a bounded detail table.
- Handle empty results and partial date ranges.
- Export only a small summary, not every matching line.
- Keep transformations separately testable.

The reporting grain is one row per sales line. There are two lines per order. A category filter therefore changes selected-line revenue, not necessarily total basket revenue for represented orders.

### 19.2 Project layout

```text
sales_dashboard/
  app.py
  analytics.py
  generate_demo.py
  requirements.txt
  tests/
    test_analytics.py
    test_app.py
  .streamlit/
    config.toml
  data/
    sales.parquet       # created by generate_demo.py
```

Use the requirements from Section 2. Run all commands from the project root.

### 19.3 `generate_demo.py`

```python
from datetime import date, timedelta
from pathlib import Path
from random import Random

import polars as pl


def main() -> None:
    rng = Random(42)
    cities = ["Debrecen", "Budapest", "Szeged", "Pecs"]
    categories = ["Books", "Electronics", "Home", "Sports"]
    rows = []
    start = date(2026, 1, 1)

    for i in range(20_000):
        order_number = i // 2
        rows.append({
            "line_id": i + 1,
            "order_id": order_number + 1,
            "order_date": start + timedelta(days=order_number % 180),
            "city": cities[order_number % len(cities)],
            "category": categories[rng.randrange(len(categories))],
            "quantity": rng.randint(1, 5),
            "unit_price_huf": rng.randint(5, 150) * 100,
        })

    df = pl.DataFrame(rows, schema_overrides={
        "line_id": pl.Int64,
        "order_id": pl.Int64,
        "quantity": pl.Int64,
        "unit_price_huf": pl.Int64,
    })
    target = Path(__file__).resolve().parent / "data" / "sales.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(target)
    print(f"Wrote {df.height:,} sales lines to {target}")


if __name__ == "__main__":
    main()
```

The data is deliberately simple and synthetic. Its distribution is not a realistic retail model and should not be used for representative performance claims.

### 19.4 `analytics.py`

```python
from datetime import date
from pathlib import Path

import polars as pl

REQUIRED_SCHEMA = {
    "line_id": pl.Int64,
    "order_id": pl.Int64,
    "order_date": pl.Date,
    "city": pl.String,
    "category": pl.String,
    "quantity": pl.Int64,
    "unit_price_huf": pl.Int64,
}


def source_version(path: str) -> str:
    stat = Path(path).stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def base_query(path: str) -> pl.LazyFrame:
    q = pl.scan_parquet(path)
    schema = q.collect_schema()
    for name, dtype in REQUIRED_SCHEMA.items():
        if schema.get(name) != dtype:
            raise ValueError(f"Expected {name}: {dtype}; got {schema.get(name)}")
    return q.select(list(REQUIRED_SCHEMA)).with_columns(
        (pl.col("quantity") * pl.col("unit_price_huf")).alias("revenue_huf")
    )


def validate_source(path: str) -> None:
    q = base_query(path)
    audit = q.select(
        pl.len().alias("rows"),
        pl.col("line_id").n_unique().alias("unique_lines"),
        pl.any_horizontal(
            [pl.col(name).is_null() for name in REQUIRED_SCHEMA]
        ).sum().alias("null_rows"),
        ((pl.col("quantity") <= 0) | (pl.col("unit_price_huf") < 0))
        .sum().alias("invalid_rows"),
    ).collect().row(0, named=True)
    if audit["rows"] == 0:
        raise ValueError("The source has no rows.")
    if audit["rows"] != audit["unique_lines"]:
        raise ValueError("line_id must be unique.")
    if audit["null_rows"] or audit["invalid_rows"]:
        raise ValueError("The source violates null or value constraints.")


def filtered_query(
    path: str,
    start: date,
    end: date,
    cities: tuple[str, ...],
    categories: tuple[str, ...],
) -> pl.LazyFrame:
    if start > end:
        raise ValueError("Start date must not exceed end date.")
    return base_query(path).filter(
        pl.col("order_date").is_between(start, end, closed="both"),
        pl.col("city").is_in(list(cities)),
        pl.col("category").is_in(list(categories)),
    )


def summarize(q: pl.LazyFrame, detail_limit: int = 1000) -> dict:
    if not 1 <= detail_limit <= 5000:
        raise ValueError("detail_limit must be between 1 and 5000.")
    totals = q.select(
        pl.len().alias("line_count"),
        pl.col("order_id").n_unique().alias("order_count"),
        pl.col("quantity").sum().alias("units"),
        pl.col("revenue_huf").sum().alias("revenue_huf"),
    ).collect()
    by_city = (
        q.group_by("city")
        .agg(pl.col("revenue_huf").sum())
        .sort(["revenue_huf", "city"], descending=[True, False])
        .collect()
    )
    by_category = (
        q.group_by("category")
        .agg(pl.col("revenue_huf").sum())
        .sort(["revenue_huf", "category"], descending=[True, False])
        .collect()
    )
    daily = (
        q.group_by("order_date")
        .agg(pl.col("revenue_huf").sum())
        .sort("order_date")
        .collect()
    )
    detail = q.sort(["order_date", "line_id"]).limit(detail_limit).collect()
    return {
        "totals": totals,
        "by_city": by_city,
        "by_category": by_category,
        "daily": daily,
        "detail": detail,
    }
```

This teaching implementation collects each result separately for clarity. That can execute the source plan repeatedly on a cache miss. For a larger source, measure alternatives: combine result plans with `pl.collect_all`, reuse a deliberately bounded materialized intermediate, or serve preaggregations. Do not assume that a Python variable holding one LazyFrame memoizes all later execution. Lazy query construction and execution are separate. [web:19][web:32]

Validation scans the source and should be cached by snapshot in the UI. The demo's local timestamp/size version is intentionally limited: production should publish immutable data snapshots atomically. Schema validation here permits extra columns but projects them away, and the numerical validation is only sufficient for the bounded synthetic generator. Add upper bounds and overflow checks before using uncontrolled business data.

### 19.5 `app.py`

```python
from pathlib import Path

import polars as pl
import streamlit as st

from analytics import (
    base_query,
    filtered_query,
    source_version,
    summarize,
    validate_source,
)

st.set_page_config(page_title="Sales Explorer", layout="wide")
st.title("Sales Explorer: Streamlit + Polars 2.0")
st.caption("Synthetic sales lines; revenue is quantity x whole-HUF unit price.")

PATH = str(Path(__file__).resolve().parent / "data" / "sales.parquet")
TRANSFORM_VERSION = "sales-dashboard-v1"


@st.cache_data(ttl=300, max_entries=4)
def load_catalog(path: str, version: str, transform_version: str) -> dict:
    validate_source(path)
    q = base_query(path)
    bounds = q.select(
        pl.col("order_date").min().alias("start"),
        pl.col("order_date").max().alias("end"),
    ).collect().row(0, named=True)
    cities = q.select("city").unique().sort("city").collect()["city"].to_list()
    categories = (
        q.select("category").unique().sort("category")
        .collect()["category"].to_list()
    )
    return {"bounds": bounds, "cities": cities, "categories": categories}


@st.cache_data(ttl=300, max_entries=32)
def load_report(
    path: str,
    version: str,
    transform_version: str,
    start,
    end,
    cities: tuple[str, ...],
    categories: tuple[str, ...],
    detail_limit: int,
) -> dict:
    q = filtered_query(path, start, end, cities, categories)
    return summarize(q, detail_limit)


try:
    version = source_version(PATH)
    catalog = load_catalog(PATH, version, TRANSFORM_VERSION)
except (OSError, ValueError, pl.exceptions.PolarsError):
    st.error("Could not load valid demo data. Run: python generate_demo.py")
    st.stop()

if st.session_state.get("source_version") != version:
    st.session_state["source_version"] = version
    st.session_state["applied"] = {
        "start": catalog["bounds"]["start"],
        "end": catalog["bounds"]["end"],
        "cities": tuple(catalog["cities"]),
        "categories": tuple(catalog["categories"]),
        "detail_limit": 1000,
    }
    for key in ("draft_dates", "draft_cities", "draft_categories", "draft_limit"):
        if key in st.session_state:
            del st.session_state[key]

applied = st.session_state["applied"]
with st.sidebar:
    st.header("Filters")
    with st.form("filters"):
        dates = st.date_input(
            "Date range",
            value=(applied["start"], applied["end"]),
            min_value=catalog["bounds"]["start"],
            max_value=catalog["bounds"]["end"],
            key="draft_dates",
        )
        cities = st.multiselect(
            "Cities", catalog["cities"], default=list(applied["cities"]),
            key="draft_cities",
        )
        categories = st.multiselect(
            "Categories", catalog["categories"],
            default=list(applied["categories"]), key="draft_categories",
        )
        detail_limit = st.selectbox(
            "Detail row limit", [100, 1000, 5000], index=1, key="draft_limit"
        )
        submitted = st.form_submit_button("Apply filters", key="apply_filters")

if submitted:
    if not isinstance(dates, (tuple, list)) or len(dates) != 2:
        st.warning("Select both the start and end date, then apply again.")
    elif dates[0] > dates[1]:
        st.warning("Start date must not exceed end date.")
    else:
        st.session_state["applied"] = {
            "start": dates[0],
            "end": dates[1],
            "cities": tuple(sorted(cities)),
            "categories": tuple(sorted(categories)),
            "detail_limit": int(detail_limit),
        }

applied = st.session_state["applied"]
st.caption(
    f"Applied dates: {applied['start']} to {applied['end']} | "
    f"Cities: {', '.join(applied['cities']) or '(none)'} | "
    f"Categories: {', '.join(applied['categories']) or '(none)'}"
)

try:
    report = load_report(PATH, version, TRANSFORM_VERSION, **applied)
except (OSError, ValueError, pl.exceptions.PolarsError):
    st.error("The report could not be calculated. Verify the source and filters.")
    st.stop()

totals = report["totals"].row(0, named=True)
if totals["line_count"] == 0:
    st.info("No sales lines match the applied filters.")
    st.stop()

metrics = st.columns(4)
metrics[0].metric("Selected-line revenue (HUF)", f"{totals['revenue_huf']:,}")
metrics[1].metric("Represented orders", f"{totals['order_count']:,}")
metrics[2].metric("Units", f"{totals['units']:,}")
metrics[3].metric("Sales lines", f"{totals['line_count']:,}")

trend_tab, summary_tab, detail_tab = st.tabs(["Trend", "Summaries", "Detail"])
with trend_tab:
    st.subheader("Daily selected-line revenue")
    st.line_chart(report["daily"].to_arrow(), x="order_date", y="revenue_huf")
    st.caption("Missing dates are not automatically filled with zero.")

with summary_tab:
    left, right = st.columns(2)
    with left:
        st.subheader("Revenue by city")
        st.bar_chart(report["by_city"].to_arrow(), x="city", y="revenue_huf")
        st.dataframe(report["by_city"].to_arrow(), hide_index=True, width="stretch")
    with right:
        st.subheader("Revenue by category")
        st.dataframe(
            report["by_category"].to_arrow(), hide_index=True, width="stretch"
        )
    st.download_button(
        "Download city summary CSV",
        data=report["by_city"].write_csv().encode("utf-8"),
        file_name="city_revenue.csv",
        mime="text/csv",
    )

with detail_tab:
    detail = report["detail"]
    st.caption(
        f"Showing {detail.height:,} of {totals['line_count']:,} matching lines; "
        "ordered by date and line identifier."
    )
    st.dataframe(
        detail.to_arrow(), hide_index=True, width="stretch", lazy=False,
        column_config={
            "revenue_huf": st.column_config.NumberColumn("Revenue (HUF)", format="%d"),
            "unit_price_huf": st.column_config.NumberColumn("Unit price (HUF)", format="%d"),
        },
    )
```

The source and transform version are explicit cache arguments. The form's draft state is separate from applied report state. Empty city/category choices deliberately mean no matches rather than silently broadening the query to all values.

The broad user-facing error messages avoid exposing paths or sensitive parser diagnostics; add structured server-side logging in production. The example does not include authentication, tenant isolation, background exports, persistent editing, or a production-grade data-publishing protocol.

### 19.6 `.streamlit/config.toml`

```toml
[server]
headless = true
maxUploadSize = 10

[theme]
base = "light"
primaryColor = "#176B5B"
```

`maxUploadSize` is expressed in megabytes in Streamlit's uploader configuration. The complete dashboard does not use uploads; the setting is an example if you later add Section 15's import workflow. Keep application-level byte checks as well. [web:35]

### 19.7 Run the project

```bash
python generate_demo.py
python -m pytest -q
python -m streamlit run app.py
```

Create the test files from the next section before running pytest. Inspect the default report, narrow the date range, select a single city/category, select no categories, and test a partially selected date range.

## 20. Testing strategy

### 20.1 Unit-test transformations independently of the UI

Polars provides `assert_frame_equal` for DataFrame/LazyFrame assertions. The current parameter names are `rel_tol` and `abs_tol`; row order, column order, and dtype checks are independently configurable. [web:70]

Save as `tests/test_analytics.py`:

```python
from datetime import date

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from analytics import base_query, filtered_query, summarize, validate_source


@pytest.fixture
def sales_path(tmp_path):
    path = tmp_path / "sales.parquet"
    pl.DataFrame({
        "line_id": [1, 2, 3],
        "order_id": [10, 10, 20],
        "order_date": [date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 2)],
        "city": ["Debrecen", "Debrecen", "Budapest"],
        "category": ["Books", "Home", "Books"],
        "quantity": [2, 1, 3],
        "unit_price_huf": [1000, 500, 2000],
    }, schema_overrides={
        "line_id": pl.Int64,
        "order_id": pl.Int64,
        "quantity": pl.Int64,
        "unit_price_huf": pl.Int64,
    }).write_parquet(path)
    return str(path)


def test_validation_and_totals(sales_path):
    validate_source(sales_path)
    result = summarize(base_query(sales_path))
    totals = result["totals"].row(0, named=True)
    assert totals["line_count"] == 3
    assert totals["order_count"] == 2
    assert totals["units"] == 6
    assert totals["revenue_huf"] == 8500
    expected = pl.DataFrame({
        "city": ["Budapest", "Debrecen"],
        "revenue_huf": [6000, 2500],
    }, schema_overrides={"revenue_huf": pl.Int64})
    assert_frame_equal(result["by_city"], expected)


def test_filter_semantics(sales_path):
    q = filtered_query(
        sales_path, date(2026, 1, 1), date(2026, 1, 1),
        ("Debrecen",), ("Books",),
    )
    totals = summarize(q)["totals"].row(0, named=True)
    assert totals["line_count"] == 1
    assert totals["revenue_huf"] == 2000


def test_empty_selection(sales_path):
    q = filtered_query(
        sales_path, date(2026, 1, 1), date(2026, 1, 2), (), ("Books",),
    )
    result = summarize(q)
    assert result["totals"]["line_count"].item() == 0
    assert result["detail"].is_empty()


def test_detail_bound(sales_path):
    result = summarize(base_query(sales_path), detail_limit=1)
    assert result["detail"].height == 1
    assert result["totals"]["line_count"].item() == 3


def test_invalid_dates(sales_path):
    with pytest.raises(ValueError):
        filtered_query(
            sales_path, date(2026, 1, 2), date(2026, 1, 1),
            ("Debrecen",), ("Books",),
        )


def test_duplicate_line_rejected(sales_path):
    source = pl.read_parquet(sales_path)
    pl.concat([source, source.head(1)]).write_parquet(sales_path)
    with pytest.raises(ValueError, match="unique"):
        validate_source(sales_path)
```

Add cases for null keys, schema mismatches, negative values, numerical overflow boundaries, missing files, failed permissions, duplicate dimension keys, and source refreshes before using real data.

### 20.2 UI smoke tests

Streamlit's `AppTest` simulates an application, exposes rendered elements, and requires `.run()` for initial execution and simulated reruns. It can be integrated with pytest. Streamlit 1.66 adds explicit form and form-submit-button test accessors. [web:51][web:38]

Save as `tests/test_app.py`:

```python
from streamlit.testing.v1 import AppTest


def test_app_starts_with_generated_demo_data():
    at = AppTest.from_file("app.py", default_timeout=30).run()
    assert not at.exception
    assert not at.error
    assert len(at.metric) == 4


def test_empty_category_selection():
    at = AppTest.from_file("app.py", default_timeout=30).run()
    assert not at.exception
    at.multiselect(key="draft_categories").set_value([])
    at.form_submit_button(key="apply_filters").click().run()
    assert not at.exception
    assert any("No sales lines" in message.value for message in at.info)
```

Run `python generate_demo.py` first: these smoke tests intentionally expect the generated file. In a larger test suite, create an isolated source fixture rather than sharing a mutable data directory.

`AppTest` is not a substitute for browser testing. Exercise actual table interactions, downloads, upload behavior, authentication redirects, accessibility, and concurrent sessions in a deployed staging environment. The testing API's supported element list should be checked for your pinned version. [web:51]

### 20.3 Migration regression tests

Before a 1.x-to-2.0 upgrade, capture fixtures and compare:

- Sorted aggregate totals and explicit schemas.
- Join match counts and unmatched keys.
- List-explode row counts.
- CSV-selected column order.
- Temporal parsing behavior.
- SQL Decimal arithmetic and rounding.
- Arrow/Map interoperability.

These correspond to documented breaking changes, including changes that can silently alter values, schema, row count, or ordering. [web:4]

## 21. Performance and observability

### 21.1 Measure the full request path

Use a latency budget rather than quoting dataframe-only benchmark results:

```text
User-visible latency =
  source access
  + query planning and execution
  + cache hashing / serialization / copying
  + result conversion
  + server-to-browser transfer
  + frontend rendering
```

The relative cost changes with data size, source layout, cache state, and concurrency. Streamlit's cache has serialization/copy overhead; lazy tables reduce transferred data but impose feature tradeoffs. [web:5][web:33]

### 21.2 Timing without the removed profiler

```python
from time import perf_counter

# For an existing LazyFrame q:
# started = perf_counter()
# result = q.collect()
# elapsed_seconds = perf_counter() - started
```

Collect cold-cache and warm-cache timings separately. Record row/column counts, result size, file layout, engine choice, process memory, scratch-disk usage, concurrency, and package versions. `LazyFrame.profile()` is not available in Polars 2.0. [web:4]

### 21.3 Optimize in this order

1. Verify correctness and establish the report's grain.
2. Remove unnecessary columns and push eligible filters toward lazy scans.
3. Aggregate before converting or transferring to the UI.
4. Bound detail views and download sizes.
5. Add a complete cache key with an explicit freshness policy.
6. Batch filter edits with forms.
7. Isolate independently interactive regions with fragments.
8. Profile concurrent workloads before introducing parallel fragments or extra workers.
9. Partition/preaggregate immutable data for repeated reports when measurements justify it.

Scans enable source-level optimization; caches, forms, fragments, and lazy tables address other bottlenecks. Combining them thoughtfully matters more than applying one decorator everywhere. [web:32][web:5][web:30][web:16][web:33]

### 21.4 Common expensive patterns

| Pattern | Why it hurts | Better approach |
|---|---|---|
| Read a full dataset before filtering | Prevents earlier source optimization | Start with `scan_*` |
| Cache a plan but collect on each interaction | The plan is not executed-result caching | Cache the materialized report |
| Collect a huge result, then show its first rows | Collection already happened | Limit/aggregate in the query; inspect the plan |
| Hash large mutable data repeatedly | Cache lookup itself becomes expensive | Pass immutable source/filter versions |
| Convert large frames back and forth to pandas | Additional processing and memory | Convert at a controlled presentation boundary |
| Several independent collections of the same source | Repeated scans on cache misses | Measure combined plans or preaggregations |
| Many concurrent heavy reports | CPU, memory, and scratch-disk contention | Admission control and workload sizing |

These recommendations follow the distinction between lazy execution, cache behavior, and UI transfer; they are not universal speedup guarantees. [web:19][web:32][web:5][web:33]

The Polars release announcement reports favorable benchmark results under specified conditions. Those are vendor-run, workload-specific measurements, not evidence that every dashboard query will outperform every alternative. [web:2]

## 22. Security and multiuser correctness

### 22.1 Authenticate identity; authorize data access separately

Streamlit supports OIDC-based authentication through `st.login`, `st.user`, and `st.logout`. OIDC identity is not itself application-level permission enforcement. Resolve roles/tenant membership and apply policy before reading data, computing reports, constructing downloads, or looking up cached results. [web:52]

```python
import streamlit as st

if not st.user.is_logged_in:
    st.button("Log in", on_click=st.login)
    st.stop()

st.button("Log out", on_click=st.logout)
# Resolve and enforce application-specific authorization here.
```

This snippet requires a configured OIDC provider and secrets. It is not a complete authorization implementation. Follow the exact authentication settings documented for your pinned version/provider, including token exposure settings if required. [web:52][web:69]

### 22.2 Prevent cache-scope leaks

For a restricted report, derive authorization scope on the server and ensure it is represented in both query construction and cache identity. Do not trust a browser-selected tenant ID as proof of access. Avoid exposing raw user data through a globally cached function with missing scope dimensions. Cached values are shared across users. [web:5]

### 22.3 Treat all client-controlled input as untrusted

- Validate upload contents, not only extensions.
- Do not use an uploaded filename as a server filesystem path.
- Restrict source locations to approved datasets.
- Do not execute arbitrary Python or SQL supplied through the UI.
- Validate table edits even when columns are disabled in the editor.
- Remove sensitive columns before display rather than hiding them.
- Preserve cache integrity and do not accept uploaded pickle files.

Streamlit explicitly warns that upload type checks are not security guarantees and that uploaded names are not sanitized. It also documents the limitations of hidden table columns and the cache's pickle serialization. [web:35][web:33][web:5]

### 22.4 Manage secrets and logs

Use `.streamlit/secrets.toml` locally or a managed secret store. Exclude secrets from Git and Docker build contexts. Restrict filesystem permissions and rotate credentials using your organization's procedure. Never log database URIs containing passwords, tokens, raw uploaded personal data, or full sensitive query results. `st.secrets` is the documented application interface for TOML-managed secrets. [web:63]

### 22.5 Model resource usage per concurrent user

Budget for all of the following, not just the Polars working set:

- Active query state and materialized results.
- Cache serialization/copies.
- Per-session uploaded data and drafts.
- UI conversion/transfer buffers.
- Export generation.
- Scratch disk used by out-of-core work.

The streaming engine and spill-to-disk improve resilience but do not remove resource limits, and shared resource caches introduce concurrency obligations. [web:2][web:5]

## 23. Deployment

### 23.1 Choose a deployment that matches the data policy

Streamlit documents Community Cloud as a sharing platform and provides container deployment guidance. For confidential company data, select a deployment with approved network access, identity controls, storage region, retention rules, and observability. A working public demo is not automatically an approved production architecture. [web:3][web:53]

### 23.2 Minimal container for the generated demo

Place this `Dockerfile` in the project root. Before building, create a reviewed `requirements.lock.txt` from the tested environment.

```dockerfile
FROM python:3.12-slim
WORKDIR /app

COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt

RUN useradd --create-home appuser
COPY --chown=appuser:appuser analytics.py app.py generate_demo.py ./
COPY --chown=appuser:appuser .streamlit/config.toml .streamlit/config.toml
RUN chown -R appuser:appuser /app
USER appuser
RUN python generate_demo.py

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3).read()"
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
```

This adapts the documented Streamlit container pattern: non-root working directory, explicit listening address/port, and a health endpoint. The non-root runtime and selective `COPY` instructions are additional hardening choices. [web:53]

Build and run:

```bash
docker build -t sales-dashboard .
docker run --rm -p 8501:8501 sales-dashboard
```

Do not bake private data or credentials into a reusable image. The `generate_demo.py` build step is only for synthetic demo data. For production, mount an authorized read-only dataset or use controlled object storage, plus a separate writable scratch location when needed.

### 23.3 Production deployment checklist

- Test the exact lock file and container image.
- Configure TLS and an appropriate reverse proxy/load balancer.
- Confirm WebSocket and authentication redirect behavior.
- Set CPU, memory, upload, connection, and execution limits.
- Provision and monitor scratch disk for out-of-core operations.
- Keep per-session state separate from durable persistence.
- Use a supported data snapshot/publishing protocol.
- Test more than one browser session and realistic concurrency.
- Define secret rotation, cache invalidation, and rollback procedures.
- Verify downloads cannot bypass the report's authorization scope.
- Keep CORS/XSRF protections enabled unless an explicitly reviewed deployment requires otherwise.

Streamlit's session state is not persisted through server failure; globally cached resources are mutable shared objects. Deployment must account for those semantics rather than assuming they behave like a database or a distributed cache. [web:31][web:5]

## 24. Polars 1.x to 2.0 migration checklist

This is a prioritized selection, not an exhaustive list of every removal in the official migration guide. Check the complete migration guide and release notes for APIs used by your project. [web:4]

### 24.1 High-impact changes

| Area | Polars 2.0 behavior | Action |
|---|---|---|
| Lazy engine default | `auto` resolves to streaming | Verify order-sensitive logic and memory behavior |
| Grouping/join/unpivot order | Incidental order is not guaranteed | Sort explicitly or use operation-specific ordering controls |
| `read_csv` | Routed through `scan_csv(...).collect()` | Remove obsolete arguments; test schema and column ordering |
| CSV removed options | `n_threads`, `batch_size`, `sample_size`, `rechunk` removed | Review older ingestion helpers |
| CSV dtype override list | Must cover every column | Prefer named overrides or a complete list |
| `read_ipc` | Legacy `memory_map` and `rechunk` options removed | Remove options; rechunk separately if needed |
| String to temporal cast | Direct casts removed | Use `str.to_date/to_datetime/to_time` |
| `LazyFrame.profile()` | Removed | Use plans and end-to-end telemetry |
| Horizontal concat | Equal heights required | Use `horizontal_extend` for intentional null padding |
| Exploding empty lists | Zero output rows by default | Set `empty_as_null=True` when old behavior is required |
| File-like scans | Start at current position | `seek(0)` or use a fresh buffer |

Each behavior above is documented as a breaking change. Several affect results without a syntax error, so successful startup is not adequate migration testing. [web:4]

### 24.2 Dtype and interoperability changes

- Signed integer combined with `UInt64` can now yield `Int128` rather than lossy `Float64`.
- `is_in` no longer performs lossy coercion to a common type; explicitly align dtypes.
- Arrow, Parquet, and Iceberg map columns load as the new Map dtype.
- Unknown Arrow extension types can load as extension dtypes instead of storage dtypes.
- The dataframe interchange protocol was removed; use explicit Arrow/pandas interoperability where appropriate.
- Certain Arrow-stream-only inputs to `from_arrow` now return a Series of Struct rather than a DataFrame.
- Null lists/arrays converted to structs preserve outer null validity.
- `pl.datetime` and `pl.repeat` output names derive from the leftmost argument; use explicit aliases.
- Selector/operator combinations with `pl.col` changed meaning; use selector-to-selector set operations.
- Zero-width frames now preserve height, and constructing data from an empty frame has changed constraints.

Review schemas and downstream consumers, not just computed totals. In a Streamlit app, newly introduced dtypes may also require scalar projections or explicit conversions before display/editing. [web:4][web:34]

### 24.3 SQL changes need financial regression tests

- Lazy SQL parsing/resolution is deferred until optimization/collection/schema resolution.
- Non-exponent numeric literals can now be exact Decimal values rather than floats.
- Decimal multiplication/division use new SQL result-scale rules.
- SQL remainder and integer division truncate toward zero.
- SQL Decimal rounding behavior differs from the old float-based literal behavior.

Test negative numbers, small fractions, precision boundaries, and comparison tolerances. Do not fix a dtype mismatch by blindly casting back if doing so would erase newly preserved precision. [web:4]

### 24.4 A safe rollout sequence

1. Lock the current environment and preserve representative fixtures.
2. Make ordering requirements explicit before upgrading.
3. Remove deprecated APIs using the migration guide.
4. Test in a clean Polars 2.0 environment.
5. Compare output schemas, counts, null behavior, values, and ordering contracts.
6. Test UI rendering, editing, caching, uploads, and downloads.
7. Benchmark realistic data with concurrency and resource limits.
8. Deploy to staging and keep a tested rollback image.

Using `collect(engine="in-memory")` can isolate an engine-related difference while investigating, but it does not restore removed APIs or every other 1.x behavior. [web:4]

## 25. Troubleshooting and quick reference

### 25.1 Symptom-based troubleshooting

| Symptom | Likely area to inspect | Practical response |
|---|---|---|
| App recalculates on each widget interaction | Rerun model and cache keys | Use a form and cache the collected report |
| Report remains stale after replacing a file | Source version absent from cache key | Use immutable snapshot identity or explicit invalidation |
| Revenue rises unexpectedly after a join | Duplicate dimension keys | Check key multiplicity and join reconciliation |
| Row order changes between runs | Incidental streaming order | Sort by semantic keys and deterministic tie-breakers |
| String-to-date cast fails after upgrade | Removed temporal casts | Use strict string parsing methods |
| Reused buffer produces no data/invalid Parquet | Buffer position | Rewind or construct a fresh buffer |
| Fewer rows after `explode` | Empty-list default | Decide whether empty lists should preserve a null row |
| `profile` is missing | Removed API | Use plan inspection and end-to-end measurements |
| Editor returns pandas unexpectedly | Editor return contract | Use explicit Arrow input and `pl.from_arrow` |
| Selection or built-in CSV export unavailable | Lazy table mode | Use a bounded preview with `lazy=False` |
| Hidden confidential column is still reachable | UI hiding is not removal | Project/drop it before passing data to Streamlit |
| Memory failure despite streaming | Stateful work, output size, concurrency | Reduce result size, inspect query shape, monitor RAM/disk |

These diagnoses follow the documented execution, cache, table, and migration semantics; verify the actual error and pinned versions rather than applying them mechanically. [web:5][web:30][web:4][web:33][web:34][web:2][web:55]

### 25.2 Polars quick reference

```python
import polars as pl

example = pl.DataFrame({"city": ["Debrecen", "Budapest"], "value": [10, 20]})
selected = example.select("city", "value")
filtered = example.filter(pl.col("value") > 10)
derived = example.with_columns((pl.col("value") * 2).alias("double"))
summary = example.group_by("city").agg(pl.col("value").sum()).sort("city")
lazy = example.lazy()
schema = lazy.collect_schema()
materialized = lazy.collect()
```

The expression contexts, lazy execution boundary, and schema-resolution methods are the essential building blocks. [web:46][web:19][web:2]

### 25.3 Streamlit quick reference

| Need | API |
|---|---|
| Page configuration | `st.set_page_config` |
| Scalar KPI | `st.metric` |
| Interactive read-only table | `st.dataframe` |
| Table editing | `st.data_editor` |
| Batched filter submission | `st.form` + `st.form_submit_button` |
| Session-local domain state | `st.session_state` |
| Cache serializable result data | `st.cache_data` |
| Share a thread-safe resource | `st.cache_resource` |
| Partial rerun | `st.fragment` |
| Multipage routing | `st.Page` + `st.navigation` |
| Read a configured secret | `st.secrets` |
| OIDC sign-in / identity / sign-out | `st.login` / `st.user` / `st.logout` |
| Simulated app test | `streamlit.testing.v1.AppTest` |

These APIs address different layers of the application; none substitutes for authorization, data validation, or a persistence design. [web:39][web:5][web:30][web:31][web:16][web:58][web:63][web:52][web:51]

## 26. Suggested learning path

### Stage 1: Fundamentals

- Run the first app and change the grouping dimension.
- Practice `select`, `with_columns`, `filter`, and `group_by`.
- Explain each intermediate table's grain and schema.
- Separate nulls, NaN, invalid values, and missing records.

### Stage 2: Reliable interactive analytics

- Run the complete dashboard and its tests.
- Explain draft versus applied filters.
- Change the demo to use an immutable source manifest as its version.
- Add a data-quality panel with bounded diagnostics.
- Test the same report in two browser sessions.

### Stage 3: Larger workloads

- Replace a full read with a lazy scan and inspect the query plan.
- Compare several collections with preaggregations or combined execution.
- Measure cold and warm latency, peak RAM, and scratch-disk pressure.
- Compare a bounded selection table with Streamlit's lazy-browsing mode.
- Move large exports to a controlled background job.

### Stage 4: Production readiness

- Add authentication and server-derived authorization scope.
- Test tenant-safe caching and authorized downloads.
- Add atomic source publishing, monitoring, and an explicit retention policy.
- Validate the exact deployment image under realistic concurrent load.

The destination is not just a fast dataframe calculation. It is a report whose data grain, ordering, numerical semantics, freshness, permissions, and resource costs remain understandable when people interact with it.
