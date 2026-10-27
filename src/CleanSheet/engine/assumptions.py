"""Assumption diagnostic engine with automatic method routing.

Implements deterministic assumption checks and method selection logic
following the statistical policy from the blueprint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
from scipy import stats

from CleanSheet.contracts import (
    AnalysisRequest,
    AssumptionCheck,
    AssumptionReport,
    Goal,
    Method,
    SemanticRole,
    StudyDesign,
)
from CleanSheet.config import get_settings


# Thresholds from statistical policy
SKEWNESS_THRESHOLD = 1.5
OUTLIER_PROPORTION_THRESHOLD = 0.05
MIN_GROUP_SIZE_INFERENCE = 5
MIN_GROUP_SIZE_PAIRED = 6
MIN_CORRELATION_N = 10
MIN_CHI2_EXPECTED = 5
CHI2_MIN_CELLS_ABOVE_5 = 0.8  # 80% of cells


@dataclass
class DiagnosticContext:
    """Context for diagnostic checks."""

    df: pl.DataFrame
    request: AnalysisRequest
    column_roles: dict[str, SemanticRole]


def check_group_sizes(ctx: DiagnosticContext) -> AssumptionCheck:
    """Check minimum group sample sizes."""
    goal = ctx.request.goal

    if goal == Goal.COMPARE_TWO_MEANS:
        group_col = ctx.request.variables["group"]
        outcome_col = ctx.request.variables["outcome"]
        levels = ctx.request.group_levels or []

        if not levels:
            return AssumptionCheck(
                name="group_sizes",
                passed=None,
                message="No group levels specified",
                severity="error",
            )

        finite = ctx.df.filter(
            pl.col(outcome_col).is_not_null() &
            ~pl.col(outcome_col).is_infinite() &
            ~pl.col(outcome_col).is_nan() &
            pl.col(group_col).is_in(levels)
        )

        counts = finite.group_by(group_col).len()
        min_count = counts["len"].min() if counts.height > 0 else 0

        passed = min_count >= MIN_GROUP_SIZE_INFERENCE
        return AssumptionCheck(
            name="group_sizes",
            passed=passed,
            value=float(min_count),
            threshold=float(MIN_GROUP_SIZE_INFERENCE),
            message=(
                f"Smallest group has n={min_count} (minimum {MIN_GROUP_SIZE_INFERENCE} required)"
                if passed
                else f"Smallest group has n={min_count} — below minimum {MIN_GROUP_SIZE_INFERENCE} for reliable inference"
            ),
            severity="error" if not passed else "info",
        )

    elif goal == Goal.COMPARE_PAIRED_MEANS:
        # Check if wide format (pre/post columns)
        if "pre_col" in ctx.request.variables and "post_col" in ctx.request.variables:
            pre_col = ctx.request.variables["pre_col"]
            post_col = ctx.request.variables["post_col"]
            
            finite = ctx.df.filter(
                pl.col(pre_col).is_not_null() &
                pl.col(post_col).is_not_null() &
                ~pl.col(pre_col).is_infinite() &
                ~pl.col(post_col).is_infinite() &
                ~pl.col(pre_col).is_nan() &
                ~pl.col(post_col).is_nan()
            )
            
            n_pairs = finite.height
            passed = n_pairs >= MIN_GROUP_SIZE_PAIRED
            return AssumptionCheck(
                name="paired_sample_size",
                passed=passed,
                value=float(n_pairs),
                threshold=float(MIN_GROUP_SIZE_PAIRED),
                message=(
                    f"Complete pairs: n={n_pairs}"
                    if passed
                    else f"Only {n_pairs} complete pairs — below minimum {MIN_GROUP_SIZE_PAIRED}"
                ),
                severity="error" if not passed else "info",
            )
        
        # Long format
        pair_col = ctx.request.variables["pair_id"]
        outcome_col = ctx.request.variables["outcome"]
        occasion_col = ctx.request.variables["occasion"]

        wide = ctx.df.pivot(values=outcome_col, index=pair_col, on=occasion_col).drop_nulls()
        n_pairs = wide.height

        passed = n_pairs >= MIN_GROUP_SIZE_PAIRED
        return AssumptionCheck(
            name="paired_sample_size",
            passed=passed,
            value=float(n_pairs),
            threshold=float(MIN_GROUP_SIZE_PAIRED),
            message=(
                f"Complete pairs: n={n_pairs}"
                if passed
                else f"Only {n_pairs} complete pairs — below minimum {MIN_GROUP_SIZE_PAIRED}"
            ),
            severity="error" if not passed else "info",
        )

    elif goal in (Goal.EXPLORE_LINEAR_RELATIONSHIP, Goal.EXPLORE_ORDERED_RELATIONSHIP):
        x_col = ctx.request.variables["outcome"]
        y_col = ctx.request.variables["predictor"]

        finite = ctx.df.filter(
            pl.col(x_col).is_not_null() &
            pl.col(y_col).is_not_null() &
            ~pl.col(x_col).is_infinite() &
            ~pl.col(y_col).is_infinite() &
            ~pl.col(x_col).is_nan() &
            ~pl.col(y_col).is_nan()
        )

        n = finite.height
        passed = n >= MIN_CORRELATION_N
        return AssumptionCheck(
            name="correlation_sample_size",
            passed=passed,
            value=float(n),
            threshold=float(MIN_CORRELATION_N),
            message=(
                f"Complete paired observations: n={n}"
                if passed
                else f"Only {n} complete pairs — below minimum {MIN_CORRELATION_N}"
            ),
            severity="error" if not passed else "info",
        )

    elif goal in (Goal.CATEGORICAL_ASSOCIATION, Goal.SPARSE_2X2_TABLE):
        x_col = ctx.request.variables["outcome"]
        y_col = ctx.request.variables["group"]

        data = ctx.df.select(x_col, y_col).drop_nulls()
        n = data.height

        passed = n >= 15  # Minimum for any chi-square
        return AssumptionCheck(
            name="contingency_sample_size",
            passed=passed,
            value=float(n),
            threshold=15.0,
            message=(
                f"Total observations: n={n}"
                if passed
                else f"Only {n} observations — below minimum 15"
            ),
            severity="error" if not passed else "info",
        )

    return AssumptionCheck(name="group_sizes", passed=True, message="Not applicable", severity="info")


def check_skewness(ctx: DiagnosticContext) -> AssumptionCheck:
    """Check skewness of continuous outcome variables."""
    goal = ctx.request.goal

    if goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS):
        outcome_col = ctx.request.variables["outcome"]
        group_col = ctx.request.variables.get("group")

        if group_col and ctx.request.group_levels:
            # Check per group
            max_skew = 0.0
            skew_details = []

            for level in ctx.request.group_levels:
                group_data = ctx.df.filter(
                    pl.col(group_col) == level
                )[outcome_col].drop_nulls()

                if len(group_data) >= 3:
                    skew = float(group_data.skew())
                    skew_details.append(f"{level}: {skew:.2f}")
                    max_skew = max(max_skew, abs(skew))

            passed = max_skew <= SKEWNESS_THRESHOLD
            return AssumptionCheck(
                name="skewness",
                passed=passed,
                value=max_skew,
                threshold=SKEWNESS_THRESHOLD,
                message=(
                    f"Max group skewness: {max_skew:.2f} (threshold: {SKEWNESS_THRESHOLD}) — {', '.join(skew_details)}"
                    if passed
                    else f"High skewness detected: {max_skew:.2f} > {SKEWNESS_THRESHOLD} — {', '.join(skew_details)}. Consider non-parametric alternative."
                ),
                severity="warning" if not passed else "info",
            )

    elif goal == Goal.COMPARE_PAIRED_MEANS:
        # Check if wide format
        if "pre_col" in ctx.request.variables and "post_col" in ctx.request.variables:
            pre_col = ctx.request.variables["pre_col"]
            post_col = ctx.request.variables["post_col"]
            
            finite = ctx.df.filter(
                pl.col(pre_col).is_not_null() &
                pl.col(post_col).is_not_null() &
                ~pl.col(pre_col).is_infinite() &
                ~pl.col(post_col).is_infinite() &
                ~pl.col(pre_col).is_nan() &
                ~pl.col(post_col).is_nan()
            )
            
            if finite.height >= 3:
                diff = finite[post_col] - finite[pre_col]
                skew = float(diff.skew())
                
                passed = abs(skew) <= SKEWNESS_THRESHOLD
                return AssumptionCheck(
                    name="skewness_differences",
                    passed=passed,
                    value=abs(skew),
                    threshold=SKEWNESS_THRESHOLD,
                    message=(
                        f"Paired differences skewness: {skew:.2f}"
                        if passed
                        else f"Paired differences highly skewed ({skew:.2f}) — consider Wilcoxon signed-rank"
                    ),
                    severity="warning" if not passed else "info",
                )
        else:
            # Long format
            outcome_col = ctx.request.variables["outcome"]
            pair_col = ctx.request.variables["pair_id"]
            occasion_col = ctx.request.variables["occasion"]

            wide = ctx.df.pivot(values=outcome_col, index=pair_col, on=occasion_col).drop_nulls()
            if wide.width >= 3:
                occasion_cols = [c for c in wide.columns if c != pair_col]
                if len(occasion_cols) >= 2:
                    diff = wide[occasion_cols[0]] - wide[occasion_cols[1]]
                    skew = float(diff.skew()) if len(diff) >= 3 else 0

                    passed = abs(skew) <= SKEWNESS_THRESHOLD
                    return AssumptionCheck(
                        name="skewness_differences",
                        passed=passed,
                        value=abs(skew),
                        threshold=SKEWNESS_THRESHOLD,
                        message=(
                            f"Paired differences skewness: {skew:.2f}"
                            if passed
                            else f"Paired differences highly skewed ({skew:.2f}) — consider Wilcoxon signed-rank"
                        ),
                        severity="warning" if not passed else "info",
                    )

    elif goal in (Goal.EXPLORE_LINEAR_RELATIONSHIP,):
        x_col = ctx.request.variables["outcome"]
        y_col = ctx.request.variables["predictor"]

        finite = ctx.df.filter(
            pl.col(x_col).is_not_null() &
            pl.col(y_col).is_not_null() &
            ~pl.col(x_col).is_infinite() &
            ~pl.col(y_col).is_infinite() &
            ~pl.col(x_col).is_nan() &
            ~pl.col(y_col).is_nan()
        )

        if finite.height >= 3:
            skew_x = float(finite[x_col].skew())
            skew_y = float(finite[y_col].skew())
            max_skew = max(abs(skew_x), abs(skew_y))

            passed = max_skew <= SKEWNESS_THRESHOLD
            return AssumptionCheck(
                name="skewness",
                passed=passed,
                value=max_skew,
                threshold=SKEWNESS_THRESHOLD,
                message=(
                    f"Max skewness: {max_skew:.2f} (X: {skew_x:.2f}, Y: {skew_y:.2f})"
                    if passed
                    else f"High skewness (X: {skew_x:.2f}, Y: {skew_y:.2f}) — consider Spearman correlation"
                ),
                severity="warning" if not passed else "info",
            )

    return AssumptionCheck(name="skewness", passed=True, message="Not applicable", severity="info")


def check_outliers(ctx: DiagnosticContext) -> AssumptionCheck:
    """Check outlier proportion using IQR method."""
    goal = ctx.request.goal

    if goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS):
        outcome_col = ctx.request.variables["outcome"]

        finite = ctx.df.filter(
            pl.col(outcome_col).is_not_null() &
            ~pl.col(outcome_col).is_infinite() &
            ~pl.col(outcome_col).is_nan()
        )

        if finite.height < 10:
            return AssumptionCheck(
                name="outliers",
                passed=None,
                message="Insufficient data for outlier check",
                severity="info",
            )

        vals = finite[outcome_col].to_numpy()
        q1 = np.percentile(vals, 25)
        q3 = np.percentile(vals, 75)
        iqr = q3 - q1
        lower = q1 - 3 * iqr
        upper = q3 + 3 * iqr

        outliers = np.sum((vals < lower) | (vals > upper))
        prop = outliers / len(vals)

        passed = prop <= OUTLIER_PROPORTION_THRESHOLD
        return AssumptionCheck(
            name="outliers",
            passed=passed,
            value=prop,
            threshold=OUTLIER_PROPORTION_THRESHOLD,
            message=(
                f"Outliers (>3 IQR): {outliers}/{len(vals)} ({prop:.1%})"
                if passed
                else f"High outlier proportion: {outliers}/{len(vals)} ({prop:.1%}) — robust methods recommended"
            ),
            severity="warning" if not passed else "info",
        )

    elif goal == Goal.COMPARE_PAIRED_MEANS:
        # Wide format
        if "pre_col" in ctx.request.variables and "post_col" in ctx.request.variables:
            pre_col = ctx.request.variables["pre_col"]
            post_col = ctx.request.variables["post_col"]
            
            finite = ctx.df.filter(
                pl.col(pre_col).is_not_null() &
                pl.col(post_col).is_not_null() &
                ~pl.col(pre_col).is_infinite() &
                ~pl.col(post_col).is_infinite() &
                ~pl.col(pre_col).is_nan() &
                ~pl.col(post_col).is_nan()
            )
            
            if finite.height >= 10:
                diff = finite[post_col] - finite[pre_col]
                vals = diff.to_numpy()
            else:
                return AssumptionCheck(name="outliers", passed=None, message="Insufficient data for outlier check", severity="info")
        else:
            # Long format
            outcome_col = ctx.request.variables["outcome"]
            
            finite = ctx.df.filter(
                pl.col(outcome_col).is_not_null() &
                ~pl.col(outcome_col).is_infinite() &
                ~pl.col(outcome_col).is_nan()
            )
            
            if finite.height < 10:
                return AssumptionCheck(
                    name="outliers",
                    passed=None,
                    message="Insufficient data for outlier check",
                    severity="info",
                )
            
            vals = finite[outcome_col].to_numpy()

        q1 = np.percentile(vals, 25)
        q3 = np.percentile(vals, 75)
        iqr = q3 - q1
        lower = q1 - 3 * iqr
        upper = q3 + 3 * iqr

        outliers = np.sum((vals < lower) | (vals > upper))
        prop = outliers / len(vals)

        passed = prop <= OUTLIER_PROPORTION_THRESHOLD
        return AssumptionCheck(
            name="outliers",
            passed=passed,
            value=prop,
            threshold=OUTLIER_PROPORTION_THRESHOLD,
            message=(
                f"Outliers (>3 IQR on differences): {outliers}/{len(vals)} ({prop:.1%})"
                if passed
                else f"High outlier proportion: {outliers}/{len(vals)} ({prop:.1%}) — robust methods recommended"
            ),
            severity="warning" if not passed else "info",
        )

    return AssumptionCheck(name="outliers", passed=True, message="Not applicable", severity="info")


def check_variance_homogeneity(ctx: DiagnosticContext) -> AssumptionCheck:
    """Check homogeneity of variance using Brown-Forsythe test."""
    goal = ctx.request.goal

    if goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS):
        outcome_col = ctx.request.variables["outcome"]
        group_col = ctx.request.variables["group"]
        levels = ctx.request.group_levels or []

        if len(levels) < 2:
            return AssumptionCheck(name="variance_homogeneity", passed=True, message="Insufficient groups", severity="info")

        groups = []
        for level in levels:
            group_data = ctx.df.filter(
                pl.col(group_col) == level
            )[outcome_col].drop_nulls()

            if len(group_data) >= 2:
                groups.append(group_data.to_numpy())

        if len(groups) < 2:
            return AssumptionCheck(name="variance_homogeneity", passed=True, message="Insufficient group data", severity="info")

        try:
            # Brown-Forsythe test (Levene with median center)
            stat, p = stats.levene(*groups, center="median")

            passed = p >= 0.05
            return AssumptionCheck(
                name="variance_homogeneity",
                passed=passed,
                value=p,
                threshold=0.05,
                message=(
                    f"Brown-Forsythe test: p = {p:.4f} (variances appear equal)"
                    if passed
                    else f"Brown-Forsythe test: p = {p:.4f} — unequal variances detected. Welch's test recommended."
                ),
                severity="warning" if not passed else "info",
            )
        except Exception:
            return AssumptionCheck(
                name="variance_homogeneity",
                passed=None,
                message="Could not compute variance test",
                severity="info",
            )

    return AssumptionCheck(name="variance_homogeneity", passed=True, message="Not applicable", severity="info")


def check_normality(ctx: DiagnosticContext) -> AssumptionCheck:
    """Check normality using Shapiro-Wilk (supplementary, not sole gate)."""
    goal = ctx.request.goal

    if goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS):
        outcome_col = ctx.request.variables["outcome"]
        group_col = ctx.request.variables.get("group")
        levels = ctx.request.group_levels or []

        results = []
        for level in levels:
            group_data = ctx.df.filter(
                pl.col(group_col) == level
            )[outcome_col].drop_nulls()

            if len(group_data) >= 3:
                n = min(len(group_data), 5000)
                sample = group_data.sample(n=n, seed=42).to_numpy() if len(group_data) > n else group_data.to_numpy()
                try:
                    stat, p = stats.shapiro(sample)
                    results.append((level, p))
                except Exception:
                    pass

        if not results:
            return AssumptionCheck(name="normality", passed=None, message="Insufficient data", severity="info")

        min_p = min(p for _, p in results)
        # Don't use as sole gate - just report
        return AssumptionCheck(
            name="normality",
            passed=None,
            value=min_p,
            threshold=0.05,
            message=f"Shapiro-Wilk (supplementary): min p = {min_p:.4f} across groups. Not used as sole gate.",
            severity="info",
        )

    elif goal == Goal.COMPARE_PAIRED_MEANS:
        outcome_col = ctx.request.variables["outcome"]
        pair_col = ctx.request.variables["pair_id"]
        occasion_col = ctx.request.variables["occasion"]

        wide = ctx.df.pivot(values=outcome_col, index=pair_col, on=occasion_col).drop_nulls()
        if wide.width >= 3:
            occasion_cols = [c for c in wide.columns if c != pair_col]
            if len(occasion_cols) >= 2:
                diff = wide[occasion_cols[0]] - wide[occasion_cols[1]]
                if len(diff) >= 3:
                    n = min(len(diff), 5000)
                    sample = diff.sample(n=n, seed=42).to_numpy() if len(diff) > n else diff.to_numpy()
                    try:
                        stat, p = stats.shapiro(sample)
                        return AssumptionCheck(
                            name="normality_differences",
                            passed=None,
                            value=p,
                            threshold=0.05,
                            message=f"Shapiro-Wilk on differences: p = {p:.4f}. Not used as sole gate.",
                            severity="info",
                        )
                    except Exception:
                        pass

    return AssumptionCheck(name="normality", passed=True, message="Not applicable", severity="info")


def check_contingency_expected_counts(ctx: DiagnosticContext) -> AssumptionCheck:
    """Check expected cell counts for chi-square."""
    goal = ctx.request.goal

    if goal in (Goal.CATEGORICAL_ASSOCIATION, Goal.SPARSE_2X2_TABLE):
        x_col = ctx.request.variables["outcome"]
        y_col = ctx.request.variables["group"]

        ct = ctx.df.select(x_col, y_col).drop_nulls()
        if ct.height == 0:
            return AssumptionCheck(name="expected_counts", passed=False, message="No data after dropping nulls", severity="error")

        contingency = ct.group_by(x_col, y_col).len().pivot(
            values="len", index=x_col, on=y_col
        ).fill_null(0)

        row_names = contingency[x_col].to_list()
        col_names = [c for c in contingency.columns if c != x_col]
        observed = contingency.select(col_names).to_numpy().astype(float)

        # Expected counts
        row_totals = observed.sum(axis=1)
        col_totals = observed.sum(axis=0)
        grand_total = observed.sum()
        expected = np.outer(row_totals, col_totals) / grand_total

        min_expected = expected.min()
        cells_below_5 = np.sum(expected < MIN_CHI2_EXPECTED)
        total_cells = expected.size
        prop_below = cells_below_5 / total_cells

        passed = min_expected >= MIN_CHI2_EXPECTED and prop_below <= (1 - CHI2_MIN_CELLS_ABOVE_5)

        return AssumptionCheck(
            name="expected_counts",
            passed=passed,
            value=min_expected,
            threshold=MIN_CHI2_EXPECTED,
            message=(
                f"Min expected count: {min_expected:.1f}, cells <5: {cells_below_5}/{total_cells}"
                if passed
                else f"Min expected count: {min_expected:.1f} (< {MIN_CHI2_EXPECTED}), {cells_below_5}/{total_cells} cells below 5 — Fisher's exact or Monte Carlo recommended"
            ),
            severity="warning" if not passed else "info",
        )

    return AssumptionCheck(name="expected_counts", passed=True, message="Not applicable", severity="info")


def check_missingness_balance(ctx: DiagnosticContext) -> AssumptionCheck:
    """Check if missingness is balanced across groups (MAR/MNAR alert)."""
    goal = ctx.request.goal

    if goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS):
        outcome_col = ctx.request.variables["outcome"]
        group_col = ctx.request.variables.get("group")
        levels = ctx.request.group_levels or []

        if not group_col or not levels:
            return AssumptionCheck(name="missingness_balance", passed=True, message="Not applicable", severity="info")

        # Create missing indicator
        df_with_missing = ctx.df.with_columns(
            pl.col(outcome_col).is_null().alias(f"_{outcome_col}_missing")
        )

        missing_by_group = df_with_missing.group_by(group_col).agg(
            pl.col(f"_{outcome_col}_missing").sum().alias("missing_count"),
            pl.len().alias("total_count"),
        ).filter(pl.col(group_col).is_in(levels))

        if missing_by_group.height < 2:
            return AssumptionCheck(name="missingness_balance", passed=True, message="Not applicable", severity="info")

        # Chi-square test for missingness independence
        missing_counts = missing_by_group["missing_count"].to_numpy()
        total_counts = missing_by_group["total_count"].to_numpy()
        observed_missing = np.column_stack([missing_counts, total_counts - missing_counts])

        try:
            stat, p, _, _ = stats.chi2_contingency(observed_missing, correction=False)

            # Only warn if missingness > 10% overall AND p < 0.01
            total_missing = missing_counts.sum()
            total_n = total_counts.sum()
            overall_missing_pct = total_missing / total_n if total_n > 0 else 0

            if overall_missing_pct > 0.1 and p < 0.01:
                return AssumptionCheck(
                    name="missingness_balance",
                    passed=False,
                    value=p,
                    threshold=0.01,
                    message=(
                        f"Missingness differs across groups (χ² p = {p:.4f}, overall {overall_missing_pct:.1%} missing). "
                        "May indicate missing-not-at-random bias."
                    ),
                    severity="warning",
                )

            return AssumptionCheck(
                name="missingness_balance",
                passed=True,
                value=p,
                threshold=0.01,
                message=f"Missingness balanced across groups (χ² p = {p:.4f})",
                severity="info",
            )
        except Exception:
            pass

    return AssumptionCheck(name="missingness_balance", passed=True, message="Not applicable", severity="info")


def run_assumption_diagnostics(
    df: pl.DataFrame,
    request: AnalysisRequest,
    column_roles: dict[str, SemanticRole],
) -> AssumptionReport:
    """Run all relevant assumption checks for the analysis request."""
    ctx = DiagnosticContext(df=df, request=request, column_roles=column_roles)

    checks = []

    # Always run these
    checks.append(check_group_sizes(ctx))
    checks.append(check_missingness_balance(ctx))

    # Parametric assumption checks
    if request.goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS, Goal.COMPARE_PAIRED_MEANS, Goal.EXPLORE_LINEAR_RELATIONSHIP):
        checks.append(check_skewness(ctx))
        checks.append(check_outliers(ctx))

    if request.goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS):
        checks.append(check_variance_homogeneity(ctx))
        checks.append(check_normality(ctx))

    if request.goal in (Goal.CATEGORICAL_ASSOCIATION, Goal.SPARSE_2X2_TABLE):
        checks.append(check_contingency_expected_counts(ctx))

    # Determine routing
    report = _determine_method_routing(request, checks)

    return report


def _determine_method_routing(request: AnalysisRequest, checks: list[AssumptionCheck]) -> AssumptionReport:
    """Determine the recommended method based on assumption checks."""
    goal = request.goal
    study_design = request.study_design

    # Default parametric methods
    parametric_map = {
        Goal.COMPARE_TWO_MEANS: Method.WELCH_T,
        Goal.COMPARE_PAIRED_MEANS: Method.PAIRED_T,
        Goal.COMPARE_K_MEANS: Method.WELCH_T,  # ANOVA handled separately
        Goal.EXPLORE_LINEAR_RELATIONSHIP: Method.PEARSON_R,
        Goal.EXPLORE_ORDERED_RELATIONSHIP: Method.SPEARMAN_RHO,
        Goal.CATEGORICAL_ASSOCIATION: Method.CHI2_INDEPENDENCE,
        Goal.SPARSE_2X2_TABLE: Method.FISHER_EXACT,
    }

    # Non-parametric fallbacks
    nonparametric_map = {
        Goal.COMPARE_TWO_MEANS: Method.MANN_WHITNEY_U,
        Goal.COMPARE_PAIRED_MEANS: Method.WILCOXON_SIGNED_RANK,
        Goal.COMPARE_K_MEANS: Method.KRUSKAL_WALLIS,
        Goal.EXPLORE_LINEAR_RELATIONSHIP: Method.SPEARMAN_RHO,
        Goal.EXPLORE_ORDERED_RELATIONSHIP: Method.SPEARMAN_RHO,
        Goal.CATEGORICAL_ASSOCIATION: Method.CHI2_INDEPENDENCE,  # Same, but with warning
        Goal.SPARSE_2X2_TABLE: Method.FISHER_EXACT,
    }

    parametric_method = parametric_map.get(goal, Method.DESCRIPTIVE)
    nonparametric_method = nonparametric_map.get(goal, Method.DESCRIPTIVE)

    # Check for hard blockers (insufficient sample size)
    hard_blockers = [c for c in checks if c.severity == "error" and c.passed is False]

    if hard_blockers:
        return AssumptionReport(
            checks=checks,
            routing_explanation=f"Analysis blocked: {'; '.join(c.message for c in hard_blockers)}",
            recommended_method=Method.DESCRIPTIVE,
            fallback_method=None,
            auto_routed=False,
        )

    # Check for assumption violations that trigger non-parametric routing
    assumption_failures = [
        c for c in checks
        if c.passed is False and c.name in ("skewness", "outliers", "variance_homogeneity", "expected_counts")
    ]

    # Also check study design mismatch
    design_mismatch = False
    if goal == Goal.COMPARE_TWO_MEANS and study_design != StudyDesign.INDEPENDENT:
        design_mismatch = True
    elif goal == Goal.COMPARE_PAIRED_MEANS and study_design != StudyDesign.PAIRED:
        design_mismatch = True

    if assumption_failures or design_mismatch:
        reasons = [c.message for c in assumption_failures]
        if design_mismatch:
            reasons.append(f"Study design ({study_design.value}) doesn't match analysis type")

        return AssumptionReport(
            checks=checks,
            routing_explanation="Assumption violations detected: " + "; ".join(reasons),
            recommended_method=nonparametric_method,
            fallback_method=parametric_method,
            auto_routed=True,
        )

    # All clear for parametric
    return AssumptionReport(
        checks=checks,
        routing_explanation="All assumption checks passed. Parametric method appropriate.",
        recommended_method=parametric_method,
        fallback_method=nonparametric_method,
        auto_routed=False,
    )


def get_method_display_name(method: Method) -> str:
    """Get human-readable method name."""
    names = {
        Method.WELCH_T: "Welch's t-test",
        Method.PAIRED_T: "Paired t-test",
        Method.PEARSON_R: "Pearson correlation",
        Method.SPEARMAN_RHO: "Spearman rank correlation",
        Method.CHI2_INDEPENDENCE: "Chi-square test of independence",
        Method.FISHER_EXACT: "Fisher's exact test",
        Method.MANN_WHITNEY_U: "Mann-Whitney U test",
        Method.WILCOXON_SIGNED_RANK: "Wilcoxon signed-rank test",
        Method.KRUSKAL_WALLIS: "Kruskal-Wallis test",
        Method.DUNN_POSTHOC: "Dunn's post-hoc test",
        Method.GAMES_HOWELL_POSTHOC: "Games-Howell post-hoc test",
        Method.DESCRIPTIVE: "Descriptive statistics",
    }
    return names.get(method, method.value)


def get_effect_size_info(method: Method) -> dict[str, str]:
    """Get effect size information for a method."""
    info = {
        Method.WELCH_T: {"name": "Hedges' g", "interpretation": "Standardized mean difference (bias-corrected)"},
        Method.PAIRED_T: {"name": "Cohen's d_z", "interpretation": "Standardized mean paired difference"},
        Method.MANN_WHITNEY_U: {"name": "Rank-biserial r", "interpretation": "Probability that random observation from one group exceeds the other"},
        Method.WILCOXON_SIGNED_RANK: {"name": "Matched rank-biserial r", "interpretation": "Probability that paired difference is positive"},
        Method.KRUSKAL_WALLIS: {"name": "Epsilon-squared (ε²)", "interpretation": "Proportion of variance in ranks explained by groups"},
        Method.PEARSON_R: {"name": "Pearson r", "interpretation": "Linear correlation coefficient"},
        Method.SPEARMAN_RHO: {"name": "Spearman ρ", "interpretation": "Monotonic rank correlation"},
        Method.CHI2_INDEPENDENCE: {"name": "Cramér's V", "interpretation": "Association strength (0-1)"},
        Method.FISHER_EXACT: {"name": "Odds Ratio", "interpretation": "Odds of outcome in one group vs another"},
    }
    return info.get(method, {"name": "N/A", "interpretation": "No effect size defined"})