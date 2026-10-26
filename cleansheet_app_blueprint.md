# CleanSheet: No-Code Statistical Analysis

**A portfolio application blueprint using Streamlit, Polars 2.0, and seaborn**  
**Prepared:** 26 October 2026  
**Status:** Proposed design, not an implemented or benchmarked application

## Product direction

Build **CleanSheet**, a local-first Streamlit application that helps nontechnical users turn a tabular file into a transparent statistical analysis: upload data, review quality issues, choose a question, inspect charts and estimates, and download a reproducible report.

The distinguishing feature should be **trustworthy automation**, not the largest possible collection of statistical tests. The application should automate mechanical work, explain its decisions, and refuse analyses when essential information or assumptions are missing.

**Product promise:** “Understand your table, ask a question, and receive an analysis you can explain—without writing code.”

**Scope assumptions:** A solo portfolio project; a focused first release; CSV and Parquet input; local processing of private files; a public demo using bundled public data; no external AI service, paid API, database, or account system required. “No-code” describes the end-user experience; the application itself is developed in Python.

All feature choices, resource budgets, schedules, and acceptance targets below are **proposed engineering decisions**, not measured results or guarantees.

## Technology reality check

Polars 2.0 is available: its official release announcement and package record identify 6 October 2026 as the release date. Target the requested 2.0 baseline explicitly instead of describing it as an unreleased future dependency. [Official release](https://pola.rs/posts/release-polars-2/) [Package record](https://pypi.org/project/polars/2.0.0/). [pola](https://pola.rs/posts/release-polars-2/)

| Technology | Role | Design implication |
|---|---|---|
| Streamlit | Guided interface and session workflow | Use explicit submission actions and per-session state; forms batch related inputs instead of rerunning on each edit. [Forms documentation](https://docs.streamlit.io/develop/concepts/architecture/forms). [docs.streamlit](https://docs.streamlit.io/develop/concepts/architecture/forms) |
| Polars 2.0 | Parsing, filtering, transformations, profiling, aggregation | Use the lazy API and native expressions; lazy optimization includes filter and column pushdown. [Lazy API](https://docs.pola.rs/user-guide/concepts/lazy-api/). [docs.pola](https://docs.pola.rs/user-guide/concepts/lazy-api/) |
| seaborn | Statistical visualizations | Accept a bounded Polars plotting frame, but acknowledge that the documented alternate-dataframe support converts to pandas internally. This is **Polars-first, not pandas-free**. [seaborn release notes](https://seaborn.pydata.org/whatsnew/v0.13.0.html). [seaborn.pydata](https://seaborn.pydata.org/whatsnew/v0.13.0.html) |
| SciPy | Statistical tests and interval calculations | Put supported calls behind an application-owned adapter; for example, independent-sample t-tests expose a mean-difference confidence interval. [Test documentation](https://docs.scipy.org/doc/scipy-1.16.2/reference/generated/scipy.stats.ttest_ind.html). [docs.scipy](https://docs.scipy.org/doc/scipy-1.16.2/reference/generated/scipy.stats.ttest_ind.html) |
| statsmodels | Multiple-testing adjustment; later extensions | Use its supported adjustment methods rather than implementing multiplicity corrections from scratch. [Implementation documentation](https://www.statsmodels.org/stable/_modules/statsmodels/stats/multitest.html). [statsmodels](https://www.statsmodels.org/stable/_modules/statsmodels/stats/multitest.html) |
| Matplotlib | Figure rendering underneath seaborn | Render in isolated worker processes with a noninteractive backend; Matplotlib documents thread-safety limitations. [FAQ](https://matplotlib.org/stable/users/faq.html). [matplotlib](https://matplotlib.org/stable/users/faq.html) |

**Version policy:** Start compatibility work with Python 3.12, `polars==2.0.0`, and a seaborn 0.13.2 baseline. Resolve Streamlit, NumPy, SciPy, statsmodels, pandas, PyArrow, Pydantic, and development dependencies into an exact lockfile only after the compatibility suite passes. These are candidate choices, not a claim that this exact stack has been tested together.

Keep one tested environment for releases. Test dependency upgrades on a separate branch; record the actual package versions in every exported run manifest. Do not silently upgrade the public demo.

## Portfolio positioning

Position the project as **an explainable statistical workflow with a Polars execution engine**, rather than another automatic data-profiling dashboard.

| Portfolio signal | Concrete evidence |
|---|---|
| Data engineering | Lazy scan plans, explicit schema handling, typed transformations, bounded materialization |
| Statistical judgment | Question-first method selection, estimates and intervals, assumption checks, transparent exclusions |
| Software engineering | UI-independent services, typed contracts, deterministic recipes, automated tests |
| Product thinking | A short guided journey, plain-language explanations, recoverable errors |
| Responsible analytics | No silent cleaning, no causal overclaims, privacy boundaries, report provenance |
| Performance discipline | Reproducible measurements, disclosed hardware, equal-output validation, honest limitations |

The project should demonstrate judgment through its boundaries: deciding when **not** to run a test is part of the product.

## Users and outcomes

**Primary user:** A researcher, operations professional, or small-business analyst who understands their spreadsheet but does not write Python or reliably distinguish statistical tests.

**Secondary user:** A hiring manager or technical reviewer evaluating whether the developer can deliver dependable analytical software.

| User story | Required outcome |
|---|---|
| “Tell me what is in this file.” | Schema, missingness, distributions, categorical summaries, quality warnings |
| “Compare these two groups.” | Confirmed group definitions, group summaries, mean difference, interval, appropriate test |
| “Compare before and after.” | Explicit pairing, retained-pair counts, paired estimate and interval |
| “Do these measurements move together?” | Scatterplot, selected relationship measure, relevant diagnostics |
| “Are these categories associated?” | Contingency table, expected-count checks, supported association test |
| “Give me something shareable.” | Downloadable report, figures, results table, recipe, and execution manifest |

A successful session ends with an understandable answer and its limitations—not merely a p-value.

## Release boundaries

| Capability | First release | Later release |
|---|---|---|
| Input | One CSV or Parquet table per session | XLSX with sheet selection; optional local file-path mode |
| Preparation | Type review, renaming, filters, explicit missing-value policies, optional deduplication | Guided reshaping and validated joins |
| Profiling | Numeric and categorical summaries, missingness, duplicate and constant-column flags | Domain-specific validation packs |
| Charts | Histogram, ECDF, boxplot, scatterplot, count chart, correlation heatmap | Facets, advanced customization, specialist diagnostics |
| Inference | Two-group means, paired means, Pearson/Spearman relationships, categorical association | Welch ANOVA, rank-based methods, regression |
| Automation | Descriptive overview and question-specific recommendations | Additional rule packs after validation |
| Export | Markdown/HTML report bundle, PNG figures, CSV results, JSON recipe and manifest | PDF and optional developer-facing reproduction script |
| Deployment | Local private-data mode; public sample-data-only demo | Authenticated private deployment |
| AI | Not required | Optional language assistance, never unvalidated statistical execution |

Explicitly exclude AutoML, arbitrary Python execution, arbitrary SQL, multi-table modeling, causal inference, survival analysis, time-series inference, weighted surveys, clustered inference, and a general-purpose spreadsheet editor from version one.

## Guided user journey

Use six stages with one visible primary action per stage:

1. **Start:** Choose “Try an example” or, in local mode, “Upload a file”; explain where processing occurs.
2. **Review data:** Show a small preview, import settings, inferred roles, and quality issues requiring attention.
3. **Prepare:** Offer reversible changes with an affected-row preview; require confirmation for destructive changes.
4. **Ask a question:** Offer plain-language cards such as “Compare two groups” and “Explore a relationship.”
5. **Review results:** Lead with the estimate and chart; place method details, assumptions, and warnings nearby.
6. **Export:** Download a shareable report and reproducibility bundle; offer “Clear this session.”

Keep the sidebar limited to the current dataset, current step, completed actions, and reset. Put technical parameters in a collapsed “Method details” panel. Never force users to select from a wall of test names.

### Screen behavior

| Screen | Main controls | Main output | Blocking condition |
|---|---|---|---|
| Import | File selector, separator, decimal convention, encoding, date format | Preview and parse summary | Unsupported or invalid file; unresolved parsing ambiguity |
| Review | Column-role editor and issue acknowledgments | Data dictionary and quality cards | Required analysis variables are unresolved |
| Prepare | Typed filters and approved transformations | Before/after counts and operation history | Invalid conversion or excessive resource use |
| Question | Goal, variables, design questions, analysis purpose | Proposed method and eligibility explanation | Unknown independence or unsupported study design |
| Results | Run, inspect details, select figures | Estimate, uncertainty, table, chart, limitations | Analysis-specific validation failure |
| Export | Include/exclude data, report title, format | Download bundle and disclosure preview | Failed run or invalidated results |

Use readable labels, keyboard-friendly native widgets, colorblind-conscious palettes, and text as well as color for statuses. Provide chart descriptions and a glossary for terms such as “confidence interval” and “paired observations.”

## Autonomous but accountable

Implement automation as a **versioned deterministic rules engine**. Do not make an LLM responsible for selecting tests, computing statistics, changing data, or interpreting assumptions.

| Decision | Automatic behavior | Required user involvement |
|---|---|---|
| Basic profiling | Compute approved summaries and quality flags | None after successful import |
| Column roles | Suggest continuous, categorical, ordinal, date, identifier, or free text | Confirm ambiguous or analysis-critical roles |
| Data changes | Propose cleaning with an impact preview | Approve value changes, row deletion, deduplication, or imputation |
| Charts | Recommend compatible charts | Choose question variables and optional settings |
| Statistical method | Recommend from goal, variable roles, study design, and eligibility | Confirm the design and intended quantity of interest |
| Unsupported analysis | Explain the limitation and continue descriptively | No bypass that disguises an unsupported test as valid |
| Result wording | Fill reviewed templates from validated result fields | Review the report before sharing |

**Autopilot overview:** Run profiling, missingness summaries, a few suitable univariate charts, and descriptive relationship views. Do **not** automatically test every pair of columns or search for significant results.

**Guided inference:** Ask a small number of questions, show the proposed plan, obtain confirmation, then execute. The application can inspect a table, but must not pretend it can establish the sampling design from column values alone.

## Input and preparation

### Import contract

Accept CSV and Parquet only in the first release. Reject archives, executables, serialized Python objects, and files whose structure does not match the approved parser.

Streamlit's uploader performs a best-effort file-type check rather than guaranteeing file safety, and uploads reach the Python backend in an in-memory buffer. A lazy Polars pipeline therefore does not turn the browser upload itself into an out-of-core transfer. [Uploader documentation](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader) [Upload storage](https://docs.streamlit.io/knowledge-base/using-streamlit/where-file-uploader-store-when-deleted). [docs.streamlit](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader)

Proposed ingestion pipeline:

1. Enforce deployment-specific upload and resource limits before expensive parsing.
2. Assign a server-generated opaque dataset identifier; never use an uploaded filename as a storage path.
3. Store input in a private session workspace with restrictive permissions; preserve original bytes and compute a SHA-256 fingerprint.
4. Inspect bounded metadata and a preview in a resource-limited process; validate dimensions, headers, column count, and nested types.
5. Present the selected import settings and schema for confirmation.
6. Build a lazy CSV or Parquet source; optionally normalize approved CSV imports to session-owned Parquet without creating a full intermediate pandas table.
7. Preserve the immutable source and record preparation as replayable operations.

Support semicolon-delimited CSVs and decimal commas explicitly, alongside comma-delimited decimal-point files. Offer UTF-8 and an explicit Windows-1250 fallback; do not silently reinterpret a decoding failure. Ask about ambiguous dates rather than guessing whether `01/02/2026` is January or February.

### Quality policies

| Issue | Proposed default |
|---|---|
| Missing values | Preserve on import; exclude only required variables for an individual analysis, with reported counts |
| NaN and infinity | Distinguish from null during profiling; handle nonfinite analysis values through an explicit, logged policy |
| Duplicate rows | Flag only; deduplication requires approval and a chosen key or whole-row rule |
| Constant columns | Display descriptively; mark ineligible for correlation and relevant tests |
| Numeric identifiers | Suggest identifier role; exclude from automatic correlations |
| Mixed-type fields | Preserve problematic values; show conversion failures and require a type decision |
| Outliers | Flag diagnostically; do not automatically remove or winsorize |
| High-cardinality categories | Warn; use top-category display plus an explicit remainder, not silent deletion |
| List, struct, or map columns | Preserve in source; exclude from scalar analyses until explicitly transformed |
| Duplicate headers | Apply a visible deterministic mapping and retain original labels in the data dictionary |
| Repeated entity IDs | Ask about clustering or repeated measurement; do not assume row independence |

Keep original and prepared row counts visible. Every operation must record its parameters, affected counts, and resulting schema. Implement undo by replaying the recipe to an earlier step, not by mutating the only copy of the table.

## Statistical analysis contract

Every inference result must answer:

- What question and quantity were analyzed?
- Which observations were included and excluded?
- Which method and settings were used, and why?
- What is the estimate, in its original units when possible?
- What uncertainty interval is available, and how was it calculated?
- What are the raw and, where applicable, adjusted p-values?
- Which assumptions were confirmed, inspected, or remain unresolved?
- What can—and cannot—be concluded?

A p-value does not measure effect magnitude or the probability that the hypothesis is true; the ASA also cautions against making decisions solely from a significance threshold. Lead with estimates and uncertainty rather than a green/red significance badge. [ASA statement](https://www.amstat.org/asa/files/pdfs/P-ValueStatement.pdf). [amstat](https://www.amstat.org/asa/files/pdfs/P-ValueStatement.pdf)

### Method routing

The following is an application policy, not a claim that one method is universally appropriate.

| User question | Eligibility and design gate | Proposed method | Required reporting |
|---|---|---|---|
| “Compare average values in two groups” | Continuous outcome; exactly two selected independent groups; design confirmed; sufficient finite data and nondegenerate variance | Welch independent-sample t-test using `equal_var=False` | Group sizes, means, SDs, signed mean difference, matching confidence interval, test statistic, degrees of freedom, p-value |
| “Compare before and after” | Same units measured twice; explicit pairing; one valid value per required occasion | Paired t-test on aligned observations | Pair definition, retained/dropped pairs, before/after summaries, mean paired difference and interval |
| “Explore a linear relationship” | Two continuous variables, valid paired rows, nonconstant inputs, independence confirmed for inference | Pearson correlation | Scatterplot, coefficient, count, confidence interval where supported, p-value and diagnostics |
| “Explore an ordered relationship” | Continuous or declared ordinal variables with a meaningful order | Spearman correlation | Rank correlation, count, ties, interval availability; use a validated permutation route for small-sample inference |
| “Are two categories associated?” | Independent observations; count table without invalid margins; count diagnostics pass | Chi-square independence test | Observed/expected counts, proportions, Cramér's V, degrees of freedom, p-value, correction setting |
| “The category table is sparse” | A valid 2-by-2 table and confirmed independent observations | Two-sided Fisher exact test | Table, denominators, odds ratio definition, p-value; interval only when an explicitly implemented method is available |
| “Describe my data” | Valid supported columns | Descriptive summaries only | Numeric/categorical summaries, missingness, distributions, no inferential claims |

SciPy documents Welch's test through `equal_var=False`; paired tests and Pearson correlation expose confidence-interval functionality. Use these documented capabilities through tested adapters. [Welch parameter](https://docs.scipy.org/doc/scipy-1.8.0/reference/generated/scipy.stats.ttest_ind.html) [Paired test](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_rel.html) [Pearson](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.pearsonr.html). [docs.scipy](https://docs.scipy.org/doc/scipy-1.8.0/reference/generated/scipy.stats.ttest_ind.html)

For Spearman inference, SciPy warns that its asymptotic p-value is accurate only for very large samples and recommends considering permutation tests for smaller samples. Record the permutation count, random seed, and method; if the configured budget is insufficient, return the descriptive coefficient without claiming an adequately computed inferential result. [Spearman documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html). [docs.scipy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html)

For categorical analysis, use a documented conservative small-count policy: flag any observed or expected cell below five; recommend Fisher for eligible 2-by-2 tables and otherwise return descriptive results until a validated resampling route exists. This is a product gate, not a universal theorem about chi-square validity. [Chi-square guidance](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chi2_contingency.html). [docs.scipy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chi2_contingency.html)

For the sparse 2-by-2 route, document the row/column orientation and odds-ratio convention, including zero-cell behavior, instead of treating the returned statistic as interchangeable with every other odds-ratio estimator. [Fisher exact documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.fisher_exact.html). [docs.scipy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.fisher_exact.html)

### Numerical eligibility gates

Implement numerical checks before library calls: require at least two finite observations per independent-sample group, at least two retained pairs for a paired test, a positive relevant standard error, and sufficient nonconstant paired observations for correlation. These are minimum computational gates, **not** guarantees of credible inference; very small samples must trigger explicit method-specific warnings and may remain descriptive-only under the reviewed statistical policy.

For Pearson intervals, require enough observations for the selected interval method and flag nonfinite or degenerate results. For paired comparisons, inspect the within-pair differences rather than treating the two occasion distributions as independent samples. Zero-margin contingency tables, constant pair differences, and invalid degrees of freedom must yield an explained blocked or unavailable status, not an uncaught error.

Keep computational validity separate from scientific validity. Add an analysis-purpose and sampling-context prompt; do not imply that a user confirmation establishes representativeness or that complete-case exclusions solve missing-data bias.

### Non-negotiable safeguards

- Require “independent,” “paired,” or “unknown” study-design selection; unknown means descriptive-only.
- Ask whether observations are clustered, weighted, repeated, or ordered in time; route unsupported designs out of ordinary independent-row inference.
- Define the desired quantity before recommending a method: means, ranks, correlation, and proportions are different questions.
- Do not automatically switch tests based on a normality-test p-value; expose plots, outlier diagnostics, and method-specific warnings.
- Validate method-specific sample counts, finite values, variance, category levels, and pairing before computation.
- Pair by an explicit entity key or a confirmed one-row-per-entity wide layout; never pair separately sorted vectors by position.
- Default to two-sided tests and 95% intervals; record any permitted change before execution.
- Permit descriptive output when inference is blocked; do not silently substitute another test.
- Use all eligible rows for a requested test or refuse it on resource grounds; never quietly run inference on a chart sample.
- Mark unavailable intervals explicitly, including a reason; do not fabricate a zero-width interval.
- Avoid “no effect” wording for nonsignificant results and avoid causal language for observational associations.
- Ask for a practical importance threshold where useful; do not automatically label every effect “small,” “medium,” or “large.”

For later rank-based comparisons, treat Mann–Whitney as a distribution/rank question rather than an automatic median test; its documented exact method does not correct for ties. [Mann–Whitney documentation](https://docs.scipy.org/doc/scipy-1.16.1/reference/generated/scipy.stats.mannwhitneyu.html). [docs.scipy](https://docs.scipy.org/doc/scipy-1.16.1/reference/generated/scipy.stats.mannwhitneyu.html)

### Multiple-testing policy

For one declared comparison, report that no family adjustment was applied. For a batch, require the family of tests to be defined before execution and use Holm adjustment by default; retain every attempted comparison and explain exclusions. statsmodels provides Holm and false-discovery-rate adjustment methods. [Multiplicity documentation](https://www.statsmodels.org/stable/_modules/statsmodels/stats/multitest.html). [statsmodels](https://www.statsmodels.org/stable/_modules/statsmodels/stats/multitest.html)

Keep correlation heatmaps descriptive by default. Do not add significance stars or generate hundreds of p-values automatically. If batch inference is added later, include all unique eligible pairs in the declared family rather than adjusting only the interesting results.

State explicitly that batch adjustment does not eliminate selection bias from repeated filtering, changing questions after seeing results, or rerunning analyses across sessions. Treat ordinary effect intervals as individual intervals unless simultaneous coverage has actually been implemented.

## Visualization rules

| Data or goal | Recommended chart | Guardrail |
|---|---|---|
| One continuous variable | Histogram plus optional ECDF | Show units, retained count, bin policy, and exclusions |
| Continuous outcome across groups | Boxplot with a bounded observation overlay | Display group sizes; retain outliers unless explicitly filtered |
| Two continuous variables | Scatterplot | Disclose sampling; do not fit an inferential line by default |
| Categorical distribution | Count or proportion chart | Make denominator and remainder category explicit |
| Numeric relationships | Correlation heatmap | Cap selected variables; show pairwise counts separately |
| Missingness | Missingness-rate chart and compact matrix | Label the denominator and whether the matrix is sampled |
| Estimated group differences | Point estimate with an interval | Use intervals from the statistical service, not a second hidden calculation |

Make a `PlotSpec` describe columns, plot type, category ordering, transform, aggregation, sampling, and labels. Validate it before rendering. Default to a maximum of 20 displayed categories and 20,000 points for observation-level plots; these are configurable budgets, not statistical thresholds.

seaborn can accept Polars frames through dataframe interchange, but the protocol does not cover every Polars dtype, and seaborn's documented path still converts internally to pandas. Project and bound the plotting data **before** crossing that boundary. [Polars visualization guide](https://docs.pola.rs/user-guide/misc/visualization/?ref=danmackinlay.name) [seaborn notes](https://seaborn.pydata.org/whatsnew/v0.13.0.html). [seaborn.pydata](https://seaborn.pydata.org/whatsnew/v0.13.0.html)

For precomputed means and intervals, disable seaborn's default re-estimation and draw the approved intervals explicitly. Do not bootstrap already aggregated group means as though they were independent original observations. Label raw-point samples separately from full-data summaries.

Render each figure with its own figure/axes objects in an isolated worker using the `Agg` backend; return PNG bytes and close the figure in a `finally` block. Matplotlib documents that access from multiple threads needs synchronization; a worker-process boundary is the proposed simplification here. [Matplotlib FAQ](https://matplotlib.org/stable/users/faq.html). [matplotlib](https://matplotlib.org/stable/users/faq.html)

## System architecture

Keep the application a modular monolith: one Streamlit frontend, one reusable analytical package, and bounded local worker processes. Avoid an unnecessary API server, task broker, or database in the first release.

```text
Streamlit interface
        |
        v
Session controller and workflow state
        |
        v
Validated request + immutable dataset reference
        |
        v
Job runner with resource and timeout limits
        |
        +--> Ingestion and schema validation
        +--> Polars lazy preparation and profiling
        +--> Deterministic recommendation rules
        +--> SciPy / statsmodels statistical adapters
        +--> Bounded seaborn / Matplotlib rendering
        +--> Report and reproducibility packaging
        |
        v
Typed result + warnings + artifacts + provenance
        |
        v
Streamlit display and downloads
```

**Boundary rule:** Only UI modules import Streamlit. Analytical services accept validated inputs and return serializable results. Worker code never calls `st.*` or reads session state.

### Module responsibilities

| Module | Owns | Must not do |
|---|---|---|
| `ingest` | File inspection, parser options, source identity | Guess unresolved formats and discard failures |
| `prepare` | Validated operations compiled to Polars expressions | Evaluate user Python, SQL, or arbitrary expressions |
| `profile` | Counts, summaries, quality diagnostics | Modify the source data |
| `recommend` | Explainable eligibility and routing rules | Search for the most significant method |
| `statistics` | Tests, estimates, intervals, corrections | Format unchecked narrative claims |
| `visualize` | Bounded plot preparation and figure rendering | Materialize the full dataset without a budget |
| `reports` | Escaped templates and artifact packaging | Execute imported recipes as code |
| `jobs` | Worker lifecycle, quotas, cancellation, cleanup | Assume a UI spinner cancels computation |
| `ui` | Controls, navigation, state, result presentation | Contain statistical formulas or parser logic |

## Polars execution design

Use `scan_csv` or `scan_parquet` where supported by the validated import path. Compile filters and transformations into native expressions; run `collect_schema()` during planning and materialize only at explicit boundaries. The lazy API supports pushdown optimizations, and the 2.0 release emphasizes early schema validation. [Lazy optimization](https://docs.pola.rs/user-guide/lazy/optimizations/) [Polars 2.0](https://pola.rs/posts/release-polars-2/). [docs.pola](https://docs.pola.rs/user-guide/lazy/optimizations/)

### Polars 2.0 implications

Polars 2.0 makes streaming the default for lazy collection, introduces spill-to-disk support for selected operations, and does not guarantee the previous row ordering for operations such as grouping and joins. The release announcement explicitly says out-of-core coverage is incomplete, including planned additional join/group-by support. Do not market this app as having unlimited-memory analytics. [Official release](https://pola.rs/posts/release-polars-2/). [pola](https://pola.rs/posts/release-polars-2/)

Required design responses:

- Create and preserve a source-row identifier before transformations when row identity matters.
- Sort displayed aggregates explicitly; do not rely on implicit execution order.
- Use explicit pair keys, not output position, for paired analyses.
- Resolve type conversions deliberately; surface failed casts instead of silently coercing values to missing.
- Keep engine choices in one adapter rather than scattering version-specific settings through pages.
- Separate data spill files from exported artifacts; restrict and clean the private scratch directory.
- Enforce scratch-space and process-memory limits through the runner or deployment environment; do not rely on Polars defaults as application quotas.
- Test actual memory behavior of each supported operation, including NumPy conversion and plotting.

### Materialization boundaries

| Boundary | Allowed payload |
|---|---|
| Preview | First 100 rows and selected columns; explicitly not a representative sample |
| Profiling result | Compact aggregate tables and quality metadata |
| Statistical adapter | Only required eligible variables, within a preflight memory budget |
| Plot renderer | Aggregates or an explicitly disclosed deterministic sample |
| Export | Selected final artifacts; prepared data only with explicit approval |

Calling `.lazy()` after eagerly reading a huge file is not the intended design. Likewise, converting the whole table to pandas before calling seaborn defeats the proposed memory boundary.

For reproducible visual samples, stabilize input ordering by source-row identity, then apply a fixed seeded sampling procedure. Record the seed and library versions; do not promise identical sample membership across arbitrary engine/version changes.

## Session and job lifecycle

Streamlit normally reruns application code after widget interactions; forms batch edits, and Session State preserves values within a user session. Make reruns cheap by storing validated requests and completed artifacts rather than re-executing analyses during ordinary navigation. [State model](https://docs.streamlit.io/develop/concepts/architecture/session-state) [Forms](https://docs.streamlit.io/develop/concepts/architecture/forms). [docs.streamlit](https://docs.streamlit.io/develop/concepts/architecture/forms)

Recommended session fields:

```text
session_id, workspace_id, dataset_ref, import_spec,
column_roles, recipe, recipe_hash, current_stage,
analysis_plan, active_job_id, result_refs, last_activity
```

Keep draft widget values separate from committed analysis settings. A changed input invalidates dependent results; stale results may remain visible only with an unmistakable “out of date—rerun required” label.

### State machine

```text
EMPTY -> IMPORT_REVIEW -> DATA_READY -> PLAN_READY
                                      |
                                      v
                               QUEUED -> RUNNING
                                      |
                    +-----------------+------------------+
                    v                 v                  v
                COMPLETE          PARTIAL             FAILED
                    |
                    v
               EXPORT_READY
```

Include `CANCELLED`, `TIMED_OUT`, and `INVALIDATED` terminal statuses. A job may finish partially when a descriptive summary succeeds but an optional plot fails; it must not present a failed statistical test as a successful analysis.

Use one active job per session and a bounded deployment-wide queue. Start CPU-heavy work with spawn-based child processes; do not fork an already multithreaded runtime. Pass workspace references and small validated specifications rather than copying large in-memory tables repeatedly.

Enforce cancellation by terminating the owned worker process and cleaning its scratch files. A timeout on a waiting future is not sufficient if the calculation continues consuming resources. Prevent double-submission and ignore completed work whose dataset/recipe identity no longer matches the session.

### Cache and privacy

Current Streamlit documentation distinguishes global caches, which are available across users, from session-scoped caches; cached values also involve pickle serialization. Use Session State or a tested session-scoped cache for private derived artifacts, never a global private-data cache. [Cache API](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data). [docs.streamlit](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data)

Default policy: globally cache only immutable bundled public examples and static resources. Keep private results in a bounded per-session store; use session-scoped caching only if supported by the pinned Streamlit release. Never accept uploaded pickle files or deserialize user-supplied Python objects.

Key derived results by session identity plus the input fingerprint, import configuration, schema, semantic roles, transformation recipe, analysis settings, rules version, and dependency identity. Do not exclude security-relevant arguments from cache keys.

“Clear this session” must cancel owned jobs, remove session artifacts, clear relevant state, and reset widgets. Add an expiry janitor and startup cleanup for abandoned workspaces; do not depend on immediate browser-disconnect cleanup or promise forensic secure erasure.

## Typed contracts

Use Pydantic models or equivalent validated types at service boundaries. Forbid unknown operation types, unknown fields where appropriate, invalid column references, and out-of-range parameters.

| Contract | Essential fields |
|---|---|
| `DatasetRef` | Opaque ID, workspace reference, source SHA-256, format, schema identity |
| `ImportSpec` | Encoding, delimiter, decimal convention, date policy, null tokens, schema overrides |
| `ColumnRole` | Column, physical dtype, semantic role, ordinal order, confirmation status |
| `TransformStep` | Versioned operation enum, validated arguments, input/output schema, affected counts |
| `AnalysisRequest` | Goal, variables, study design, estimand, confidence level, missingness policy, family ID |
| `EligibilityResult` | Allowed/blocked status, rule IDs, reasons, user confirmations, warnings |
| `StatisticalResult` | Method, group counts, estimate, interval/method/status, statistic, df, p-values, exclusions |
| `PlotSpec` | Plot type, variables, order, labels, transform, sampling/aggregation policy |
| `AnalysisResult` | Run ID, status, typed results, plots, warnings, provenance, artifact references |
| `RunManifest` | Input and recipe hashes, application/dependency versions, seeds, timestamps, limits, outcomes |

Separate `not_applicable`, `not_computed`, `blocked`, and `failed` instead of representing all four as an ambiguous null. Serialize unsupported nonfinite numbers as null plus an explicit status; keep exported JSON standards-compliant.

### Example analysis specification

This is a proposed request structure—not an executed analysis or fabricated result. It uses column names from the public penguin dataset for the demonstration journey.

```json
{
  "spec_version": "1.0",
  "goal": "compare_two_means",
  "outcome": "body_mass_g",
  "group": "species",
  "group_levels": ["Adelie", "Gentoo"],
  "contrast": "Adelie_minus_Gentoo",
  "study_design": "independent",
  "design_confirmation_source": "user",
  "estimand": "difference_in_population_means",
  "missing_policy": "required_columns_complete_cases",
  "nonfinite_policy": "exclude_and_report",
  "method": "welch_t",
  "alternative": "two-sided",
  "confidence_level": 0.95,
  "analysis_purpose": "exploratory",
  "multiplicity": {"method": "none", "family_size": 1},
  "seed": 42
}
```

Generate this specification from allowlisted controls. Validate it again in the worker; do not treat a recipe imported from a file as trusted code or allow it to supply local filesystem paths.

## Reproducibility and export

The default download should be a ZIP containing a report, figures, tables, and enough metadata to reproduce the analysis against the same input. Do not include private source data by default.

```text
CleanSheet-run/
  report.md
  report.html
  results.csv
  data_dictionary.csv
  quality_issues.csv
  recipe.json
  run_manifest.json
  figures/
    distribution.png
    comparison.png
```

Use relative image links in Markdown and embed or package assets for HTML. Report generation should be deterministic apart from declared metadata such as execution timestamps.

Report sections should cover the question, dataset description, included/excluded counts, preparation steps, estimates and intervals, charts, methods, multiplicity, unresolved assumptions, limitations, and reproduction instructions. Make the technical appendix collapsible in HTML rather than omitting it.

A recipe must include import settings, roles and ordinal ordering, filters, transformations, method choices, contrast direction, confidence level, correction family, seeds, plotting sample policy, and rules version. Compute its identity from canonical JSON. Input fingerprints help identify bytes but are **not** a privacy or anonymization mechanism.

Reproduction requires the same source bytes and compatible locked environment; without the original data, the exported metadata documents the run but cannot recreate its calculations. Supply a CLI entry point that accepts an input path and recipe and invokes the same headless services as the UI.

Escape dataset labels and report text. For CSV intended for spreadsheet viewing, implement and test formula-injection defenses and explain any changed text fields; preserve exact values in a separate machine-readable representation where needed. OWASP notes that there is no universal CSV sanitization strategy safe across all spreadsheet consumers. [CSV injection guidance](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/07-Injection/21-CSV_Injection/). [wstg.owasp](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/07-Injection/21-CSV_Injection/)

## Security and deployment

| Mode | Data policy | Recommended first-release behavior |
|---|---|---|
| Local private analysis | Files processed on the user's own machine | Bind to loopback by default; no outbound analytical requests; private temporary workspaces |
| Public portfolio demo | Bundled public examples only | Disable arbitrary uploads; show an explicit demo-mode banner |
| Future private hosted mode | Uploaded data reaches the deployed backend | Require authentication, access controls, resource isolation, documented retention and operational review |

Do not advertise a hosted Streamlit upload workflow as “data never leaves your computer”: uploaded files are transferred to the backend. Explain the difference between local deployment and hosted processing. [Upload documentation](https://docs.streamlit.io/knowledge-base/using-streamlit/where-file-uploader-store-when-deleted). [docs.streamlit](https://docs.streamlit.io/knowledge-base/using-streamlit/where-file-uploader-store-when-deleted)

Security requirements:

- No arbitrary code, formula execution, user SQL, URL fetching, or filesystem browsing in the no-code interface.
- Generate server-side filenames; validate paths remain within the owned workspace.
- Apply limits to file size, parsed dimensions, column/string size, decoded memory, worker runtime, scratch storage, and exports.
- Use parser isolation, maintained dependencies, and dependency/security scanning.
- Preserve Streamlit's applicable request protections; do not disable them as a deployment shortcut.
- Do not log row values, raw filenames, column labels, file fingerprints, or reports by default.
- Log opaque run IDs, durations, dimensions, status/error codes, and resource usage only.
- Preview exports for accidental identifier inclusion; exclude source/prepared data unless explicitly requested.
- Disclose any temporary disk staging and spilling; make retention and deletion behavior honest.
- Treat local-first operation as a privacy-oriented design, not a blanket regulatory-compliance guarantee.

## Resource budgets

Use configurable limits with clear messages. Initial values below are deliberately conservative starting points to revise after measurement.

| Resource | Initial proposed budget | On limit |
|---|---|---|
| Local upload size | 50 MB | Explain the limit and suggest reducing columns or using an approved local-path extension later |
| Public demo input | Bundled files only | Upload disabled |
| Supported scalar columns | 200 per file | Ask the user to reduce the table |
| Full profiling width | 50 selected columns per run | Offer column selection; compute lightweight schema checks separately |
| Preview | 100 rows | Label as first rows, not a random sample |
| Observation-level plot | 20,000 rows | Use a disclosed reproducible sample |
| Category display | 20 categories | Show a remainder category for display only |
| Correlation view | 20 selected numeric columns | Require variable selection |
| Inference materialization | Preflight against a configurable 256 MiB selected-data estimate | Refuse or use an explicitly implemented exact summary-statistics path; never silently sample |
| Analysis job | 30 seconds | Terminate worker; preserve valid earlier artifacts |
| Full export job | 60 seconds | Abort cleanly; offer smaller bundle |
| Session scratch storage | 512 MiB | Stop writes and explain the resource limit |
| Local inactivity expiry | 30 minutes, best-effort cleanup | Delete owned artifacts via janitor; explain loss of session state |

Estimate memory before expensive conversions, but also enforce a measured worker high-water limit through the platform; estimates alone cannot guarantee safety. Include copies, library overhead, simultaneous sessions, and the in-memory upload in capacity planning.

Do not make a speedup claim until measurements exist. Profile ingestion, preparation, inference, plotting, and export separately so the project does not hide plotting or conversion costs behind a fast Polars aggregate.

## Repository structure

```text
CleanSheet/
  app.py
  pyproject.toml
  uv.lock
  README.md
  LICENSE
  Dockerfile
  .streamlit/
    config.toml
  src/CleanSheet/
    config.py
    contracts.py
    errors.py
    ui/
      start.py
      import_review.py
      preparation.py
      question.py
      results.py
      export.py
    services/
      ingest.py
      prepare.py
      profile.py
      recommend.py
      statistics.py
      visualize.py
      reports.py
    engine/
      expressions.py
      execution.py
      sampling.py
    jobs/
      runner.py
      worker.py
      workspace.py
    reporting/
      templates/
      interpretations.py
    cli.py
  tests/
    unit/
    statistical/
    integration/
    ui/
    security/
    performance/
    fixtures/
  examples/
    public-data/
    recipes/
  docs/
    architecture.md
    statistical-policy.md
    data-handling.md
    benchmark-method.md
    decisions/
  benchmarks/
  .github/workflows/
    ci.yml
```

Use `uv` or an equivalent reproducible environment manager, Ruff, a type checker, pytest, and a dependency scanner. Keep benchmark outputs and reports out of the source tree unless deliberately published; exclude private workspaces and uploads from version control.

## Verification strategy

Streamlit's `AppTest` can simulate application interaction and inspect rendered output; use it for UI workflows while testing the analytical package independently. Add browser automation for file upload/download and behaviors not covered by the selected AppTest release. [App testing](https://docs.streamlit.io/develop/api-reference/app-testing). [docs.streamlit](https://docs.streamlit.io/develop/api-reference/app-testing)

| Layer | Required checks |
|---|---|
| Unit | Parser settings, role inference, transformation validation, rule decisions, state transitions |
| Statistical | Adapter agreement with pinned library calls; independently checked reference cases; interval and contrast direction |
| Invariance | Row permutation does not change order-invariant statistics; group reversal changes signed estimates correctly |
| Paired analysis | Key alignment, duplicate keys, incomplete pairs, occasion ordering, no positional matching |
| Integration | Input → recipe → result → export; replay gives equivalent results within documented tolerance |
| UI | Disabled states, confirmation gates, clear error messages, stale-result invalidation, repeated reruns |
| Browser | Real upload, downloads, reset, separate sessions, navigation during running jobs |
| Security | Wrong file structure, hostile labels, path traversal, oversized input, formula-like export text, cross-session leakage |
| Reliability | Cancellation, timeout, worker crash, stale job completion, disk-full behavior, abandoned workspace cleanup |
| Performance | Cold/warm timings, peak process-tree memory, scratch use, concurrent-job behavior |

Keep malformed-file fixtures and small hand-verifiable arrays as explicit software test cases; they are not evidence about real populations. Use public observed datasets for the portfolio demonstration and performance measurements. Record expected results from an independently reviewed reference, not solely from the same adapter being tested.

### Release acceptance criteria

- A first-time user can complete the sample-data journey without writing code or knowing test names.
- Every executed inference includes eligibility reasoning, counts, exclusions, method, estimate, and interval status.
- Every result clearly identifies whether it used full eligible data or a disclosed sample; inference never silently uses a plot sample.
- All supported statistical adapters pass numerical reference tests at documented tolerances.
- Replaying a recipe in the locked environment reproduces numeric results within declared tolerance.
- Updating the dataset, parsing settings, roles, or preparation invalidates dependent results.
- Two concurrent sessions cannot access each other's artifacts or private caches.
- Cancelled/timed-out workers stop consuming owned compute and scratch resources.
- The app handles empty, malformed, all-null, constant, sparse, and high-cardinality inputs without an uncaught UI traceback.
- CI is green, the dependency lock is committed, and a reviewer can run the project from the README.

**Proposed usability target:** At least four of five nontechnical trial users complete the public-data journey in ten minutes without coaching. Report the actual trial result, including failures; do not present the target as achieved evidence.

## Build roadmap

Treat this as a six-week part-time sequence of exit gates, not a fixed delivery promise. Prefer cutting scope over weakening statistical or privacy safeguards.

| Phase | Build | Exit gate |
|---|---|---|
| Week 1: Foundations | Repository, environment lock candidate, contracts, workspace manager, CSV/Parquet import | Valid and invalid inputs are handled predictably; original data is preserved |
| Week 2: Trustworthy overview | Roles, quality flags, lazy profiling, preparation recipe, preview | Every data-changing action is explicit and reversible |
| Week 3: Visual workflow | Question cards, chart recommendations, bounded plotting, plot exports | No full-table pandas conversion; sample policies appear in UI and report |
| Week 4: Statistical core | Welch, paired t-test, Pearson/Spearman, categorical routing, interval adapters | Method eligibility and reference-result tests pass |
| Week 5: Reproducibility | Job runner, limits, report bundle, CLI recipe replay, stale-result handling | Cancel/replay/export workflows pass end-to-end tests |
| Week 6: Portfolio release | Public sample-only deployment, usability tests, measured benchmarks, documentation, demo recording | Published release has disclosed limitations and passes acceptance checks |

If time is constrained, ship an initial vertical slice—CSV import → quality review → two-group Welch comparison → report export—before adding the remaining methods. Keep paired analysis and sparse-table handling behind feature flags until their validation gates pass.

## Demonstration and benchmarks

Use Palmer Penguins as the bundled introductory dataset: it contains observed penguin measurements, missing values, and categorical variables, and the dataset is available under CC0. Retain attribution and source details even though the license permits broad reuse. [Dataset introduction](https://allisonhorst.github.io/palmerpenguins/articles/intro.html). [allisonhorst.github](https://allisonhorst.github.io/palmerpenguins/articles/intro.html)