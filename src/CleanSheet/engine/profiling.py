"""Optimized single-pass profiling and progressive discovery utilities."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

from CleanSheet.config import get_settings
from CleanSheet.contracts import (
    ColumnRole,
    DatasetRef,
    SemanticRole,
)
from CleanSheet.engine.discovery import DiscoveryConfig
from CleanSheet.engine.execution import (
    LazyExecutor,
)
from CleanSheet.jobs.workspace import Workspace


@dataclass
class ProfilingResult:
    """Result of single-pass profiling."""

    n_rows: int
    n_columns: int
    column_stats: list[dict[str, Any]]
    quality_issues: dict[str, Any]
    memory_estimate_mib: float
    profiling_time_ms: float
    schema: dict[str, pl.DataType]


def build_single_pass_profiling_exprs(
    columns: list[str],
    column_roles: dict[str, SemanticRole],
) -> list[pl.Expr]:
    """Build Polars expressions for single-pass profiling of multiple columns.
    
    Returns a list of expressions that compute all statistics in one pass.
    """
    exprs = []

    for col in columns:
        role = column_roles.get(col, SemanticRole.FREE_TEXT)

        # Basic stats for all columns
        exprs.extend([
            pl.col(col).null_count().alias(f"{col}__null_count"),
            pl.col(col).n_unique().alias(f"{col}__n_unique"),
            pl.len().alias(f"{col}__n_rows"),
        ])

        if role in (SemanticRole.CONTINUOUS, SemanticRole.DISCRETE, SemanticRole.ORDINAL):
            # Numeric statistics
            exprs.extend([
                pl.col(col).mean().alias(f"{col}__mean"),
                pl.col(col).std().alias(f"{col}__std"),
                pl.col(col).median().alias(f"{col}__median"),
                pl.col(col).quantile(0.25).alias(f"{col}__q1"),
                pl.col(col).quantile(0.75).alias(f"{col}__q3"),
                pl.col(col).min().alias(f"{col}__min"),
                pl.col(col).max().alias(f"{col}__max"),
                pl.col(col).skew().alias(f"{col}__skew"),
                pl.col(col).kurtosis().alias(f"{col}__kurtosis"),
            ])

            # NaN/Inf counts for floats
            exprs.extend([
                pl.col(col).is_nan().sum().alias(f"{col}__n_nan"),
                pl.col(col).is_infinite().sum().alias(f"{col}__n_inf"),
            ])

        elif role in (SemanticRole.NOMINAL, SemanticRole.ORDINAL, SemanticRole.BINARY):
            # Categorical - top categories (approximate for performance)
            # Note: value_counts in lazy is tricky, we'll do this separately if needed
            pass

        elif role in (SemanticRole.DATE, SemanticRole.DATETIME):
            exprs.extend([
                pl.col(col).min().alias(f"{col}__min_date"),
                pl.col(col).max().alias(f"{col}__max_date"),
            ])

    return exprs


def run_single_pass_profiling(
    workspace: Workspace,
    dataset_ref: DatasetRef,
    column_roles: list[ColumnRole],
    recipe_steps: list[dict[str, Any]] | None = None,
) -> ProfilingResult:
    """Run single-pass profiling using Polars lazy execution.
    
    Computes all column statistics in a single query execution,
    dramatically faster than per-column profiling.
    """
    settings = get_settings()
    start_time = time.perf_counter()

    executor = LazyExecutor(workspace, dataset_ref)

    # Build the lazy frame with preparation pipeline
    if recipe_steps:
        from CleanSheet.engine.execution import build_preparation_pipeline
        lf = executor.source_lf
        lf = build_preparation_pipeline(lf, recipe_steps)
    else:
        lf = executor.source_lf

    # Get columns to profile (limit for performance)
    role_dict = {cr.column: cr.semantic_role for cr in column_roles}
    cols_to_profile = list(role_dict.keys())[:settings.max_profiling_columns]

    # Select only needed columns
    lf = lf.select(cols_to_profile)

    # Build single-pass expressions
    exprs = build_single_pass_profiling_exprs(cols_to_profile, role_dict)

    # Execute single query
    result_df = lf.select(exprs).collect(engine="streaming" if settings.polars_streaming else "in-memory")

    # Parse results into column stats
    column_stats = []
    for col in cols_to_profile:
        role = role_dict[col]
        row = result_df.row(0, named=True)

        n_rows = row[f"{col}__n_rows"]
        n_null = row[f"{col}__null_count"]
        n_unique = row[f"{col}__n_unique"]
        null_pct = (n_null / n_rows * 100) if n_rows > 0 else 0
        is_constant = n_unique <= 1

        stat = {
            "name": col,
            "physical_dtype": str(result_df[col].dtype) if col in result_df.columns else "unknown",
            "semantic_role": role.value,
            "n_rows": n_rows,
            "n_null": n_null,
            "n_unique": n_unique,
            "null_pct": round(null_pct, 2),
            "is_constant": is_constant,
        }

        if role in (SemanticRole.CONTINUOUS, SemanticRole.DISCRETE, SemanticRole.ORDINAL):
            stat.update({
                "mean": row.get(f"{col}__mean"),
                "std": row.get(f"{col}__std"),
                "median": row.get(f"{col}__median"),
                "q1": row.get(f"{col}__q1"),
                "q3": row.get(f"{col}__q3"),
                "min": row.get(f"{col}__min"),
                "max": row.get(f"{col}__max"),
                "skew": row.get(f"{col}__skew"),
                "kurtosis": row.get(f"{col}__kurtosis"),
                "n_nan": row.get(f"{col}__n_nan", 0),
                "n_inf": row.get(f"{col}__n_inf", 0),
            })
        elif role in (SemanticRole.DATE, SemanticRole.DATETIME):
            stat.update({
                "min_date": str(row.get(f"{col}__min_date")) if row.get(f"{col}__min_date") else None,
                "max_date": str(row.get(f"{col}__max_date")) if row.get(f"{col}__max_date") else None,
            })

        # Add quality flags
        flags = []
        if null_pct > 50:
            flags.append("high_missingness")
        elif null_pct > 10:
            flags.append("moderate_missingness")
        if is_constant:
            flags.append("constant")
        if stat.get("n_inf", 0) > 0:
            flags.append("has_infinite")
        if stat.get("n_nan", 0) > 0:
            flags.append("has_nan")
        if role in (SemanticRole.NOMINAL, SemanticRole.ORDINAL, SemanticRole.BINARY) and n_unique > 100:
            flags.append("high_cardinality")
        stat["quality_flags"] = ", ".join(flags) if flags else "ok"

        column_stats.append(stat)

    # Quality issues (from basic stats)
    quality_issues = _compute_quality_issues(column_stats, result_df)

    # Memory estimate
    schema = lf.collect_schema()
    row_size = sum(_estimate_dtype_size(dtype) for dtype in schema.values())
    row_count = n_rows
    memory_mib = (row_size * row_count) / (1024 * 1024)

    profiling_time_ms = (time.perf_counter() - start_time) * 1000

    return ProfilingResult(
        n_rows=n_rows,
        n_columns=len(cols_to_profile),
        column_stats=column_stats,
        quality_issues=quality_issues,
        memory_estimate_mib=memory_mib,
        profiling_time_ms=profiling_time_ms,
        schema={k: str(v) for k, v in schema.items()},
    )


def _compute_quality_issues(column_stats: list[dict], result_df: pl.DataFrame) -> dict[str, Any]:
    """Compute quality issues from profiling results."""
    issues = {
        "duplicates": [],
        "constant_columns": [],
        "high_cardinality": [],
        "missingness": [],
        "numeric_issues": [],
        "date_issues": [],
    }

    for stat in column_stats:
        # Missingness
        if stat["n_null"] > 0:
            issues["missingness"].append({
                "column": stat["name"],
                "null_count": stat["n_null"],
                "null_pct": stat["null_pct"],
                "severity": "high" if stat["null_pct"] > 50 else "medium" if stat["null_pct"] > 10 else "low",
            })

        # Constant columns
        if stat["is_constant"]:
            issues["constant_columns"].append(stat["name"])

        # High cardinality
        if stat["semantic_role"] in ("nominal", "ordinal", "binary") and stat["n_unique"] > 50:
            issues["high_cardinality"].append({
                "column": stat["name"],
                "unique_count": stat["n_unique"],
                "note": "Possible identifier column",
            })

        # Numeric issues
        if stat.get("n_inf", 0) > 0:
            issues["numeric_issues"].append({
                "column": stat["name"],
                "issue": "Infinite values",
                "count": stat["n_inf"],
            })
        if stat.get("n_nan", 0) > 0:
            issues["numeric_issues"].append({
                "column": stat["name"],
                "issue": "NaN values",
                "count": stat["n_nan"],
            })

    return issues


def _estimate_dtype_size(dtype: pl.DataType) -> int:
    """Estimate bytes per value for a dtype."""
    sizes = {
        pl.Int8: 1, pl.Int16: 2, pl.Int32: 4, pl.Int64: 8,
        pl.UInt8: 1, pl.UInt16: 2, pl.UInt32: 4, pl.UInt64: 8,
        pl.Float32: 4, pl.Float64: 8,
        pl.Boolean: 1,
        pl.Date: 4,
        pl.Datetime: 8,
        pl.String: 50,
        pl.Categorical: 4,
    }
    for dt, size in sizes.items():
        if isinstance(dtype, dt):
            return size
    return 64


@dataclass
class ProgressCallback:
    """Callback for reporting progress during long operations."""

    on_progress: Callable[[int, int, str], None]  # current, total, message
    on_complete: Callable[[Any], None] = None
    on_error: Callable[[Exception], None] = None


def run_progressive_discovery(
    workspace: Workspace,
    dataset_ref: DatasetRef,
    column_roles: list[ColumnRole],
    recipe_steps: list[dict[str, Any]] | None = None,
    target_column: str | None = None,
    progress_callback: ProgressCallback | None = None,
    cancellation_token: Callable[[], bool] | None = None,
) -> list[dict]:
    """Run discovery with progress reporting and cancellation support.
    
    Yields intermediate results and checks cancellation token between steps.
    
    This is a simplified version that uses the existing DiscoveryEngine
    but adds progress reporting and cancellation support.
    """
    from CleanSheet.engine.discovery import DiscoveryEngine

    config = DiscoveryConfig()
    engine = DiscoveryEngine(
        workspace=workspace,
        dataset_ref=dataset_ref,
        column_roles=column_roles,
        recipe_steps=recipe_steps,
        target_column=target_column,
        config=config,
    )

    # Override run_discovery to support progress/cancellation
    def _report(step: int, total: int, msg: str):
        if progress_callback:
            progress_callback.on_progress(step, total, msg)

    def _check_cancel() -> bool:
        if cancellation_token and cancellation_token():
            raise KeyboardInterrupt("Discovery cancelled by user")
        return False

    _report(1, 9, "Generating candidate questions...")
    _check_cancel()

    candidates = engine._generate_candidates()

    if not candidates:
        if progress_callback and progress_callback.on_complete:
            progress_callback.on_complete([])
        return []

    _report(2, 9, f"Checking eligibility for {len(candidates)} candidates...")
    _check_cancel()

    # Process candidates in batches with progress
    batch_size = 10
    eligible_candidates = []

    for i in range(0, len(candidates), batch_size):
        _check_cancel()
        batch = candidates[i:i+batch_size]
        batch = engine._check_eligibility_and_assumptions(batch)
        eligible_candidates.extend([c for c in batch if c.eligibility and c.eligibility.allowed])

        progress = 2 + int(3 * (i + len(batch)) / len(candidates))
        _report(progress, 9, f"Eligibility: {len(eligible_candidates)}/{len(candidates)} passed")

    candidates = eligible_candidates
    if not candidates:
        if progress_callback and progress_callback.on_complete:
            progress_callback.on_complete([])
        return []

    # Limit to max candidates for performance
    if len(candidates) > engine.config.max_candidates:
        candidates = candidates[:engine.config.max_candidates]

    _report(5, 9, f"Running analyses for {len(candidates)} candidates...")
    _check_cancel()

    # Run analyses with progress - reuse the materialized DataFrame from engine
    df = engine.df  # Reuse materialized data

    analyzed = []
    for i, cand in enumerate(candidates):
        _check_cancel()
        request = _build_analysis_request(cand, engine)
        try:
            from CleanSheet.services.statistics import run_analysis
            # Use the pre-materialized data by passing it through recipe
            result = run_analysis(engine.ws, engine.dataset_ref, request, engine.recipe_steps, engine.column_roles_list)
            if result.statistical_results:
                stat = result.statistical_results[0]
                cand.raw_p_value = stat.p_value
                cand.effect_size = stat.effect_size
                cand.effect_magnitude = abs(stat.effect_size) if stat.effect_size else None
            analyzed.append(cand)
        except Exception:
            pass  # Skip failed analyses

        if i % 5 == 0:
            _report(5 + int(2 * i / len(candidates)), 9, f"Analyzed {i+1}/{len(candidates)}")

    _check_cancel()
    _report(7, 9, "Applying FDR correction...")

    # BH-FDR
    valid = [c for c in analyzed if c.raw_p_value is not None]
    if valid:
        p_values = [c.raw_p_value for c in valid]
        m = len(p_values)
        sorted_indices = np.argsort(p_values)
        sorted_p = np.array(p_values)[sorted_indices]

        q_values = np.zeros(m)
        for i, idx in enumerate(sorted_indices):
            q = sorted_p[i] * m / (i + 1)
            q_values[idx] = min(q, 1.0)
        for i in range(m - 2, -1, -1):
            q_values[i] = min(q_values[i], q_values[i + 1])

        for i, cand in enumerate(valid):
            cand.q_value = float(q_values[i])

    _check_cancel()
    _report(8, 9, "Filtering and ranking...")

    # Filter
    filtered = [c for c in candidates if c.q_value is not None and c.q_value < 0.05 and (c.effect_magnitude or 0) >= 0.1]

    _check_cancel()
    _report(9, 9, "Ranking and pruning redundancy...")

    # Rank
    for cand in filtered:
        cand.composite_score = engine._compute_composite_score(cand)
    filtered.sort(key=lambda c: c.composite_score or 0, reverse=True)

    # Prune redundancy
    final = []
    for cand in filtered:
        if not any(engine._are_redundant(cand, kept) for kept in final):
            final.append(cand)

    _report(9, 9, f"Complete: {len(final)} findings")

    if progress_callback and progress_callback.on_complete:
        progress_callback.on_complete(final)

    return final


def _build_analysis_request(cand, engine) -> AnalysisRequest:
    from CleanSheet.contracts import (
        Alternative,
        AnalysisRequest,
        MissingPolicy,
        NonFinitePolicy,
        StudyDesign,
    )
    from CleanSheet.services.statistics import _select_method

    return AnalysisRequest(
        goal=cand.goal,
        variables=cand.variables,
        group_levels=None,
        study_design=StudyDesign.INDEPENDENT,
        design_confirmation_source="inferred",
        estimand=cand.question,
        missing_policy=MissingPolicy.REQUIRED_COLUMNS_COMPLETE_CASES,
        nonfinite_policy=NonFinitePolicy.EXCLUDE_AND_REPORT,
        method=cand.eligibility.suggested_method if cand.eligibility else _select_method(cand.goal),
        alternative=Alternative.TWO_SIDED,
        confidence_level=0.95,
        seed=42,
    )
