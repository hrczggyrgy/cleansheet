# AGENTS.md — CleanSheet Repository Instructions

## Repository State

This is a **design/planning repository**, not an implemented codebase. All files are Markdown design documents. There is no `pyproject.toml`, no `src/`, no tests, no CI, and no lockfile yet.

The primary artifact is `cleansheet_app_blueprint.md` — a detailed blueprint for a Streamlit + Polars 2.0 + seaborn application called **CleanSheet**.

## Key Design Documents

| File | Purpose |
|------|---------|
| `cleansheet_app_blueprint.md` | Complete application blueprint: architecture, statistical policy, UI journey, contracts, verification strategy, 6-week build roadmap |
| `streamlit_polars_2_user_guide.md` | Practical guide for the target stack (Streamlit 1.66, Polars 2.0, Python 3.12) |
| `seaborn.md` | Seaborn 0.13.2 ecosystem reference (plotting layer, not a statistics engine) |
| `scientific-stats-python.md` | Scientific statistical workflow reference (pandas/NumPy/SciPy/statsmodels stack) |
| `Statistical Analysis of Tabular Data A Plain-Language Guide.md` | Non-technical statistical analysis guide |

## Target Stack (from blueprint)

- **Python**: 3.12
- **Streamlit**: 1.66.0
- **Polars**: 2.0.0 (streaming default, spill-to-disk, order changes in group_by/joins)
- **seaborn**: 0.13.2 (accepts Polars via interchange, converts to pandas internally)
- **SciPy**: statistical tests and intervals
- **statsmodels**: multiple-testing adjustments
- **Matplotlib**: rendering backend (Agg, isolated worker processes)
- **Pydantic**: typed contracts at service boundaries
- **uv**: environment manager (recommended)

## Architecture Principles (from blueprint)

1. **Modular monolith**: One Streamlit frontend, one reusable analytical package, bounded local workers
2. **Boundary rule**: Only UI modules import Streamlit. Analytical services accept validated inputs, return serializable results. Workers never call `st.*` or read session state.
3. **Polars-first**: Use lazy API (`scan_csv`/`scan_parquet`), native expressions, explicit materialization boundaries. Never convert full table to pandas before seaborn.
4. **Deterministic rules engine**: Automation = versioned deterministic rules, not LLM decisions. Statistical method selection is rule-based with user confirmation gates.
5. **Reproducibility**: Every run exports a manifest (input hash, recipe hash, versions, seeds, limits, outcomes). CLI entry point replays recipes headless.

## Critical Polars 2.0 Behaviors to Respect

- Streaming is default for `LazyFrame.collect()` — does not guarantee constant memory for all operations
- Row order is **not preserved** through `group_by`, joins, `unpivot` — always sort explicitly
- `explode` on empty list → zero rows (was one null row in 1.x)
- Direct string-to-temporal casts removed — use `str.to_date`/`str.to_datetime`
- `LazyFrame.profile()` removed — use `explain()` + `show_graph(engine="streaming", plan_stage="physical")`
- CSV reader behavior changed — check migration guide before porting older recipes

## Critical Streamlit Behaviors to Respect

- Script reruns top-to-bottom on widget interaction — use `st.session_state` for persistence
- `st.cache_data` = shared across users, returns copies; `st.cache_resource` = shared instance
- **Never** globally cache private uploaded data — use Session State or session-scoped cache
- Forms batch inputs; fragments limit rerun scope
- `st.dataframe` accepts Polars DataFrame/LazyFrame; explicit Arrow conversion is a boundary choice
- Uploaded files reach backend memory — "local-first" means loopback binding, not zero network transfer

## Statistical Policy Highlights (from blueprint)

- **Lead with estimates and intervals**, not p-values
- **Require explicit study design**: independent / paired / unknown (unknown = descriptive only)
- **Validate before compute**: finite values, variance, category levels, pairing keys, sample counts
- **No silent test switching** on normality p-values — expose diagnostics instead
- **Multiple testing**: one comparison = no adjustment; batch = Holm by default, family defined upfront
- **Descriptive fallback**: when inference blocked, return descriptive output with explanation, never substitute another test silently
- **Pair by explicit entity key**, never by positional alignment after sorting

## Build Roadmap (6 phases, from blueprint)

| Phase | Focus | Exit Gate |
|-------|-------|-----------|
| Week 1 | Foundations: repo, env lock, contracts, workspace, CSV/Parquet import | Valid/invalid inputs handled; original data preserved |
| Week 2 | Trustworthy overview: roles, quality flags, lazy profiling, prep recipe | Every data change explicit and reversible |
| Week 3 | Visual workflow: question cards, chart recommendations, bounded plotting | No full-table pandas conversion; sample policies visible |
| Week 4 | Statistical core: Welch, paired t, Pearson/Spearman, categorical, intervals | Method eligibility + reference-result tests pass |
| Week 5 | Reproducibility: job runner, limits, report bundle, CLI replay | Cancel/replay/export workflows pass end-to-end |
| Week 6 | Portfolio release: public demo, usability tests, benchmarks, docs | Published release with disclosed limitations |

## If Implementing: First Commands to Run

```bash
# From project root (when code exists)
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "streamlit==1.66.0" "polars==2.0.0" pyarrow pytest
python -m pip install "seaborn[stats]==0.13.2" scipy statsmodels matplotlib pydantic
python -c "import sys, streamlit, polars; print(sys.version); print(streamlit.__version__); print(polars.__version__)"
python -m streamlit run app.py
```

## Verification Strategy (from blueprint)

| Layer | Required Checks |
|-------|-----------------|
| Unit | Parser settings, role inference, transformation validation, rule decisions, state transitions |
| Statistical | Adapter agreement with pinned libs; independently checked reference cases; interval/contrast direction |
| Invariance | Row permutation doesn't change order-invariant stats; group reversal flips signed estimates |
| Paired analysis | Key alignment, duplicate keys, incomplete pairs, occasion ordering, no positional matching |
| Integration | Input → recipe → result → export; replay gives equivalent results within tolerance |
| UI | Disabled states, confirmation gates, clear errors, stale-result invalidation, repeated reruns |
| Browser | Real upload, downloads, reset, separate sessions, navigation during running jobs |
| Security | Wrong file structure, hostile labels, path traversal, oversized input, formula injection, cross-session leakage |
| Reliability | Cancellation, timeout, worker crash, stale job completion, disk-full, abandoned workspace cleanup |
| Performance | Cold/warm timings, peak process-tree memory, scratch use, concurrent-job behavior |

## Repository Structure (planned, from blueprint)

```
CleanSheet/
  app.py
  pyproject.toml
  uv.lock
  README.md
  LICENSE
  Dockerfile
  .streamlit/config.toml
  src/CleanSheet/
    config.py, contracts.py, errors.py
    ui/           # start, import_review, preparation, question, results, export
    services/     # ingest, prepare, profile, recommend, statistics, visualize, reports
    engine/       # expressions, execution, sampling
    jobs/         # runner, worker, workspace
    reporting/    # templates, interpretations
    cli.py
  tests/
    unit, statistical, integration, ui, security, performance, fixtures
  examples/
    public-data, recipes
  docs/
    architecture.md, statistical-policy.md, data-handling.md, benchmark-method.md, decisions/
  benchmarks/
  .github/workflows/ci.yml
```

## Do Not Assume

- ❌ Any code exists yet
- ❌ `pyproject.toml` or lockfile exists
- ❌ Tests exist or pass
- ❌ CI/CD is configured
- ❌ The exact stack versions have been tested together (blueprint: "candidate choices, not a claim")
- ❌ Polars 2.0 streaming works for all operations (out-of-core joins/group-bys are planned, not done)
- ❌ Seaborn is pandas-free (it converts Polars → pandas internally)

## When Code Exists: High-Signal Checks

- Run `uv lock` / `pip freeze` to verify exact versions
- Run `pytest tests/` — check for `tests/statistical/` reference-case tests
- Run `python -m streamlit run app.py` — verify it starts
- Check `src/CleanSheet/contracts.py` for Pydantic models matching blueprint typed contracts
- Check `src/CleanSheet/jobs/runner.py` for worker lifecycle, cancellation, scratch cleanup
- Check `src/CleanSheet/engine/execution.py` for Polars lazy → materialization boundaries
- Check `src/CleanSheet/services/statistics.py` for adapter pattern (SciPy/statsmodels behind application-owned interface)