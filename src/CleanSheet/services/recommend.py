"""Statistical method recommendation engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from CleanSheet.contracts import (
    AnalysisRequest,
    EligibilityResult,
    Goal,
    Method,
    SemanticRole,
    StudyDesign,
)
from CleanSheet.config import get_settings
from CleanSheet.engine.execution import LazyExecutor, get_prepared_lazy
from CleanSheet.jobs.workspace import Workspace


@dataclass
class EligibilityGate:
    """Single eligibility check."""

    rule_id: str
    description: str
    check: callable
    severity: str = "error"  # "error" | "warning"


# Eligibility gates for each goal
ELIGIBILITY_GATES: dict[Goal, list[EligibilityGate]] = {
    Goal.COMPARE_TWO_MEANS: [
        EligibilityGate(
            rule_id="two_groups",
            description="Exactly two groups must be selected",
            check=lambda req, df, roles: len(req.group_levels or []) == 2,
        ),
        EligibilityGate(
            rule_id="continuous_outcome",
            description="Outcome must be continuous",
            check=lambda req, df, roles: roles.get(req.variables.get("outcome", "")) == SemanticRole.CONTINUOUS,
        ),
        EligibilityGate(
            rule_id="independent_design",
            description="Study design must be independent",
            check=lambda req, df, roles: req.study_design == StudyDesign.INDEPENDENT,
        ),
        EligibilityGate(
            rule_id="sufficient_data",
            description="Each group must have ≥2 finite observations",
            check=lambda req, df, roles: _check_group_counts(req, df, min_per_group=2),
            severity="error",
        ),
        EligibilityGate(
            rule_id="non_constant",
            description="Outcome must not be constant within groups",
            check=lambda req, df, roles: _check_non_constant(req, df),
            severity="warning",
        ),
    ],
    Goal.COMPARE_PAIRED_MEANS: [
        EligibilityGate(
            rule_id="paired_design",
            description="Study design must be paired",
            check=lambda req, df, roles: req.study_design == StudyDesign.PAIRED,
        ),
        EligibilityGate(
            rule_id="continuous_outcome",
            description="Outcome must be continuous",
            check=lambda req, df, roles: roles.get(req.variables.get("outcome", "")) == SemanticRole.CONTINUOUS,
        ),
        EligibilityGate(
            rule_id="pair_key",
            description="Pair identifier must be specified",
            check=lambda req, df, roles: "pair_id" in req.variables,
        ),
        EligibilityGate(
            rule_id="sufficient_pairs",
            description="Must have ≥2 complete pairs",
            check=lambda req, df, roles: _check_paired_counts(req, df, min_pairs=2),
        ),
    ],
    Goal.EXPLORE_LINEAR_RELATIONSHIP: [
        EligibilityGate(
            rule_id="two_continuous",
            description="Both variables must be continuous",
            check=lambda req, df, roles: all(
                roles.get(req.variables.get(k, "")) == SemanticRole.CONTINUOUS
                for k in ["outcome", "predictor"]
            ),
        ),
        EligibilityGate(
            rule_id="sufficient_pairs",
            description="Must have ≥3 complete paired observations",
            check=lambda req, df, roles: _check_correlation_pairs(req, df, min_pairs=3),
        ),
        EligibilityGate(
            rule_id="non_constant",
            description="Both variables must have variation",
            check=lambda req, df, roles: _check_both_non_constant(req, df),
        ),
    ],
    Goal.EXPLORE_ORDERED_RELATIONSHIP: [
        EligibilityGate(
            rule_id="ordered_variables",
            description="Variables must be continuous or ordinal",
            check=lambda req, df, roles: all(
                roles.get(req.variables.get(k, "")) in (SemanticRole.CONTINUOUS, SemanticRole.ORDINAL)
                for k in ["outcome", "predictor"]
            ),
        ),
        EligibilityGate(
            rule_id="sufficient_pairs",
            description="Must have ≥3 complete paired observations",
            check=lambda req, df, roles: _check_correlation_pairs(req, df, min_pairs=3),
        ),
    ],
    Goal.CATEGORICAL_ASSOCIATION: [
        EligibilityGate(
            rule_id="two_categorical",
            description="Both variables must be categorical",
            check=lambda req, df, roles: all(
                roles.get(req.variables.get(k, "")) == SemanticRole.CATEGORICAL
                for k in ["outcome", "group"]
            ),
        ),
        EligibilityGate(
            rule_id="sufficient_counts",
            description="Expected cell counts should be ≥5 (or use Fisher)",
            check=lambda req, df, roles: _check_contingency_counts(req, df),
            severity="warning",
        ),
    ],
    Goal.SPARSE_2X2_TABLE: [
        EligibilityGate(
            rule_id="2x2_table",
            description="Must be a 2×2 contingency table",
            check=lambda req, df, roles: _is_2x2(req, df),
        ),
        EligibilityGate(
            rule_id="independent_design",
            description="Study design must be independent",
            check=lambda req, df, roles: req.study_design == StudyDesign.INDEPENDENT,
        ),
    ],
    Goal.DESCRIBE_DATA: [
        EligibilityGate(
            rule_id="has_data",
            description="Must have at least one valid column",
            check=lambda req, df, roles: len(df.columns) > 0,
        ),
    ],
    Goal.COMPARE_K_MEANS: [
        EligibilityGate(
            rule_id="three_plus_groups",
            description="At least three groups must be selected",
            check=lambda req, df, roles: len(req.group_levels or []) >= 3,
        ),
        EligibilityGate(
            rule_id="continuous_outcome",
            description="Outcome must be continuous",
            check=lambda req, df, roles: roles.get(req.variables.get("outcome", "")) in (
                SemanticRole.CONTINUOUS, SemanticRole.DISCRETE, SemanticRole.ORDINAL
            ),
        ),
        EligibilityGate(
            rule_id="independent_design",
            description="Study design must be independent",
            check=lambda req, df, roles: req.study_design == StudyDesign.INDEPENDENT,
        ),
        EligibilityGate(
            rule_id="sufficient_data",
            description="Each group must have ≥5 finite observations",
            check=lambda req, df, roles: _check_group_counts(req, df, min_per_group=5),
            severity="error",
        ),
        EligibilityGate(
            rule_id="non_constant",
            description="Outcome must not be constant within groups",
            check=lambda req, df, roles: _check_non_constant(req, df),
            severity="warning",
        ),
    ],
}


def _check_group_counts(req: AnalysisRequest, df: pl.DataFrame, min_per_group: int) -> bool:
    """Check minimum observations per group."""
    group_col = req.variables.get("group")
    outcome_col = req.variables.get("outcome")
    if not group_col or not outcome_col:
        return False

    if group_col not in df.columns or outcome_col not in df.columns:
        return False

    # Count finite outcome per group
    finite = df.filter(
        pl.col(outcome_col).is_not_null() &
        ~pl.col(outcome_col).is_infinite() &
        ~pl.col(outcome_col).is_nan()
    )

    if req.group_levels:
        finite = finite.filter(pl.col(group_col).is_in(req.group_levels))

    counts = finite.group_by(group_col).len()
    return all(counts["len"] >= min_per_group)


def _check_non_constant(req: AnalysisRequest, df: pl.DataFrame) -> bool:
    """Check outcome is not constant."""
    outcome_col = req.variables.get("outcome")
    if not outcome_col or outcome_col not in df.columns:
        return False

    finite = df.filter(
        pl.col(outcome_col).is_not_null() &
        ~pl.col(outcome_col).is_infinite() &
        ~pl.col(outcome_col).is_nan()
    )

    if req.group_levels:
        finite = finite.filter(pl.col(req.variables["group"]).is_in(req.group_levels))

    return finite[outcome_col].n_unique() > 1


def _check_paired_counts(req: AnalysisRequest, df: pl.DataFrame, min_pairs: int) -> bool:
    """Check sufficient paired observations."""
    pair_col = req.variables.get("pair_id")
    outcome_col = req.variables.get("outcome")
    occasion_col = req.variables.get("occasion")

    if not all([pair_col, outcome_col, occasion_col]):
        return False

    if not all(c in df.columns for c in [pair_col, outcome_col, occasion_col]):
        return False

    # Count complete pairs
    wide = df.pivot(
        values=outcome_col,
        index=pair_col,
        columns=occasion_col,
    )

    # Need both occasions non-null
    complete = wide.drop_nulls()
    return complete.height >= min_pairs


def _check_correlation_pairs(req: AnalysisRequest, df: pl.DataFrame, min_pairs: int) -> bool:
    """Check sufficient paired observations for correlation."""
    x_col = req.variables.get("outcome")
    y_col = req.variables.get("predictor")

    if not x_col or not y_col:
        return False

    if x_col not in df.columns or y_col not in df.columns:
        return False

    finite = df.filter(
        pl.col(x_col).is_not_null() &
        pl.col(y_col).is_not_null() &
        ~pl.col(x_col).is_infinite() &
        ~pl.col(y_col).is_infinite() &
        ~pl.col(x_col).is_nan() &
        ~pl.col(y_col).is_nan()
    )

    return finite.height >= min_pairs


def _check_both_non_constant(req: AnalysisRequest, df: pl.DataFrame) -> bool:
    """Check both variables have variation."""
    x_col = req.variables.get("outcome")
    y_col = req.variables.get("predictor")

    for col in [x_col, y_col]:
        if not col or col not in df.columns:
            return False
        finite = df.filter(
            pl.col(col).is_not_null() &
            ~pl.col(col).is_infinite() &
            ~pl.col(col).is_nan()
        )
        if finite[col].n_unique() <= 1:
            return False
    return True


def _check_contingency_counts(req: AnalysisRequest, df: pl.DataFrame) -> bool:
    """Check expected cell counts for chi-square."""
    x_col = req.variables.get("outcome")
    y_col = req.variables.get("group")

    if not x_col or not y_col:
        return False

    if x_col not in df.columns or y_col not in df.columns:
        return False

    ct = df.select(x_col, y_col).drop_nulls()
    if ct.height == 0:
        return False

    # Compute contingency table
    contingency = ct.group_by(x_col, y_col).len().pivot(
        values="len",
        index=x_col,
        columns=y_col,
    ).fill_null(0)

    if contingency.width < 2 or contingency.height < 2:
        return False

    # Check expected counts
    row_totals = contingency.select(pl.exclude(contingency.columns[0])).sum_horizontal()
    col_totals = contingency.select(pl.exclude(contingency.columns[0])).sum()
    grand_total = row_totals.sum()

    # Simple check: any cell with expected < 5
    for row_idx in range(contingency.height):
        for col_idx in range(1, contingency.width):
            observed = contingency[row_idx, col_idx]
            expected = (row_totals[row_idx] * col_totals[col_idx - 1]) / grand_total
            if expected < 5:
                return False
    return True


def _is_2x2(req: AnalysisRequest, df: pl.DataFrame) -> bool:
    """Check if contingency table is 2x2."""
    x_col = req.variables.get("outcome")
    y_col = req.variables.get("group")

    if not x_col or not y_col:
        return False

    if x_col not in df.columns or y_col not in df.columns:
        return False

    ct = df.select(x_col, y_col).drop_nulls()
    n_x = ct[x_col].n_unique()
    n_y = ct[y_col].n_unique()

    return n_x == 2 and n_y == 2


def check_eligibility(
    workspace: Workspace,
    dataset_ref: DatasetRef,
    request: AnalysisRequest,
    column_roles: list | None = None,
    recipe_steps: list[dict[str, Any]] | None = None,
) -> EligibilityResult:
    """Check if an analysis is eligible for the given data."""
    # Get prepared data
    if recipe_steps is not None:
        lf = get_prepared_lazy(workspace, dataset_ref, recipe_steps)
        df = lf.collect(engine="streaming" if get_settings().polars_streaming else "in-memory")
    else:
        executor = LazyExecutor(workspace, dataset_ref)
        df = executor.materialize_for_profiling(list(request.variables.values()))

    # Get column roles - use confirmed roles if provided, otherwise infer
    roles = {}
    if column_roles:
        for cr in column_roles:
            roles[cr.column] = cr.semantic_role
    else:
        for col in df.columns:
            # Infer from dtype
            s = df[col]
            if s.dtype.is_numeric():
                roles[col] = SemanticRole.CONTINUOUS
            elif s.dtype in (pl.Date, pl.Datetime):
                roles[col] = SemanticRole.DATE
            elif s.dtype == pl.Boolean or (s.n_unique() / len(s) < 0.05 and s.n_unique() <= 20):
                roles[col] = SemanticRole.CATEGORICAL
            else:
                roles[col] = SemanticRole.FREE_TEXT

    # Run gates for the goal
    gates = ELIGIBILITY_GATES.get(request.goal, [])
    rule_ids = []
    reasons = []
    warnings = []
    user_confirmations = {}

    for gate in gates:
        try:
            passed = gate.check(request, df, roles)
        except Exception as e:
            passed = False
            reasons.append(f"{gate.rule_id}: {e}")

        if not passed:
            if gate.severity == "error":
                rule_ids.append(gate.rule_id)
                reasons.append(gate.description)
            else:
                warnings.append(gate.description)

    # For UNKNOWN study design, block inference (except descriptive)
    unknown_design_block = request.study_design == StudyDesign.UNKNOWN and request.goal != Goal.DESCRIBE_DATA
    if unknown_design_block:
        rule_ids.append("unknown_study_design")
        reasons.append("Study design is unknown; only descriptive analysis is allowed")

    # Determine suggested method
    suggested_method = _suggest_method(request.goal)

    allowed = len(rule_ids) == 0
    blocked_reason = "; ".join(reasons) if reasons else None

    return EligibilityResult(
        allowed=allowed,
        rule_ids=rule_ids,
        reasons=reasons,
        user_confirmations=user_confirmations,
        warnings=warnings,
        suggested_method=suggested_method,
        blocked_reason=blocked_reason,
    )


def _suggest_method(goal: Goal) -> Method:
    """Suggest default method for a goal."""
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


def recommend_questions(profile_result: Any) -> list[dict[str, Any]]:
    """Recommend analysis questions based on data profile."""
    recommendations = []

    # Get column roles
    continuous_cols = [c.name for c in profile_result.columns if c.semantic_role == "continuous"]
    categorical_cols = [c.name for c in profile_result.columns if c.semantic_role == "categorical"]
    ordinal_cols = [c.name for c in profile_result.columns if c.semantic_role == "ordinal"]
    date_cols = [c.name for c in profile_result.columns if c.semantic_role == "date"]

    # Compare two groups
    for cat_col in categorical_cols:
        for cont_col in continuous_cols:
            recommendations.append({
                "goal": Goal.COMPARE_TWO_MEANS,
                "label": f"Compare {cont_col} across {cat_col}",
                "variables": {"outcome": cont_col, "group": cat_col},
                "description": f"Compare mean {cont_col} between groups in {cat_col}",
            })

    # Paired comparison
    for date_col in date_cols:
        for cont_col in continuous_cols:
            recommendations.append({
                "goal": Goal.COMPARE_PAIRED_MEANS,
                "label": f"Compare {cont_col} over time",
                "variables": {"outcome": cont_col, "pair_id": "entity_id", "occasion": date_col},
                "description": f"Compare {cont_col} before/after using {date_col}",
            })

    # Correlations
    for i, x in enumerate(continuous_cols):
        for y in continuous_cols[i+1:]:
            recommendations.append({
                "goal": Goal.EXPLORE_LINEAR_RELATIONSHIP,
                "label": f"Explore {x} vs {y}",
                "variables": {"outcome": x, "predictor": y},
                "description": f"Linear relationship between {x} and {y}",
            })

    # Categorical associations
    for i, x in enumerate(categorical_cols):
        for y in categorical_cols[i+1:]:
            recommendations.append({
                "goal": Goal.CATEGORICAL_ASSOCIATION,
                "label": f"Associate {x} with {y}",
                "variables": {"outcome": x, "group": y},
                "description": f"Test association between {x} and {y}",
            })

    # Descriptive
    if continuous_cols or categorical_cols:
        recommendations.append({
            "goal": Goal.DESCRIBE_DATA,
            "label": "Describe the data",
            "variables": {},
            "description": "Summarize all variables with distributions and quality flags",
        })

    return recommendations
