# AGENTS.md — CleanSheet Repository Instructions

## Repository State

This is an **implemented Streamlit + Polars 2.0 statistical analysis application**. The codebase is complete with all core features implemented.

**Stack (verified):**
- Python 3.12
- Streamlit 1.66.0
- Polars 2.0.0 (streaming enabled)
- Seaborn 0.13.2 / Matplotlib 3.9.0
- SciPy 1.13+, Statsmodels 0.14+, Pydantic 2.8+

## Quick Start

```bash
# From project root
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
streamlit run app.py
```

## Test & Verify

```bash
# All tests (28 passing)
pytest tests/ -v

# Single test file
pytest tests/test_analytics.py -v

# Lint + typecheck
ruff check src/
mypy src/
```

## Architecture (Implemented)

```
src/CleanSheet/
├── config.py           # Pydantic Settings (env-driven limits)
├── contracts.py        # Pydantic v2 models — ALL service boundaries
├── errors.py           # Typed exceptions with user_message
├── cli.py              # Headless replay: `cleansheet replay|profile`
├── engine/
│   ├── expressions.py  # Polars expression builders
│   ├── execution.py    # LazyExecutor, materialization boundaries, caching
│   ├── sampling.py     # Reproducible sampling (stable, stratified, bootstrap)
│   ├── semantic_typing.py  # Column → SemanticRole inference
│   ├── assumptions.py  # Diagnostic checks + auto-routing
│   ├── nonparametric.py    # Mann-Whitney, Wilcoxon, Kruskal-Wallis, post-hoc
│   ├── discovery.py        # 9-step autonomous discovery + BH-FDR
│   └── profiling.py        # Single-pass profiling + progressive discovery
├── services/
│   ├── ingest.py       # CSV/Parquet validation + SHA-256
│   ├── prepare.py      # Reversible CleaningStep pipeline
│   ├── profile.py      # Column profiling + quality issues
│   ├── recommend.py    # Eligibility gates per Goal
│   ├── statistics.py   # Adapter pattern (parametric + nonparametric)
│   ├── visualize.py    # Matplotlib worker isolation, Okabe-Ito palette
│   └── reports.py      # Markdown/HTML/CSV export + reproduction script
├── jobs/
│   ├── runner.py       # ProcessPoolExecutor background jobs
│   └── workspace.py    # Session-isolated file storage + janitor
└── ui/                 # Streamlit screens (all import accessibility.py)
    ├── start.py        # Upload + Study Context intake
    ├── import_review.py # Import settings + SemanticRole confirmation
    ├── preparation.py  # Reversible issue cards + recipe
    ├── question.py     # 3-mode: Guided / Target Scan / Autonomous Discovery
    ├── results.py      # 9-part Result Card + follow-ups (sensitivity, confounder, subgroup)
    └── export.py       # ZIP bundle + reproduction script
```

## Key Conventions (Non-Obvious)

### Boundary Rule (Enforced)
- **Only `ui/` imports Streamlit** — `engine/`, `services/`, `jobs/`, `contracts/` are pure Python
- Services accept `AnalysisRequest` / `ColumnRole` / `DatasetRef` and return `AnalysisResult` / `StatisticalResult` / `ProfilingResult`
- This enables headless CLI replay and pytest unit tests without Streamlit

### Contracts Are Source of Truth
- `contracts.py` defines every service I/O via Pydantic v2 (`ConfigDict(extra="forbid", frozen=True)`)
- Run `pytest tests/test_imports.py::test_contracts` to verify schema validity
- When changing a service signature, update the contract model first

### Session State Keys (Single Source)
Managed in `app.py::init_session()`:
```python
session_id, workspace_id, current_stage, dataset_ref, study_context,
column_roles, recipe, recipe_hash, analysis_plan, active_job_id,
results, plots, warnings, stale_results, pending_analysis_request,
pending_import_spec, show_reset_confirm, applied_fixes
```
- Never add ad-hoc `st.session_state["foo"]` — add to `init_session()` and `reset_session()`

### Resource Budgets (Config-Driven)
All limits in `config.py::Settings` (env-overridable):
- `max_upload_size_mb=50`, `max_profiling_columns=50`, `max_plot_points=20000`
- `inference_materialization_limit_mib=256`, `analysis_job_timeout_seconds=30`
- `session_scratch_limit_mib=512`, `max_concurrent_jobs=1`

### Polars 2.0 Patterns Used
- Lazy execution default: `LazyExecutor.source_lf` → `build_preparation_pipeline()` → `.collect(engine="streaming")`
- Single-pass profiling: `build_single_pass_profiling_exprs()` → one `collect()`
- Hash-based sampling for plots: `materialize_for_plotting()` with deterministic row-index hash
- Row order NOT preserved in `group_by`/joins — explicit `.sort()` where needed

### Statistical Policy (Implemented)
- Lead with estimates + 95% CI, not p-values
- Effect sizes: Hedges' g (paired/independent), rank-biserial r, ε², Cramér's V, Pearson/Spearman r
- Bootstrap CIs for all effect sizes (parametric + nonparametric)
- BH-FDR for autonomous discovery; Holm for post-hoc
- Descriptive fallback when eligibility fails (never silent test swap)
- Pair by explicit `pair_id` key, never positional

### Reproducibility
- Every run exports `run_manifest.json` (hashes, versions, seeds, limits, outcomes)
- Export ZIP includes `cleansheet_reproduce.py` — standalone script that:
  1. Verifies source file SHA-256
  2. Replays cleaning recipe via Polars expressions
  3. Re-runs analysis and asserts results match within 1e-6

## Development Workflow

```bash
# 1. Make changes
# 2. Run affected tests
pytest tests/test_analytics.py::TestStatisticalAdapters::test_welch_ttest_adapter -v

# 3. Lint + typecheck
ruff check src/
mypy src/

# 4. Full test suite
pytest tests/ -v

# 5. Manual smoke test
streamlit run app.py
```

## Streamlit Cloud Deployment

- `packages.txt` = empty (no system deps needed)
- `.streamlit/config.toml` configures headless, CORS, theme, Matplotlib
- Deploy from `master` branch, main file `app.py`

## Common Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: CleanSheet` | Not installed in env | `pip install -e .` |
| `KeyError: 'occasion'` in assumptions | Wide-format paired data lacks `occasion` key | Assumptions now check for `pre_col`/`post_col` |
| Tests fail with `TransformStep` | Renamed to `CleaningStep` in contracts | Update imports to `CleaningStep` |
| Matplotlib hangs | Missing `matplotlib.use("Agg")` | `visualize.py` sets at module top |
| Job runner fails on Windows | `mp_context="spawn"` required | Already set in `runner.py` |

## Files That Change Often

- `contracts.py` — schema changes cascade to services/UI
- `engine/assumptions.py` — new diagnostic checks
- `engine/nonparametric.py` — new non-parametric tests
- `services/statistics.py` — new adapters / effect sizes
- `ui/question.py` — new analysis modes / goals
- `ui/results.py` — new follow-up actions

## Reference Commands

```bash
# Headless analysis replay
cleansheet replay data.parquet recipe.json -o output/

# Profile only
cleansheet profile data.csv -o output/

# Run with custom config
CLEANSHEET_MAX_UPLOAD_SIZE_MB=100 streamlit run app.py
```

## Existing Documentation

- `cleansheet_app_blueprint.md` — original 6-week roadmap (architecture reference)
- `streamlit_polars_2_user_guide.md` — stack-specific patterns
- `seaborn.md`, `scientific-stats-python.md` — library references