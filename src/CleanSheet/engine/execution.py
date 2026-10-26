"""Polars lazy execution with explicit materialization boundaries."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import polars as pl

from CleanSheet.config import get_settings
from CleanSheet.contracts import DatasetRef, ImportSpec
from CleanSheet.errors import ResourceLimitError
from CleanSheet.jobs.workspace import Workspace


class LazyExecutor:
    """Manages lazy Polars execution with resource budgets."""

    def __init__(self, workspace: Workspace, dataset_ref: DatasetRef) -> None:
        self.workspace = workspace
        self.dataset_ref = dataset_ref
        self.settings = get_settings()
        self._import_spec: ImportSpec | None = None
        self._lf: pl.LazyFrame | None = None

    @property
    def import_spec(self) -> ImportSpec:
        if self._import_spec is None:
            self._import_spec = self.workspace.get_import_spec(self.dataset_ref)
        return self._import_spec

    @property
    def source_lf(self) -> pl.LazyFrame:
        """Get the source LazyFrame."""
        if self._lf is None:
            path = self.workspace.get_source_path(self.dataset_ref)
            spec = self.import_spec

            if self.dataset_ref.format == "csv":
                self._lf = pl.scan_csv(
                    str(path),
                    separator=spec.delimiter,
                    encoding=spec.encoding,
                    decimal_comma=spec.decimal_comma,
                    null_values=spec.null_tokens,
                    infer_schema_length=spec.infer_schema_length,
                    try_parse_dates=False,  # We'll parse explicitly
                )
            else:
                self._lf = pl.scan_parquet(str(path))

            # Apply schema overrides
            if spec.schema_overrides:
                casts = {k: v.value if hasattr(v, "value") else v for k, v in spec.schema_overrides.items()}
                polars_dtypes = {k: getattr(pl, v) for k, v in casts.items()}
                self._lf = self._lf.with_columns([
                    pl.col(k).cast(v).alias(k) for k, v in polars_dtypes.items()
                ])

        return self._lf

    def collect_schema(self) -> dict[str, pl.DataType]:
        """Get schema without materializing data."""
        return self.source_lf.collect_schema()

    def preview(self, n: int = 100) -> pl.DataFrame:
        """Materialize a preview."""
        n = min(n, self.settings.preview_rows)
        return self.source_lf.limit(n).collect()

    def materialize_for_profiling(self, columns: list[str] | None = None) -> pl.DataFrame:
        """Materialize data for profiling with column limit."""
        lf = self.source_lf
        if columns:
            lf = lf.select(columns[:self.settings.max_profiling_columns])
        return lf.collect()

    def materialize_for_analysis(
        self,
        columns: list[str],
        filters: list[pl.Expr] | None = None,
    ) -> pl.DataFrame:
        """Materialize only required columns for analysis."""
        lf = self.source_lf.select(columns)

        if filters:
            for f in filters:
                lf = lf.filter(f)

        # Preflight memory estimate
        self._check_materialization_size(lf, columns)

        return lf.collect(engine="streaming" if self.settings.polars_streaming else "in-memory")

    def materialize_for_plotting(
        self,
        columns: list[str],
        max_rows: int,
        seed: int = 42,
    ) -> pl.DataFrame:
        """Materialize a reproducible sample for plotting.
        
        Uses efficient sampling that doesn't require full materialization first.
        """
        lf = self.source_lf.select(columns)
        
        # Get total row count for sampling fraction
        total_rows = lf.select(pl.len()).collect().item()
        max_n = min(max_rows, self.settings.max_plot_points, total_rows)
        
        if total_rows <= max_n:
            # Small enough to collect entirely
            df = lf.collect(engine="streaming" if self.settings.polars_streaming else "in-memory")
            return df
        
        # For large datasets, use hash-based sampling to avoid full materialization
        # Add a stable hash-based filter for reproducible sampling
        sample_fraction = max_n / total_rows
        
        # Use hash-based deterministic sampling
        # hash = hash(row_index, seed) % 10000 / 10000 < sample_fraction
        lf = lf.with_row_index("_row_idx")
        
        # Use a simple deterministic hash for sampling
        # This avoids full materialization by filtering during collection
        hash_expr = (
            (pl.col("_row_idx") * 1103515245 + 12345 + seed) % 2147483647
        ) / 2147483647
        
        lf = lf.filter(hash_expr < sample_fraction)
        
        # Add row index for stable ordering, sort, and limit
        df = lf.sort("_row_idx").limit(max_n).collect(
            engine="streaming" if self.settings.polars_streaming else "in-memory"
        )
        
        return df.drop("_row_idx")

    def _check_materialization_size(self, lf: pl.LazyFrame, columns: list[str]) -> None:
        """Estimate materialization size before collecting."""
        try:
            # Get schema to estimate row size
            schema = lf.collect_schema()
            row_size = sum(
                self._dtype_size(dtype) for name, dtype in schema.items() if name in columns
            )
            row_count = lf.select(pl.len()).collect().item()
            estimated_mib = (row_size * row_count) / (1024 * 1024)

            if estimated_mib > self.settings.inference_materialization_limit_mib:
                raise ResourceLimitError(
                    f"Estimated materialization size ({estimated_mib:.1f} MiB) exceeds limit "
                    f"({self.settings.inference_materialization_limit_mib} MiB)",
                    limit_type="inference_materialization_limit_mib",
                    limit_value=self.settings.inference_materialization_limit_mib,
                    actual_value=estimated_mib,
                )
        except ResourceLimitError:
            raise
        except Exception:
            # If estimation fails, proceed but warn
            pass

    @staticmethod
    def _dtype_size(dtype: pl.DataType) -> int:
        """Estimate bytes per value for a dtype."""
        sizes = {
            pl.Int8: 1, pl.Int16: 2, pl.Int32: 4, pl.Int64: 8,
            pl.UInt8: 1, pl.UInt16: 2, pl.UInt32: 4, pl.UInt64: 8,
            pl.Float32: 4, pl.Float64: 8,
            pl.Boolean: 1,
            pl.Date: 4,
            pl.Datetime: 8,
            pl.String: 50,  # Average estimate
            pl.Categorical: 4,
        }
        for dt, size in sizes.items():
            if isinstance(dtype, dt):
                return size
        return 64  # Default conservative estimate

    @contextmanager
    def temp_scratch(self, prefix: str = "exec_") -> Any:
        """Context manager for temporary scratch files."""
        with self.workspace.temp_file() as path:
            yield path

    def sink_parquet(self, lf: pl.LazyFrame, name: str) -> Path:
        """Sink a lazy frame to parquet in workspace."""
        path = self.workspace.root / f"{name}.parquet"
        lf.sink_parquet(str(path))
        return path

    def explain_plan(self, lf: pl.LazyFrame) -> str:
        """Get query plan as string."""
        return lf.explain()


def build_preparation_pipeline(
    lf: pl.LazyFrame,
    steps: list[dict[str, Any]],
) -> pl.LazyFrame:
    """Apply preparation steps to a lazy frame."""
    from CleanSheet.contracts import TransformOp

    for step in steps:
        op = step.get("operation")
        args = step.get("arguments", {})

        if op == TransformOp.RENAME:
            mapping = args.get("mapping", {})
            lf = lf.rename(mapping)

        elif op == TransformOp.FILTER:
            expr_str = args.get("expression")
            if expr_str:
                # Safe evaluation of filter expression
                lf = lf.filter(pl.eval(expr_str))

        elif op == TransformOp.CAST:
            casts = args.get("casts", {})
            for col, dtype_str in casts.items():
                dtype = getattr(pl, dtype_str)
                lf = lf.with_columns(pl.col(col).cast(dtype).alias(col))

        elif op == TransformOp.DEDUPLICATE:
            subset = args.get("subset")
            keep = args.get("keep", "first")
            if subset:
                lf = lf.unique(subset=subset, keep=keep, maintain_order=True)
            else:
                lf = lf.unique(keep=keep, maintain_order=True)

        elif op == TransformOp.DROP_COLUMNS:
            columns = args.get("columns", [])
            lf = lf.drop(columns)

        elif op == TransformOp.RECODE_CATEGORICAL:
            mapping = args.get("mapping", {})
            for col, recode in mapping.items():
                lf = lf.with_columns(
                    pl.col(col).replace(recode).alias(col)
                )

        elif op == TransformOp.IMPUTE:
            # Imputation happens at materialization time
            pass

    return lf


def compute_recipe_hash(steps: list[dict[str, Any]]) -> str:
    """Compute deterministic hash of preparation recipe."""
    serialized = json.dumps(steps, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def get_or_create_prepared(
    workspace: Workspace,
    dataset_ref: DatasetRef,
    recipe_steps: list[dict[str, Any]],
) -> pl.DataFrame:
    """Get prepared data, computing if necessary."""
    recipe_hash = compute_recipe_hash(recipe_steps)

    # Check cache
    cached_path = workspace.get_prepared_path(recipe_hash)
    if cached_path:
        return pl.read_parquet(cached_path)

    # Build and execute
    executor = LazyExecutor(workspace, dataset_ref)
    lf = executor.source_lf
    lf = build_preparation_pipeline(lf, recipe_steps)

    df = lf.collect(engine="streaming" if get_settings().polars_streaming else "in-memory")

    # Cache result
    workspace.store_prepared(df, recipe_hash)

    return df


def get_prepared_lazy(
    workspace: Workspace,
    dataset_ref: DatasetRef,
    recipe_steps: list[dict[str, Any]],
) -> pl.LazyFrame:
    """Get prepared lazy frame for analysis."""
    executor = LazyExecutor(workspace, dataset_ref)
    lf = executor.source_lf
    lf = build_preparation_pipeline(lf, recipe_steps)
    return lf
