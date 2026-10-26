"""Statistical analysis service with SciPy/statsmodels adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
from scipy import stats
from statsmodels.stats.multitest import multipletests

from CleanSheet.config import get_settings
from CleanSheet.contracts import (
    AnalysisRequest,
    IntervalMethod,
    Method,
    StatisticalResult,
)
from CleanSheet.engine.execution import LazyExecutor
from CleanSheet.errors import EligibilityError
from CleanSheet.jobs.workspace import Workspace


@dataclass
class TestAdapter:
    method: Method
    name: str

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        raise NotImplementedError


class WelchTTestAdapter(TestAdapter):
    """Welch's independent samples t-test."""

    def __init__(self) -> None:
        super().__init__(Method.WELCH_T, "Welch's t-test")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        group_col = request.variables["group"]
        outcome_col = request.variables["outcome"]
        levels = request.group_levels

        if not levels or len(levels) != 2:
            raise EligibilityError("Welch t-test requires exactly two group levels")

        data = df.filter(
            pl.col(group_col).is_in(levels) &
            pl.col(outcome_col).is_not_null() &
            ~pl.col(outcome_col).is_infinite() &
            ~pl.col(outcome_col).is_nan()
        )

        group1 = data.filter(pl.col(group_col) == levels[0])[outcome_col].to_numpy()
        group2 = data.filter(pl.col(group_col) == levels[1])[outcome_col].to_numpy()

        if len(group1) < 2 or len(group2) < 2:
            raise EligibilityError("Each group must have at least 2 observations")

        result = stats.ttest_ind(
            group1, group2,
            equal_var=False,
            alternative=request.alternative.value,
        )

        mean_diff = np.mean(group1) - np.mean(group2)
        se = np.sqrt(np.var(group1, ddof=1)/len(group1) + np.var(group2, ddof=1)/len(group2))
        df_welch = (np.var(group1, ddof=1)/len(group1) + np.var(group2, ddof=1)/len(group2))**2 / (
            (np.var(group1, ddof=1)/len(group1))**2/(len(group1)-1) +
            (np.var(group2, ddof=1)/len(group2))**2/(len(group2)-1)
        )

        from scipy.stats import t
        alpha = 1 - request.confidence_level
        t_crit = t.ppf(1 - alpha/2, df_welch)
        ci_low = mean_diff - t_crit * se
        ci_high = mean_diff + t_crit * se

        pooled_sd = np.sqrt(((len(group1)-1)*np.var(group1, ddof=1) + (len(group2)-1)*np.var(group2, ddof=1)) / (len(group1) + len(group2) - 2))
        cohen_d = mean_diff / pooled_sd if pooled_sd > 0 else 0

        return StatisticalResult(
            method=Method.WELCH_T,
            group_counts={levels[0]: len(group1), levels[1]: len(group2)},
            estimate=float(mean_diff),
            interval=(float(ci_low), float(ci_high)),
            interval_method=IntervalMethod.PARAMETRIC,
            interval_status="computed",
            statistic=float(result.statistic),
            degrees_of_freedom=float(df_welch),
            p_value=float(result.pvalue),
            effect_size=float(cohen_d),
            effect_size_interpretation=_interpret_cohen_d(cohen_d),
            assumption_checks={
                "normality_group1": _check_normality(group1),
                "normality_group2": _check_normality(group2),
                "variance_ratio": float(np.var(group1, ddof=1) / np.var(group2, ddof=1)) if np.var(group2, ddof=1) > 0 else None,
            },
        )


class PairedTTestAdapter(TestAdapter):
    """Paired samples t-test."""

    def __init__(self) -> None:
        super().__init__(Method.PAIRED_T, "Paired t-test")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        pair_col = request.variables["pair_id"]
        outcome_col = request.variables["outcome"]
        occasion_col = request.variables["occasion"]

        wide = df.pivot(
            values=outcome_col,
            index=pair_col,
            columns=occasion_col,
        ).drop_nulls()

        if wide.width < 3:
            raise EligibilityError("Need at least two occasions for paired test")

        occasion_cols = [c for c in wide.columns if c != pair_col]
        if len(occasion_cols) != 2:
            raise EligibilityError("Paired test requires exactly two occasions")

        before = wide[occasion_cols[0]].to_numpy()
        after = wide[occasion_cols[1]].to_numpy()

        if len(before) < 2:
            raise EligibilityError("Need at least 2 complete pairs")

        diff = before - after if request.contrast == "before_minus_after" else after - before

        result = stats.ttest_rel(before, after, alternative=request.alternative.value)

        mean_diff = np.mean(diff)
        se = np.std(diff, ddof=1) / np.sqrt(len(diff))
        df_paired = len(diff) - 1

        from scipy.stats import t
        alpha = 1 - request.confidence_level
        t_crit = t.ppf(1 - alpha/2, df_paired)
        ci_low = mean_diff - t_crit * se
        ci_high = mean_diff + t_crit * se

        cohen_d = mean_diff / np.std(diff, ddof=1) if np.std(diff, ddof=1) > 0 else 0

        return StatisticalResult(
            method=Method.PAIRED_T,
            group_counts={"pairs": len(diff)},
            estimate=float(mean_diff),
            interval=(float(ci_low), float(ci_high)),
            interval_method=IntervalMethod.PARAMETRIC,
            interval_status="computed",
            statistic=float(result.statistic),
            degrees_of_freedom=df_paired,
            p_value=float(result.pvalue),
            effect_size=float(cohen_d),
            effect_size_interpretation=_interpret_cohen_d(cohen_d),
            assumption_checks={
                "normality_differences": _check_normality(diff),
                "n_pairs": len(diff),
            },
        )


class PearsonCorrelationAdapter(TestAdapter):
    """Pearson correlation with confidence interval."""

    def __init__(self) -> None:
        super().__init__(Method.PEARSON_R, "Pearson correlation")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        x_col = request.variables["outcome"]
        y_col = request.variables["predictor"]

        data = df.filter(
            pl.col(x_col).is_not_null() &
            pl.col(y_col).is_not_null() &
            ~pl.col(x_col).is_infinite() &
            ~pl.col(y_col).is_infinite() &
            ~pl.col(x_col).is_nan() &
            ~pl.col(y_col).is_nan()
        )

        x = data[x_col].to_numpy()
        y = data[y_col].to_numpy()

        if len(x) < 3:
            raise EligibilityError("Need at least 3 complete paired observations")

        result = stats.pearsonr(x, y, alternative=request.alternative.value)

        r = result.statistic
        z = np.arctanh(r)
        se = 1 / np.sqrt(len(x) - 3)
        alpha = 1 - request.confidence_level
        z_crit = stats.norm.ppf(1 - alpha/2)
        z_low = z - z_crit * se
        z_high = z + z_crit * se
        ci_low = np.tanh(z_low)
        ci_high = np.tanh(z_high)

        return StatisticalResult(
            method=Method.PEARSON_R,
            group_counts={"n": len(x)},
            estimate=float(r),
            interval=(float(ci_low), float(ci_high)),
            interval_method=IntervalMethod.PARAMETRIC,
            interval_status="computed",
            statistic=float(r),
            degrees_of_freedom=len(x) - 2,
            p_value=float(result.pvalue),
            effect_size=float(r),
            effect_size_interpretation=_interpret_correlation(r),
            assumption_checks={
                "linearity": "Assessed via scatterplot",
                "normality_x": _check_normality(x),
                "normality_y": _check_normality(y),
                "homoscedasticity": "Assessed via residual plot",
            },
        )


class SpearmanCorrelationAdapter(TestAdapter):
    """Spearman rank correlation."""

    def __init__(self) -> None:
        super().__init__(Method.SPEARMAN_RHO, "Spearman rank correlation")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        x_col = request.variables["outcome"]
        y_col = request.variables["predictor"]

        data = df.filter(
            pl.col(x_col).is_not_null() &
            pl.col(y_col).is_not_null()
        )

        x = data[x_col].to_numpy()
        y = data[y_col].to_numpy()

        if len(x) < 3:
            raise EligibilityError("Need at least 3 complete paired observations")

        n = len(x)
        use_permutation = n < 30

        if use_permutation:
            result = stats.spearmanr(x, y, alternative=request.alternative.value)
            n_perm = get_settings().permutation_resamples
            rng = np.random.default_rng(request.seed)
            rho_obs = result.statistic
            rho_perm = []
            for _ in range(n_perm):
                y_perm = rng.permutation(y)
                rho_perm.append(stats.spearmanr(x, y_perm).statistic)
            rho_perm = np.array(rho_perm)

            if request.alternative == "two-sided":
                p_perm = np.mean(np.abs(rho_perm) >= np.abs(rho_obs))
            elif request.alternative == "less":
                p_perm = np.mean(rho_perm <= rho_obs)
            else:
                p_perm = np.mean(rho_perm >= rho_obs)

            p_value = float(p_perm)
            interval_method = IntervalMethod.PERMUTATION
        else:
            result = stats.spearmanr(x, y, alternative=request.alternative.value)
            p_value = float(result.pvalue)
            interval_method = IntervalMethod.NOT_COMPUTED

        ci_low, ci_high = None, None
        if n >= 10:
            try:
                from scipy.stats import bootstrap
                ci = bootstrap(
                    (x, y),
                    lambda x, y: stats.spearmanr(x, y).statistic,
                    confidence_level=request.confidence_level,
                    n_resamples=min(get_settings().bootstrap_resamples, 2000),
                    method="percentile",
                    rng=np.random.default_rng(request.seed),
                )
                ci_low, ci_high = float(ci.confidence_interval.low), float(ci.confidence_interval.high)
                interval_method = IntervalMethod.BOOTSTRAP_PERCENTILE
                interval_status = "computed"
            except Exception:
                interval_method = IntervalMethod.NOT_COMPUTED
                interval_status = "not_computed"
        else:
            interval_method = IntervalMethod.NOT_COMPUTED
            interval_status = "not_computed"

        return StatisticalResult(
            method=Method.SPEARMAN_RHO,
            group_counts={"n": n},
            estimate=float(result.statistic),
            interval=(ci_low, ci_high) if ci_low is not None else None,
            interval_method=interval_method,
            interval_status=interval_status,
            statistic=float(result.statistic),
            degrees_of_freedom=None,
            p_value=p_value,
            effect_size=float(result.statistic),
            effect_size_interpretation=_interpret_correlation(result.statistic),
            assumption_checks={
                "monotonicity": "Assessed via scatterplot",
                "ties_x": int(len(x) - len(np.unique(x))),
                "ties_y": int(len(y) - len(np.unique(y))),
                "permutation_test": use_permutation,
            },
        )


class ChiSquareAdapter(TestAdapter):
    """Chi-square test of independence."""

    def __init__(self) -> None:
        super().__init__(Method.CHI2_INDEPENDENCE, "Chi-square test of independence")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        x_col = request.variables["outcome"]
        y_col = request.variables["group"]

        data = df.select(x_col, y_col).drop_nulls()

        ct = data.group_by(x_col, y_col).len().pivot(
            values="len",
            index=x_col,
            columns=y_col,
        ).fill_null(0)

        row_names = ct[x_col].to_list()
        col_names = [c for c in ct.columns if c != x_col]
        observed = ct.select(col_names).to_numpy().astype(float)

        result = stats.chi2_contingency(observed, correction=False)

        n = observed.sum()
        min_dim = min(observed.shape) - 1
        cramers_v = np.sqrt(result.statistic / (n * min_dim)) if n > 0 and min_dim > 0 else 0

        expected = result.expected_freq

        return StatisticalResult(
            method=Method.CHI2_INDEPENDENCE,
            group_counts={"n": int(n), "rows": observed.shape[0], "cols": observed.shape[1]},
            estimate=float(cramers_v),
            interval=None,
            interval_method=IntervalMethod.NOT_APPLICABLE,
            interval_status="not_applicable",
            statistic=float(result.statistic),
            degrees_of_freedom=int(result.dof),
            p_value=float(result.pvalue),
            effect_size=float(cramers_v),
            effect_size_interpretation=_interpret_cramers_v(cramers_v),
            assumption_checks={
                "expected_counts": expected.tolist(),
                "min_expected": float(expected.min()),
                "cells_below_5": int(np.sum(expected < 5)),
                "row_names": row_names,
                "col_names": col_names,
            },
            exclusions={"dropped_null_rows": len(df) - len(data)},
        )


class FisherExactAdapter(TestAdapter):
    """Fisher's exact test for 2x2 tables."""

    def __init__(self) -> None:
        super().__init__(Method.FISHER_EXACT, "Fisher's exact test")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        x_col = request.variables["outcome"]
        y_col = request.variables["group"]

        data = df.select(x_col, y_col).drop_nulls()

        ct = data.group_by(x_col, y_col).len().pivot(
            values="len",
            index=x_col,
            columns=y_col,
        ).fill_null(0)

        row_names = ct[x_col].to_list()
        col_names = [c for c in ct.columns if c != x_col]
        observed = ct.select(col_names).to_numpy().astype(int)

        if observed.shape != (2, 2):
            raise EligibilityError("Fisher's exact test requires a 2x2 table")

        result = stats.fisher_exact(observed, alternative=request.alternative.value)

        odds_ratio = (observed[0, 0] * observed[1, 1]) / (observed[0, 1] * observed[1, 0]) if observed[0, 1] * observed[1, 0] > 0 else np.inf

        return StatisticalResult(
            method=Method.FISHER_EXACT,
            group_counts={"n": int(observed.sum())},
            estimate=float(odds_ratio),
            interval=None,
            interval_method=IntervalMethod.NOT_COMPUTED,
            interval_status="not_computed",
            statistic=float(result.statistic),
            degrees_of_freedom=None,
            p_value=float(result.pvalue),
            effect_size=float(odds_ratio),
            effect_size_interpretation=_interpret_odds_ratio(odds_ratio),
            assumption_checks={
                "table": observed.tolist(),
                "row_names": row_names,
                "col_names": col_names,
                "odds_ratio_convention": "OR = (a*d)/(b*c) where a=row0_col0",
            },
            exclusions={"dropped_null_rows": len(df) - len(data)},
        )


class DescriptiveAdapter(TestAdapter):
    """Descriptive statistics only."""

    def __init__(self) -> None:
        super().__init__(Method.DESCRIPTIVE, "Descriptive statistics")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        return StatisticalResult(
            method=Method.DESCRIPTIVE,
            group_counts={"n_rows": len(df), "n_columns": len(df.columns)},
            estimate=None,
            interval=None,
            interval_method=IntervalMethod.NOT_APPLICABLE,
            interval_status="not_applicable",
            statistic=None,
            degrees_of_freedom=None,
            p_value=None,
            effect_size=None,
        )


ADAPTERS: dict[Method, TestAdapter] = {
    Method.WELCH_T: WelchTTestAdapter(),
    Method.PAIRED_T: PairedTTestAdapter(),
    Method.PEARSON_R: PearsonCorrelationAdapter(),
    Method.SPEARMAN_RHO: SpearmanCorrelationAdapter(),
    Method.CHI2_INDEPENDENCE: ChiSquareAdapter(),
    Method.FISHER_EXACT: FisherExactAdapter(),
    Method.DESCRIPTIVE: DescriptiveAdapter(),
}


def run_analysis(
    workspace: Workspace,
    dataset_ref: Any,
    request: AnalysisRequest,
) -> StatisticalResult:
    executor = LazyExecutor(workspace, dataset_ref)

    required_cols = list(set(request.variables.values()))
    df = executor.materialize_for_analysis(required_cols)

    method = request.method or _select_method(request.goal)
    adapter = ADAPTERS.get(method)

    if adapter is None:
        raise EligibilityError(f"No adapter for method: {method}")

    result = adapter.run(df, request)

    if request.multiplicity.get("method") != "none" and request.multiplicity.get("family_size", 1) > 1:
        pass

    return result


def _select_method(goal: str) -> Method:
    from CleanSheet.contracts import Goal
    mapping = {
        Goal.COMPARE_TWO_MEANS: Method.WELCH_T,
        Goal.COMPARE_PAIRED_MEANS: Method.PAIRED_T,
        Goal.EXPLORE_LINEAR_RELATIONSHIP: Method.PEARSON_R,
        Goal.EXPLORE_ORDERED_RELATIONSHIP: Method.SPEARMAN_RHO,
        Goal.CATEGORICAL_ASSOCIATION: Method.CHI2_INDEPENDENCE,
        Goal.SPARSE_2X2_TABLE: Method.FISHER_EXACT,
        Goal.DESCRIBE_DATA: Method.DESCRIPTIVE,
    }
    return mapping.get(goal, Method.DESCRIPTIVE)


def adjust_pvalues(
    p_values: list[float],
    method: str = "holm",
    alpha: float = 0.05,
) -> tuple[list[bool], list[float]]:
    reject, p_adj, _, _ = multipletests(p_values, alpha=alpha, method=method)
    return reject.tolist(), p_adj.tolist()


def _interpret_cohen_d(d: float) -> str:
    abs_d = abs(d)
    if abs_d < 0.2:
        return "negligible"
    if abs_d < 0.5:
        return "small"
    if abs_d < 0.8:
        return "medium"
    return "large"


def _interpret_correlation(r: float) -> str:
    abs_r = abs(r)
    if abs_r < 0.1:
        return "negligible"
    if abs_r < 0.3:
        return "small"
    if abs_r < 0.5:
        return "medium"
    return "large"


def _interpret_cramers_v(v: float) -> str:
    if v < 0.1:
        return "negligible"
    if v < 0.3:
        return "small"
    if v < 0.5:
        return "medium"
    return "large"


def _interpret_odds_ratio(or_val: float) -> str:
    if or_val == np.inf or or_val == 0:
        return "infinite/undefined"
    log_or = np.log(or_val)
    abs_log = abs(log_or)
    if abs_log < 0.2:
        return "negligible"
    if abs_log < 0.5:
        return "small"
    if abs_log < 1.0:
        return "medium"
    return "large"


def _check_normality(data: np.ndarray) -> dict[str, Any]:
    if len(data) < 3:
        return {"test": "insufficient_data"}

    try:
        n = min(len(data), 5000)
        sample = np.random.default_rng(42).choice(data, size=n, replace=False)
        stat, p = stats.shapiro(sample)
        return {
            "test": "shapiro_wilk",
            "statistic": float(stat),
            "p_value": float(p),
            "sample_size": n,
        }
    except Exception:
        return {"test": "failed"}
