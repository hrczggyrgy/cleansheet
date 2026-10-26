"""Data profiling service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import polars as pl

from CleanSheet.config import get_settings
from CleanSheet.contracts import DatasetRef
from CleanSheet.engine.execution import LazyExecutor
from CleanSheet.services.ingest import infer_column_roles, validate_data_quality


@dataclass
class ColumnProfile:
    """Profile for a single column."""

    name: str
    physical_dtype: str
    semantic_role: str
    n_rows: int
    n_null: int
    n_unique: int
    null_pct: float
    is_constant: bool

    # Numeric stats
    mean: float | None = None
    std: float | None = None
    median: float | None = None
    q1: float | None = None
    q3: float | None = None
    min: float | None = None
    max: float | None = None
    skew: float | None = None
    kurtosis: float | None = None
    n_infinite: int = 0
    n_nan: int = 0

    # Categorical stats
    top_categories: list[tuple[str, int]] = field(default_factory=list)
    n_categories: int = 0

    # Date stats
    min_date: str | None = None
    max_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "physical_dtype": self.physical_dtype,
            "semantic_role": self.semantic_role,
            "n_rows": self.n_rows,
            "n_null": self.n_null,
            "n_unique": self.n_unique,
            "null_pct": round(self.null_pct, 2),
            "is_constant": self.is_constant,
            "mean": self.mean,
            "std": self.std,
            "median": self.median,
            "q1": self.q1,
            "q3": self.q3,
            "min": self.min,
            "max": self.max,
            "skew": self.skew,
            "kurtosis": self.kurtosis,
            "n_infinite": self.n_infinite,
            "n_nan": self.n_nan,
            "top_categories": self.top_categories[:10],
            "n_categories": self.n_categories,
            "min_date": self.min_date,
            "max_date": self.max_date,
        }


@dataclass
class ProfileResult:
    """Complete profiling result."""

    dataset_ref: DatasetRef
    n_rows: int
    n_columns: int
    columns: list[ColumnProfile] = field(default_factory=list)
    quality_issues: dict[str, Any] = field(default_factory=dict)
    memory_estimate_mib: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_ref": self.dataset_ref.model_dump(),
            "n_rows": self.n_rows,
            "n_columns": self.n_columns,
            "columns": [c.to_dict() for c in self.columns],
            "quality_issues": self.quality_issues,
            "memory_estimate_mib": round(self.memory_estimate_mib, 2),
        }


def profile_column(s: pl.Series, semantic_role: str) -> ColumnProfile:
    """Profile a single column."""
    name = s.name
    dtype = str(s.dtype)
    n_rows = len(s)
    n_null = s.null_count()
    n_unique = s.n_unique()
    null_pct = (n_null / n_rows * 100) if n_rows > 0 else 0
    is_constant = n_unique <= 1

    prof = ColumnProfile(
        name=name,
        physical_dtype=dtype,
        semantic_role=semantic_role,
        n_rows=n_rows,
        n_null=n_null,
        n_unique=n_unique,
        null_pct=null_pct,
        is_constant=is_constant,
    )

    # Numeric profiling
    if s.dtype.is_numeric():
        prof.mean = float(s.mean()) if n_rows > n_null else None
        prof.std = float(s.std()) if n_rows > n_null + 1 else None
        prof.median = float(s.median()) if n_rows > n_null else None
        prof.q1 = float(s.quantile(0.25)) if n_rows > n_null else None
        prof.q3 = float(s.quantile(0.75)) if n_rows > n_null else None
        prof.min = float(s.min()) if n_rows > n_null else None
        prof.max = float(s.max()) if n_rows > n_null else None
        prof.skew = float(s.skew()) if n_rows > n_null + 2 else None
        prof.kurtosis = float(s.kurtosis()) if n_rows > n_null + 3 else None

        if s.dtype.is_float():
            prof.n_nan = int(s.is_nan().sum())
            prof.n_infinite = int(s.is_infinite().sum())

    # Categorical profiling
    if s.dtype in (pl.String, pl.Categorical) or semantic_role in ("categorical", "identifier"):
        prof.n_categories = n_unique
        # Top categories
        if n_unique > 0 and n_unique <= 1000:  # Limit computation
            vc = s.value_counts(sort=True).head(10)
            prof.top_categories = [
                (str(row[name]), int(row["count"]))
                for row in vc.iter_rows(named=True)
            ]

    # Date profiling
    if s.dtype in (pl.Date, pl.Datetime):
        if n_rows > n_null:
            prof.min_date = str(s.min())
            prof.max_date = str(s.max())

    return prof


def run_profiling(
    workspace: Any,
    dataset_ref: DatasetRef,
    column_roles: dict[str, str] | None = None,
) -> ProfileResult:
    """Run complete data profiling."""
    settings = get_settings()
    executor = LazyExecutor(workspace, dataset_ref)

    # Get column roles if not provided
    if column_roles is None:
        # Materialize preview for role inference
        preview = executor.preview(settings.max_profiling_columns)
        roles_dict = infer_column_roles(preview)
        column_roles = {col: info["semantic_role"] for col, info in roles_dict.items()}

    # Select columns to profile (limit for performance)
    cols_to_profile = list(column_roles.keys())[:settings.max_profiling_columns]

    # Materialize for profiling
    df = executor.materialize_for_profiling(cols_to_profile)

    # Profile each column
    columns = []
    for col in cols_to_profile:
        role = column_roles.get(col, "unknown")
        prof = profile_column(df[col], role)
        columns.append(prof)

    # Quality checks
    quality_issues = validate_data_quality(df)

    # Memory estimate
    memory_estimate = df.estimated_size() / (1024 * 1024)

    return ProfileResult(
        dataset_ref=dataset_ref,
        n_rows=df.height,
        n_columns=len(columns),
        columns=columns,
        quality_issues=quality_issues,
        memory_estimate_mib=memory_estimate,
    )


def generate_data_dictionary(profile: ProfileResult) -> pl.DataFrame:
    """Generate a data dictionary DataFrame from profile."""
    rows = []
    for col in profile.columns:
        rows.append({
            "column_name": col.name,
            "physical_type": col.physical_dtype,
            "semantic_role": col.semantic_role,
            "n_rows": col.n_rows,
            "n_missing": col.n_null,
            "pct_missing": round(col.null_pct, 2),
            "n_unique": col.n_unique,
            "is_constant": col.is_constant,
            "mean": col.mean,
            "std": col.std,
            "median": col.median,
            "q1": col.q1,
            "q3": col.q3,
            "min": col.min,
            "max": col.max,
            "top_categories": str(col.top_categories[:5]),
            "n_categories": col.n_categories,
            "min_date": col.min_date,
            "max_date": col.max_date,
            "quality_flags": _quality_flags(col),
        })
    return pl.DataFrame(rows)


def _quality_flags(col: ColumnProfile) -> str:
    """Generate quality flags for a column."""
    flags = []
    if col.null_pct > 50:
        flags.append("high_missingness")
    elif col.null_pct > 10:
        flags.append("moderate_missingness")
    if col.is_constant:
        flags.append("constant")
    if col.n_infinite > 0:
        flags.append("has_infinite")
    if col.n_nan > 0:
        flags.append("has_nan")
    if col.n_categories > 100:
        flags.append("high_cardinality")
    return ", ".join(flags) if flags else "ok"
