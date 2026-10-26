"""Polars expression builders and utilities."""

from __future__ import annotations

import polars as pl
from polars.selectors import categorical, date, datetime, float, integer, string


def strip_strings(*cols: str) -> list[pl.Expr]:
    """Strip whitespace from string columns."""
    return [pl.col(c).str.strip_chars().alias(c) for c in cols]


def to_lowercase(*cols: str) -> list[pl.Expr]:
    """Convert string columns to lowercase."""
    return [pl.col(c).str.to_lowercase().alias(c) for c in cols]


def parse_dates(
    cols: list[str],
    format: str | None = None,
    strict: bool = True,
) -> list[pl.Expr]:
    """Parse string columns as dates."""
    exprs = []
    for c in cols:
        if format:
            exprs.append(pl.col(c).str.to_date(format=format, strict=strict).alias(c))
        else:
            exprs.append(pl.col(c).str.to_date(strict=strict).alias(c))
    return exprs


def parse_datetimes(
    cols: list[str],
    format: str | None = None,
    time_zone: str | None = None,
    strict: bool = True,
) -> list[pl.Expr]:
    """Parse string columns as datetimes."""
    exprs = []
    for c in cols:
        if format:
            exprs.append(pl.col(c).str.to_datetime(format=format, time_zone=time_zone, strict=strict).alias(c))
        else:
            exprs.append(pl.col(c).str.to_datetime(time_zone=time_zone, strict=strict).alias(c))
    return exprs


def cast_columns(casts: dict[str, pl.DataType]) -> list[pl.Expr]:
    """Cast columns to specified types."""
    return [pl.col(name).cast(dtype).alias(name) for name, dtype in casts.items()]


def fill_nulls(fills: dict[str, Any], strategy: str | None = None) -> list[pl.Expr]:
    """Fill null values."""
    exprs = []
    for col, value in fills.items():
        if strategy == "forward":
            exprs.append(pl.col(col).fill_null(strategy="forward").alias(col))
        elif strategy == "backward":
            exprs.append(pl.col(col).fill_null(strategy="backward").alias(col))
        elif strategy == "mean":
            exprs.append(pl.col(col).fill_null(pl.col(col).mean()).alias(col))
        elif strategy == "median":
            exprs.append(pl.col(col).fill_null(pl.col(col).median()).alias(col))
        else:
            exprs.append(pl.col(col).fill_null(value).alias(col))
    return exprs


def replace_nan_with_null(*cols: str) -> list[pl.Expr]:
    """Replace NaN with null in float columns."""
    return [pl.col(c).fill_nan(None).alias(c) for c in cols]


def compute_revenue(qty_col: str, price_col: str, output_col: str = "revenue") -> pl.Expr:
    """Compute revenue as quantity * price."""
    return (pl.col(qty_col) * pl.col(price_col)).alias(output_col)


def compute_pct_change(col: str, output_col: str | None = None) -> pl.Expr:
    """Compute percentage change."""
    out = output_col or f"{col}_pct_change"
    return pl.col(col).pct_change().alias(out)


def rank_column(
    col: str,
    output_col: str | None = None,
    method: str = "average",
    descending: bool = False,
) -> pl.Expr:
    """Rank values in a column."""
    out = output_col or f"{col}_rank"
    return pl.col(col).rank(method=method, descending=descending).alias(out)


def quantile_bins(
    col: str,
    n_bins: int,
    output_col: str | None = None,
    labels: list[str] | None = None,
) -> pl.Expr:
    """Create quantile-based bins."""
    out = output_col or f"{col}_qbin"
    expr = pl.col(col).qcut(n_bins, labels=labels)
    return expr.alias(out)


def equal_width_bins(
    col: str,
    n_bins: int,
    output_col: str | None = None,
    labels: list[str] | None = None,
) -> pl.Expr:
    """Create equal-width bins."""
    out = output_col or f"{col}_bin"
    expr = pl.col(col).cut(n_bins, labels=labels)
    return expr.alias(out)


def log_transform(col: str, output_col: str | None = None, base: float = 10.0) -> pl.Expr:
    """Apply log transformation."""
    out = output_col or f"{col}_log"
    if base == 10.0:
        return pl.col(col).log10().alias(out)
    if base == 2.718281828459045:
        return pl.col(col).log().alias(out)
    return (pl.col(col).log() / pl.lit(base).log()).alias(out)


def zscore(col: str, output_col: str | None = None) -> pl.Expr:
    """Compute z-score."""
    out = output_col or f"{col}_z"
    return ((pl.col(col) - pl.col(col).mean()) / pl.col(col).std()).alias(out)


def winsorize(col: str, lower: float = 0.01, upper: float = 0.99, output_col: str | None = None) -> pl.Expr:
    """Winsorize at given quantiles."""
    out = output_col or f"{col}_winsor"
    lower_val = pl.col(col).quantile(lower)
    upper_val = pl.col(col).quantile(upper)
    return pl.col(col).clip(lower_val, upper_val).alias(out)


def create_interaction(col1: str, col2: str, output_col: str | None = None) -> pl.Expr:
    """Create interaction term for two categorical columns."""
    out = output_col or f"{col1}_x_{col2}"
    return (pl.col(col1).cast(pl.String) + "_" + pl.col(col2).cast(pl.String)).alias(out)


def case_when(
    conditions: list[tuple[pl.Expr, Any]],
    default: Any,
    output_col: str,
) -> pl.Expr:
    """Build a when-then-otherwise expression."""
    expr = pl.when(conditions[0][0]).then(conditions[0][1])
    for cond, val in conditions[1:]:
        expr = expr.when(cond).then(val)
    return expr.otherwise(default).alias(output_col)


def filter_expression(filters: dict[str, Any]) -> pl.Expr:
    """Build a filter expression from a dict of column -> value(s)."""
    exprs = []
    for col, value in filters.items():
        if isinstance(value, (list, tuple, set)):
            exprs.append(pl.col(col).is_in(value))
        elif isinstance(value, dict):
            # Range filter: {"min": 0, "max": 100}
            if "min" in value:
                exprs.append(pl.col(col) >= value["min"])
            if "max" in value:
                exprs.append(pl.col(col) <= value["max"])
        else:
            exprs.append(pl.col(col) == value)

    if not exprs:
        return pl.lit(True)

    combined = exprs[0]
    for e in exprs[1:]:
        combined = combined & e
    return combined


def aggregate_exprs(
    group_by: list[str],
    metrics: dict[str, list[str]],
) -> list[pl.Expr]:
    """Build aggregation expressions."""
    exprs = []
    for col, funcs in metrics.items():
        for func in funcs:
            if func == "count":
                exprs.append(pl.len().alias(f"{col}_count"))
            elif func == "n_unique":
                exprs.append(pl.col(col).n_unique().alias(f"{col}_n_unique"))
            elif func == "sum":
                exprs.append(pl.col(col).sum().alias(f"{col}_sum"))
            elif func == "mean":
                exprs.append(pl.col(col).mean().alias(f"{col}_mean"))
            elif func == "median":
                exprs.append(pl.col(col).median().alias(f"{col}_median"))
            elif func == "std":
                exprs.append(pl.col(col).std().alias(f"{col}_std"))
            elif func == "var":
                exprs.append(pl.col(col).var().alias(f"{col}_var"))
            elif func == "min":
                exprs.append(pl.col(col).min().alias(f"{col}_min"))
            elif func == "max":
                exprs.append(pl.col(col).max().alias(f"{col}_max"))
            elif func == "q1":
                exprs.append(pl.col(col).quantile(0.25).alias(f"{col}_q1"))
            elif func == "q3":
                exprs.append(pl.col(col).quantile(0.75).alias(f"{col}_q3"))
            elif func == "skew":
                exprs.append(pl.col(col).skew().alias(f"{col}_skew"))
            elif func == "kurtosis":
                exprs.append(pl.col(col).kurtosis().alias(f"{col}_kurtosis"))
    return exprs


def selector_by_role(role: str) -> pl.Selector:
    """Get Polars selector for a semantic role."""
    selectors = {
        "continuous": float() | integer(),
        "categorical": categorical() | string(),
        "ordinal": categorical() | string(),
        "date": date(),
        "datetime": datetime(),
        "identifier": string(),
        "free_text": string(),
    }
    return selectors.get(role, string())


def validate_numeric_for_analysis(df: pl.DataFrame, cols: list[str]) -> dict[str, list[str]]:
    """Validate numeric columns for analysis."""
    issues = {"non_finite": [], "constant": [], "all_null": []}

    for col in cols:
        if col not in df.columns:
            continue

        s = df[col]

        # Check for non-finite
        if s.dtype.is_numeric():
            non_finite = s.filter(pl.col(col).is_infinite() | pl.col(col).is_nan())
            if len(non_finite) > 0:
                issues["non_finite"].append(f"{col}: {len(non_finite)} non-finite values")

            # Check for constant
            if s.n_unique() <= 1:
                issues["constant"].append(col)

            # Check for all null
            if s.null_count() == len(s):
                issues["all_null"].append(col)

    return {k: v for k, v in issues.items() if v}
