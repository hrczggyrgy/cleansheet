"""Non-parametric statistical test adapters.

Implements Mann-Whitney U, Wilcoxon Signed-Rank, Kruskal-Wallis,
Dunn's post-hoc, and Games-Howell post-hoc tests with effect sizes
and confidence intervals.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
from scipy import stats
from statsmodels.stats.libqsturng import qsturng

try:
    from scipy.stats import bootstrap
    HAS_BOOTSTRAP = True
except ImportError:
    HAS_BOOTSTRAP = False

from CleanSheet.contracts import (
    AnalysisRequest,
    IntervalMethod,
    Method,
    StatisticalResult,
)
from CleanSheet.config import get_settings


def _bootstrap_rank_biserial_ci(
    group_first: np.ndarray,
    group_second: np.ndarray,
    confidence_level: float,
    seed: int,
    n_resamples: int = 2000,
) -> tuple[float, float] | None:
    """Bootstrap CI for rank-biserial correlation."""
    if not HAS_BOOTSTRAP:
        return None
    try:
        from scipy.stats import mannwhitneyu
        rng = np.random.default_rng(seed)
        n1, n2 = len(group_first), len(group_second)
        
        def statistic(x1, x2):
            u = mannwhitneyu(x1, x2, alternative="two-sided", method="asymptotic").statistic
            return (2 * u) / (n1 * n2) - 1
        
        ci = bootstrap(
            (group_first, group_second),
            statistic,
            confidence_level=confidence_level,
            n_resamples=min(n_resamples, 2000),
            method="percentile",
            paired=False,
            rng=rng,
        )
        return float(ci.confidence_interval.low), float(ci.confidence_interval.high)
    except Exception:
        return None


def _bootstrap_matched_rank_biserial_ci(
    diff: np.ndarray,
    confidence_level: float,
    seed: int,
    n_resamples: int = 2000,
) -> tuple[float, float] | None:
    """Bootstrap CI for matched rank-biserial correlation."""
    if not HAS_BOOTSTRAP:
        return None
    try:
        from scipy.stats import wilcoxon
        rng = np.random.default_rng(seed)
        n = len(diff)
        
        def statistic(x):
            try:
                result = wilcoxon(x, alternative="two-sided", method="approx")
                if result.pvalue >= 0.5:
                    return 0.0
                z_stat = stats.norm.ppf(1 - result.pvalue / 2)
                return z_stat / np.sqrt(n)
            except Exception:
                pos = np.sum(x > 0)
                neg = np.sum(x < 0)
                return (pos - neg) / n if n > 0 else 0
        
        ci = bootstrap(
            (diff,),
            statistic,
            confidence_level=confidence_level,
            n_resamples=min(n_resamples, 2000),
            method="percentile",
            rng=rng,
        )
        return float(ci.confidence_interval.low), float(ci.confidence_interval.high)
    except Exception:
        return None


@dataclass
class TestAdapter:
    method: Method
    name: str

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        raise NotImplementedError


class MannWhitneyUAdapter(TestAdapter):
    """Mann-Whitney U test with Hodges-Lehmann estimator and rank-biserial correlation."""

    def __init__(self) -> None:
        super().__init__(Method.MANN_WHITNEY_U, "Mann-Whitney U test")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        group_col = request.variables["group"]
        outcome_col = request.variables["outcome"]
        levels = request.group_levels
        contrast = request.contrast

        if not levels or len(levels) != 2:
            raise ValueError("Mann-Whitney U requires exactly two group levels")

        data = df.filter(
            pl.col(group_col).is_in(levels) &
            pl.col(outcome_col).is_not_null() &
            ~pl.col(outcome_col).is_infinite() &
            ~pl.col(outcome_col).is_nan()
        )

        # Determine contrast order
        if contrast and contrast.endswith(f"_minus_{levels[1]}") and contrast.startswith(f"{levels[0]}_"):
            first, second = levels[0], levels[1]
        elif contrast and contrast.endswith(f"_minus_{levels[0]}") and contrast.startswith(f"{levels[1]}_"):
            first, second = levels[1], levels[0]
        else:
            first, second = levels[0], levels[1]

        group_first = data.filter(pl.col(group_col) == first)[outcome_col].to_numpy()
        group_second = data.filter(pl.col(group_col) == second)[outcome_col].to_numpy()

        if len(group_first) < 2 or len(group_second) < 2:
            raise ValueError("Each group must have at least 2 observations")

        # Mann-Whitney U test
        result = stats.mannwhitneyu(
            group_first, group_second,
            alternative=request.alternative.value,
            method="exact" if len(group_first) * len(group_second) < 10000 else "asymptotic",
        )

        # Hodges-Lehmann estimator (median of all pairwise differences)
        # For large samples, use a sample of pairwise differences
        n_pairs = len(group_first) * len(group_second)
        if n_pairs <= 10000:
            diffs = group_first[:, None] - group_second[None, :]
            hl_estimate = float(np.median(diffs))
        else:
            # Subsample for computational efficiency
            rng = np.random.default_rng(request.seed)
            sample_first = rng.choice(group_first, size=min(100, len(group_first)), replace=False)
            sample_second = rng.choice(group_second, size=min(100, len(group_second)), replace=False)
            diffs = sample_first[:, None] - sample_second[None, :]
            hl_estimate = float(np.median(diffs))

        # Rank-biserial correlation
        # r_rb = (U1 - U2) / (n1 * n2) where U1 + U2 = n1 * n2
        u_stat = float(result.statistic)
        n1, n2 = len(group_first), len(group_second)
        rank_biserial = (2 * u_stat) / (n1 * n2) - 1

        # Confidence interval for Hodges-Lehmann (bootstrap percentile)
        ci_low, ci_high = None, None
        interval_status = "not_computed"
        interval_method = IntervalMethod.NOT_COMPUTED

        try:
            n_resamples = min(get_settings().bootstrap_resamples, 2000)
            rng = np.random.default_rng(request.seed)
            hl_samples = []

            for _ in range(n_resamples):
                boot_first = rng.choice(group_first, size=len(group_first), replace=True)
                boot_second = rng.choice(group_second, size=len(group_second), replace=True)
                boot_diffs = boot_first[:, None] - boot_second[None, :]
                hl_samples.append(np.median(boot_diffs))

            hl_samples = np.array(hl_samples)
            alpha = 1 - request.confidence_level
            ci_low = float(np.percentile(hl_samples, alpha / 2 * 100))
            ci_high = float(np.percentile(hl_samples, (1 - alpha / 2) * 100))
            interval_status = "computed"
            interval_method = IntervalMethod.BOOTSTRAP_PERCENTILE
        except Exception:
            pass

        # Effect size interpretation
        abs_rb = abs(rank_biserial)
        if abs_rb < 0.1:
            es_interpretation = "negligible"
        elif abs_rb < 0.3:
            es_interpretation = "small"
        elif abs_rb < 0.5:
            es_interpretation = "moderate"
        else:
            es_interpretation = "large"

        # Bootstrap CI for rank-biserial correlation
        effect_size_ci = _bootstrap_rank_biserial_ci(
            group_first, group_second, request.confidence_level, request.seed
        )

        return StatisticalResult(
            method=Method.MANN_WHITNEY_U,
            group_counts={first: len(group_first), second: len(group_second)},
            estimate=hl_estimate,
            interval=(ci_low, ci_high) if ci_low is not None else None,
            interval_method=interval_method,
            interval_status=interval_status,
            statistic=u_stat,
            degrees_of_freedom=None,
            p_value=float(result.pvalue),
            effect_size=rank_biserial,
            effect_size_interpretation=es_interpretation,
            effect_size_ci=effect_size_ci,
            unstandardized_effect=hl_estimate,
            unstandardized_effect_ci=(ci_low, ci_high) if ci_low is not None else None,
            effect_magnitude_label=es_interpretation,
            assumption_checks={
                "test_type": "mann_whitney_u",
                "n1": n1,
                "n2": n2,
                "method": "exact" if n_pairs < 10000 else "asymptotic",
                "contrast": f"{first} minus {second}",
            },
        )


class WilcoxonSignedRankAdapter(TestAdapter):
    """Wilcoxon Signed-Rank test with matched rank-biserial correlation.
    Supports both long format (Subject_ID, Occasion, Outcome) 
    and wide format (Subject_ID, Pre_Value, Post_Value)."""

    def __init__(self) -> None:
        super().__init__(Method.WILCOXON_SIGNED_RANK, "Wilcoxon signed-rank test")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        pair_col = request.variables.get("pair_id")
        contrast = request.contrast
        
        # Detect data format
        is_wide_format = "pre_col" in request.variables and "post_col" in request.variables
        
        if is_wide_format:
            # Wide format: Subject_ID, Pre_Value, Post_Value
            pre_col = request.variables["pre_col"]
            post_col = request.variables["post_col"]
            
            # Filter to complete pairs
            data = df.filter(
                pl.col(pre_col).is_not_null() &
                pl.col(post_col).is_not_null() &
                ~pl.col(pre_col).is_infinite() &
                ~pl.col(post_col).is_infinite() &
                ~pl.col(pre_col).is_nan() &
                ~pl.col(post_col).is_nan()
            )
            
            if len(data) < 2:
                raise ValueError("Need at least 2 complete pairs")
            
            vals_pre = data[pre_col].to_numpy()
            vals_post = data[post_col].to_numpy()
            
            first, second = post_col, pre_col
            vals_first = vals_post
            vals_second = vals_pre
            first_label, second_label = post_col, pre_col
            n_pairs = len(data)
            
        else:
            # Long format: Subject_ID, Occasion, Outcome
            outcome_col = request.variables["outcome"]
            occasion_col = request.variables["occasion"]
            pair_col = request.variables.get("pair_id")
            
            if not pair_col or not occasion_col or not outcome_col:
                raise ValueError("Paired test requires pair_id, occasion, and outcome variables")
            
            wide = df.pivot(
                values=outcome_col,
                index=pair_col,
                on=occasion_col,
            ).drop_nulls()
            
            if wide.width < 3:
                raise ValueError("Need at least two occasions for paired test")
            
            occasion_cols = [c for c in wide.columns if c != pair_col]
            if len(occasion_cols) != 2:
                raise ValueError("Paired test requires exactly two occasions")
            
            # Determine contrast order
            if contrast and contrast.endswith(f"_minus_{occasion_cols[1]}") and contrast.startswith(f"{occasion_cols[0]}_"):
                first, second = occasion_cols[0], occasion_cols[1]
            elif contrast and contrast.endswith(f"_minus_{occasion_cols[0]}") and contrast.startswith(f"{occasion_cols[1]}_"):
                first, second = occasion_cols[1], occasion_cols[0]
            else:
                first, second = occasion_cols[0], occasion_cols[1]
            
            vals_first = wide[first].to_numpy()
            vals_second = wide[second].to_numpy()
            
            if len(vals_first) < 2:
                raise ValueError("Need at least 2 complete pairs")
            
            n_pairs = len(vals_first)
            first_label, second_label = first, second

        # Common Wilcoxon analysis
        diff = vals_first - vals_second

        # Wilcoxon signed-rank test
        result = stats.wilcoxon(
            vals_first, vals_second,
            alternative=request.alternative.value,
            method="exact" if len(diff) < 50 else "approx",
            zero_method="wilcox",
        )

        # Hodges-Lehmann estimator for paired data (median of differences)
        hl_estimate = float(np.median(diff))

        # Matched rank-biserial correlation
        n = len(diff)
        if result.statistic is not None:
            try:
                z_stat = stats.norm.ppf(1 - result.pvalue / 2) if request.alternative == "two-sided" else stats.norm.ppf(1 - result.pvalue)
                if result.pvalue > 0.5:
                    z_stat = 0
                rank_biserial = z_stat / np.sqrt(n) if n > 0 else 0
            except Exception:
                pos = np.sum(diff > 0)
                neg = np.sum(diff < 0)
                rank_biserial = (pos - neg) / n if n > 0 else 0
        else:
            rank_biserial = 0

        # Bootstrap CI for Hodges-Lehmann
        ci_low, ci_high = None, None
        interval_status = "not_computed"
        interval_method = IntervalMethod.NOT_COMPUTED

        try:
            n_resamples = min(get_settings().bootstrap_resamples, 2000)
            rng = np.random.default_rng(request.seed)
            hl_samples = []

            for _ in range(n_resamples):
                boot_diff = rng.choice(diff, size=n, replace=True)
                hl_samples.append(np.median(boot_diff))

            hl_samples = np.array(hl_samples)
            alpha = 1 - request.confidence_level
            ci_low = float(np.percentile(hl_samples, alpha / 2 * 100))
            ci_high = float(np.percentile(hl_samples, (1 - alpha / 2) * 100))
            interval_status = "computed"
            interval_method = IntervalMethod.BOOTSTRAP_PERCENTILE
        except Exception:
            pass

        abs_rb = abs(rank_biserial)
        if abs_rb < 0.1:
            es_interpretation = "negligible"
        elif abs_rb < 0.3:
            es_interpretation = "small"
        elif abs_rb < 0.5:
            es_interpretation = "moderate"
        else:
            es_interpretation = "large"

        # Bootstrap CI for matched rank-biserial correlation
        effect_size_ci = _bootstrap_matched_rank_biserial_ci(
            diff, request.confidence_level, request.seed
        )

        # Determine contrast label
        if contrast and "_minus_" in contrast:
            contrast_label = contrast.replace("_minus_", " minus ")
        else:
            contrast_label = f"{first_label} minus {second_label}"

        return StatisticalResult(
            method=Method.WILCOXON_SIGNED_RANK,
            group_counts={f"{first_label}": len(vals_first), f"{second_label}": len(vals_second)},
            estimate=hl_estimate,
            interval=(ci_low, ci_high) if ci_low is not None else None,
            interval_method=interval_method,
            interval_status=interval_status,
            statistic=float(result.statistic) if result.statistic is not None else None,
            degrees_of_freedom=None,
            p_value=float(result.pvalue),
            effect_size=rank_biserial,
            effect_size_interpretation=es_interpretation,
            effect_size_ci=effect_size_ci,
            unstandardized_effect=hl_estimate,
            unstandardized_effect_ci=(ci_low, ci_high) if ci_low is not None else None,
            effect_magnitude_label=es_interpretation,
            assumption_checks={
                "test_type": "wilcoxon_signed_rank",
                "n_pairs": n_pairs,
                "method": "exact" if n < 50 else "approx",
                "contrast": contrast_label,
                "data_format": "wide (pre/post columns)" if is_wide_format else "long (occasion column)",
            },
        )


class KruskalWallisAdapter(TestAdapter):
    """Kruskal-Wallis H test with epsilon-squared effect size."""

    def __init__(self) -> None:
        super().__init__(Method.KRUSKAL_WALLIS, "Kruskal-Wallis test")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        group_col = request.variables["group"]
        outcome_col = request.variables["outcome"]
        levels = request.group_levels

        if not levels or len(levels) < 3:
            raise ValueError("Kruskal-Wallis requires at least 3 groups")

        data = df.filter(
            pl.col(group_col).is_in(levels) &
            pl.col(outcome_col).is_not_null() &
            ~pl.col(outcome_col).is_infinite() &
            ~pl.col(outcome_col).is_nan()
        )

        groups = []
        group_counts = {}
        for level in levels:
            group_data = data.filter(pl.col(group_col) == level)[outcome_col].to_numpy()
            if len(group_data) > 0:
                groups.append(group_data)
                group_counts[level] = len(group_data)

        if len(groups) < 3:
            raise ValueError("Need at least 3 groups with data")

        # Kruskal-Wallis H test
        result = stats.kruskal(*groups)

        # Epsilon-squared effect size
        # ε² = (H - k + 1) / (n - k) where H is the test statistic, k is number of groups, n is total N
        H = float(result.statistic)
        k = len(groups)
        n = sum(len(g) for g in groups)

        if n > k:
            epsilon_sq = max(0, (H - k + 1) / (n - k))
        else:
            epsilon_sq = 0

        # Effect size interpretation
        if epsilon_sq < 0.01:
            es_interpretation = "negligible"
        elif epsilon_sq < 0.06:
            es_interpretation = "small"
        elif epsilon_sq < 0.14:
            es_interpretation = "moderate"
        else:
            es_interpretation = "large"

        return StatisticalResult(
            method=Method.KRUSKAL_WALLIS,
            group_counts=group_counts,
            estimate=None,  # No single estimate for k-group test
            interval=None,
            interval_method=IntervalMethod.NOT_APPLICABLE,
            interval_status="not_applicable",
            statistic=H,
            degrees_of_freedom=k - 1,
            p_value=float(result.pvalue),
            effect_size=epsilon_sq,
            effect_size_interpretation=es_interpretation,
            effect_size_ci=None,
            unstandardized_effect=None,
            unstandardized_effect_ci=None,
            effect_magnitude_label=es_interpretation,
            assumption_checks={
                "test_type": "kruskal_wallis",
                "k_groups": k,
                "total_n": n,
                "group_sizes": group_counts,
            },
        )


class DunnPosthocAdapter(TestAdapter):
    """Dunn's post-hoc test with Holm-Bonferroni correction."""

    def __init__(self) -> None:
        super().__init__(Method.DUNN_POSTHOC, "Dunn's post-hoc test")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        group_col = request.variables["group"]
        outcome_col = request.variables["outcome"]
        levels = request.group_levels

        if not levels or len(levels) < 3:
            raise ValueError("Dunn's test requires at least 3 groups")

        data = df.filter(
            pl.col(group_col).is_in(levels) &
            pl.col(outcome_col).is_not_null() &
            ~pl.col(outcome_col).is_infinite() &
            ~pl.col(outcome_col).is_nan()
        )

        groups = {}
        for level in levels:
            group_data = data.filter(pl.col(group_col) == level)[outcome_col].to_numpy()
            if len(group_data) > 0:
                groups[level] = group_data

        if len(groups) < 3:
            raise ValueError("Need at least 3 groups with data")

        # Compute ranks across all groups
        all_data = np.concatenate(list(groups.values()))
        all_ranks = stats.rankdata(all_data)

        # Map back to groups
        rank_sums = {}
        group_sizes = {}
        start = 0
        for level, vals in groups.items():
            n = len(vals)
            group_sizes[level] = n
            rank_sums[level] = np.sum(all_ranks[start:start + n])
            start += n

        n_total = len(all_ranks)

        # Pairwise comparisons
        comparisons = []
        for i, level1 in enumerate(levels):
            for level2 in levels[i+1:]:
                if level1 not in groups or level2 not in groups:
                    continue

                n1, n2 = group_sizes[level1], group_sizes[level2]
                r1, r2 = rank_sums[level1], rank_sums[level2]

                # Mean rank difference
                mean_rank1 = r1 / n1 if n1 > 0 else 0
                mean_rank2 = r2 / n2 if n2 > 0 else 0
                rank_diff = mean_rank1 - mean_rank2

                # Standard error for Dunn's test
                se = np.sqrt(n_total * (n_total + 1) / 12 * (1/n1 + 1/n2))

                if se > 0:
                    z = rank_diff / se
                    # Two-tailed p-value
                    p = 2 * stats.norm.sf(abs(z))
                else:
                    z = 0
                    p = 1.0

                comparisons.append({
                    "group1": level1,
                    "group2": level2,
                    "rank_diff": rank_diff,
                    "z_statistic": z,
                    "p_value": p,
                    "n1": n1,
                    "n2": n2,
                })

        # Holm-Bonferroni correction
        comparisons.sort(key=lambda x: x["p_value"])
        adjusted = []
        for i, comp in enumerate(comparisons):
            m = len(comparisons) - i
            adj_p = min(comp["p_value"] * m, 1.0)
            adjusted.append({**comp, "adjusted_p_value": adj_p})

        return StatisticalResult(
            method=Method.DUNN_POSTHOC,
            group_counts=group_sizes,
            estimate=None,
            interval=None,
            interval_method=IntervalMethod.NOT_APPLICABLE,
            interval_status="not_applicable",
            statistic=None,
            degrees_of_freedom=None,
            p_value=None,
            adjusted_p_value=None,
            effect_size=None,
            effect_size_interpretation=None,
            assumption_checks={
                "test_type": "dunn_posthoc",
                "comparisons": adjusted,
                "correction": "holm_bonferroni",
            },
        )


class GamesHowellPosthocAdapter(TestAdapter):
    """Games-Howell post-hoc test for unequal variances."""

    def __init__(self) -> None:
        super().__init__(Method.GAMES_HOWELL_POSTHOC, "Games-Howell post-hoc test")

    def run(self, df: pl.DataFrame, request: AnalysisRequest) -> StatisticalResult:
        group_col = request.variables["group"]
        outcome_col = request.variables["outcome"]
        levels = request.group_levels

        if not levels or len(levels) < 3:
            raise ValueError("Games-Howell requires at least 3 groups")

        data = df.filter(
            pl.col(group_col).is_in(levels) &
            pl.col(outcome_col).is_not_null() &
            ~pl.col(outcome_col).is_infinite() &
            ~pl.col(outcome_col).is_nan()
        )

        groups = {}
        for level in levels:
            group_data = data.filter(pl.col(group_col) == level)[outcome_col].to_numpy()
            if len(group_data) >= 2:
                groups[level] = group_data

        if len(groups) < 3:
            raise ValueError("Need at least 3 groups with sufficient data")

        comparisons = []
        for i, level1 in enumerate(levels):
            for level2 in levels[i+1:]:
                if level1 not in groups or level2 not in groups:
                    continue

                g1, g2 = groups[level1], groups[level2]
                n1, n2 = len(g1), len(g2)
                mean1, mean2 = np.mean(g1), np.mean(g2)
                var1, var2 = np.var(g1, ddof=1), np.var(g2, ddof=1)

                mean_diff = mean1 - mean2
                se = np.sqrt(var1/n1 + var2/n2)

                if se > 0:
                    t_stat = mean_diff / se
                    # Welch-Satterthwaite df
                    df_welch = (var1/n1 + var2/n2)**2 / (
                        (var1/n1)**2/(n1-1) + (var2/n2)**2/(n2-1)
                    )

                    # Studentized range distribution for Games-Howell
                    # q = t * sqrt(2)
                    q_stat = t_stat * np.sqrt(2)
                    k = len(groups)

                    # Two-tailed p-value from studentized range
                    # Use approximation: p = 1 - CDF of studentized range
                    try:
                        p = 1 - stats.f.cdf(q_stat**2 / 2, 1, df_welch)  # rough approximation
                    except Exception:
                        # Fallback to t-distribution
                        p = 2 * stats.t.sf(abs(t_stat), df_welch)
                else:
                    t_stat = 0
                    df_welch = 0
                    p = 1.0

                comparisons.append({
                    "group1": level1,
                    "group2": level2,
                    "mean_diff": mean_diff,
                    "t_statistic": t_stat,
                    "df": df_welch,
                    "p_value": p,
                    "n1": n1,
                    "n2": n2,
                })

        # Holm correction
        comparisons.sort(key=lambda x: x["p_value"])
        adjusted = []
        for i, comp in enumerate(comparisons):
            m = len(comparisons) - i
            adj_p = min(comp["p_value"] * m, 1.0)
            adjusted.append({**comp, "adjusted_p_value": adj_p})

        return StatisticalResult(
            method=Method.GAMES_HOWELL_POSTHOC,
            group_counts={k: len(v) for k, v in groups.items()},
            estimate=None,
            interval=None,
            interval_method=IntervalMethod.NOT_APPLICABLE,
            interval_status="not_applicable",
            statistic=None,
            degrees_of_freedom=None,
            p_value=None,
            adjusted_p_value=None,
            effect_size=None,
            effect_size_interpretation=None,
            assumption_checks={
                "test_type": "games_howell_posthoc",
                "comparisons": adjusted,
                "correction": "holm",
            },
        )


def run_posthoc_if_needed(
    df: pl.DataFrame,
    request: AnalysisRequest,
    omnibus_result: StatisticalResult,
) -> StatisticalResult | None:
    """Run appropriate post-hoc test if omnibus test is significant."""
    goal = request.goal
    alpha = 0.05

    # Check if omnibus was significant
    p_val = omnibus_result.p_value
    if p_val is None or p_val >= alpha:
        return None

    # Determine post-hoc test
    if goal == Goal.COMPARE_K_MEANS:
        # Check if variances were equal (use assumption checks)
        variance_check = omnibus_result.assumption_checks.get("variance_homogeneity", {})
        variances_equal = variance_check.get("passed", True)

        if variances_equal:
            return GamesHowellPosthocAdapter().run(df, request)
        else:
            return GamesHowellPosthocAdapter().run(df, request)  # Games-Howell is robust to unequal variances

    elif goal in (Goal.CATEGORICAL_ASSOCIATION,):
        # For chi-square, we could do standardized residuals
        # This is handled in the assumption checks
        return None

    return None