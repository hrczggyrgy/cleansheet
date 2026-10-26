# CleanSheet

No-code statistical analysis with Streamlit, Polars, and seaborn.

## Quick Start

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

## Architecture

```
CleanSheet/
├── app.py                    # Streamlit entry point
├── pyproject.toml            # Package configuration
├── requirements.txt          # Dependencies
├── src/CleanSheet/           # Main package
│   ├── config.py             # Settings & resource budgets
│   ├── contracts.py          # Pydantic models for service boundaries
│   ├── errors.py             # Custom exceptions
│   ├── engine/               # Polars execution layer
│   │   ├── expressions.py    # Expression builders
│   │   ├── execution.py      # Lazy execution with boundaries
│   │   └── sampling.py       # Reproducible sampling
│   ├── jobs/                 # Background job management
│   │   ├── runner.py         # Process pool executor
│   │   └── workspace.py      # Session-isolated file storage
│   ├── services/             # Analytical services
│   │   ├── ingest.py         # File ingestion & validation
│   │   ├── profile.py        # Data profiling
│   │   ├── prepare.py        # Reversible transformations
│   │   ├── recommend.py      # Method recommendation engine
│   │   ├── statistics.py     # Statistical test adapters
│   │   ├── visualize.py      # Bounded plotting (worker-isolated)
│   │   └── reports.py        # Export bundle generation
│   ├── ui/                   # Streamlit UI screens
│   │   ├── start.py          # Upload / demo selection
│   │   ├── import_review.py  # Schema & preview review
│   │   ├── preparation.py    # Transformation recipe builder
│   │   ├── question.py       # Analysis goal & variable selection
│   │   ├── results.py        # Statistical results & plots
│   │   └── export.py         # Download reproducible bundle
│   └── cli.py                # Headless recipe replay
├── tests/                    # Test suite
└── .streamlit/config.toml    # Streamlit configuration
```

## Key Features

- **Polars-first**: Lazy execution, streaming, explicit materialization boundaries
- **Deterministic rules engine**: Versioned eligibility checks, not LLM-based
- **Reproducible**: Every run exports manifest (input hash, recipe, versions, seeds)
- **Worker-isolated plotting**: Matplotlib in separate processes with Agg backend
- **Statistical rigor**: Effect sizes, confidence intervals, assumption checks, multiplicity control

## Supported Analyses

| Goal | Method |
|------|--------|
| Compare two groups | Welch's t-test |
| Compare before/after | Paired t-test |
| Linear relationship | Pearson correlation |
| Ordered relationship | Spearman correlation (permutation for small n) |
| Category association | Chi-square / Fisher's exact |
| Describe data | Comprehensive summaries |

## CLI Usage

```bash
# Profile a dataset
python -m CleanSheet.cli profile data.csv -o output/

# Replay a recipe
python -m CleanSheet.cli replay data.parquet recipe.json -o output/
```

## Configuration

Key settings (via environment variables or `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_UPLOAD_SIZE_MB` | 50 | Max upload size |
| `ANALYSIS_JOB_TIMEOUT_SECONDS` | 30 | Analysis timeout |
| `SESSION_SCRATCH_LIMIT_MIB` | 512 | Per-session disk limit |
| `POLARS_STREAMING` | true | Use streaming engine |

## Note on Polars Version

This environment uses `polars-lts-cpu` (1.33.x) for CPU compatibility. The architecture is designed for Polars 2.0+; update `pyproject.toml` to `polars==2.0.0` when running on AVX2-capable hardware.