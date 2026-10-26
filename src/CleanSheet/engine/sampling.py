"""Reproducible sampling utilities."""

from __future__ import annotations

import hashlib

import polars as pl


def stable_sample(
    df: pl.DataFrame,
    n: int,
    seed: int = 42,
    key_column: str | None = None,
) -> pl.DataFrame:
    """Take a stable, reproducible sample.

    If key_column is provided, sample by unique key values.
    Otherwise, sample rows directly with stable ordering.
    """
    if len(df) <= n:
        return df

    if key_column and key_column in df.columns:
        # Sample unique keys, then join back
        keys = df.select(key_column).unique()
        sampled_keys = keys.sample(n=min(n, len(keys)), seed=seed, with_replacement=False)
        return df.join(sampled_keys, on=key_column, how="inner")
    # Add stable row index if not present
    if "_sample_idx" not in df.columns:
        df = df.with_row_index("_sample_idx")

    # Sort by index for stability, then sample
    df = df.sort("_sample_idx")
    return df.sample(n=n, seed=seed, with_replacement=False).drop("_sample_idx")


def stratified_sample(
    df: pl.DataFrame,
    strata_column: str,
    n_per_stratum: int | dict[str, int],
    seed: int = 42,
) -> pl.DataFrame:
    """Take a stratified sample."""
    if isinstance(n_per_stratum, int):
        # Same n for all strata
        return df.group_by(strata_column).map_groups(
            lambda g: g.sample(n=min(n_per_stratum, len(g)), seed=seed, with_replacement=False)
        )
    # Per-stratum n
    results = []
    for stratum, n in n_per_stratum.items():
        stratum_df = df.filter(pl.col(strata_column) == stratum)
        if len(stratum_df) > 0:
            sampled = stratum_df.sample(n=min(n, len(stratum_df)), seed=seed, with_replacement=False)
            results.append(sampled)
    return pl.concat(results) if results else df.slice(0, 0)


def reservoir_sample(
    df: pl.DataFrame,
    n: int,
    seed: int = 42,
) -> pl.DataFrame:
    """Reservoir sampling for streaming (approximate, memory-efficient).

    Note: This materializes the dataframe first. For true streaming,
    use Polars' streaming engine with sink operations.
    """
    return df.sample(n=min(n, len(df)), seed=seed, with_replacement=False)


def systematic_sample(
    df: pl.DataFrame,
    n: int,
    seed: int = 42,
) -> pl.DataFrame:
    """Systematic sampling with random start."""
    if len(df) <= n:
        return df

    # Add row index
    df = df.with_row_index("_sys_idx")

    # Calculate step
    step = len(df) // n
    if step == 0:
        step = 1

    # Random start
    import random
    rng = random.Random(seed)
    start = rng.randint(0, step - 1)

    # Select every step-th row
    indices = list(range(start, len(df), step))[:n]
    return df.filter(pl.col("_sys_idx").is_in(indices)).drop("_sys_idx")


def bootstrap_sample(
    df: pl.DataFrame,
    n: int | None = None,
    seed: int = 42,
) -> pl.DataFrame:
    """Bootstrap sample (with replacement)."""
    n = n or len(df)
    return df.sample(n=n, seed=seed, with_replacement=True)


def permutation_sample(
    df: pl.DataFrame,
    column: str,
    seed: int = 42,
) -> pl.DataFrame:
    """Permute a column's values (for permutation tests)."""
    permuted = df.select(column).sample(fraction=1.0, seed=seed, with_replacement=False)
    return df.drop(column).hstack(permuted.rename({column: f"{column}_permuted"}))


def compute_sample_hash(
    df: pl.DataFrame,
    seed: int,
    method: str,
    n: int,
) -> str:
    """Compute hash of sampling parameters for reproducibility tracking."""
    params = f"{seed}:{method}:{n}:{len(df)}"
    return hashlib.sha256(params.encode()).hexdigest()[:16]


class SamplingPlan:
    """Describes a sampling strategy for reporting."""

    def __init__(
        self,
        method: str,
        n: int,
        seed: int,
        population_size: int,
        strata: str | None = None,
    ) -> None:
        self.method = method
        self.n = n
        self.seed = seed
        self.population_size = population_size
        self.strata = strata
        self.hash = compute_sample_hash(pl.DataFrame({"_n": [population_size]}), seed, method, n)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "sample_size": self.n,
            "population_size": self.population_size,
            "seed": self.seed,
            "strata": self.strata,
            "sample_hash": self.hash,
        }

    def describe(self) -> str:
        if self.method == "stable":
            return f"Stable random sample of {self.n} from {self.population_size} (seed={self.seed})"
        if self.method == "stratified":
            return f"Stratified sample of {self.n} per stratum from {self.population_size} (seed={self.seed})"
        if self.method == "bootstrap":
            return f"Bootstrap sample of {self.n} from {self.population_size} (seed={self.seed})"
        if self.method == "systematic":
            return f"Systematic sample of {self.n} from {self.population_size} (seed={self.seed})"
        return f"Sample: {self.method}, n={self.n}, seed={self.seed}"
