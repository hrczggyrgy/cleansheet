"""Autonomous Discovery Engine with BH-FDR control and multi-factor ranking.

Implements the 9-step deterministic pipeline for safe automated insight discovery.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl
from scipy import stats

from CleanSheet.config import get_settings
from CleanSheet.contracts import (
    AnalysisMode,
    AnalysisRequest,
    AssumptionReport,
    ColumnRole,
    DiscoveryCandidate,
    EligibilityResult,
    Goal,
    Method,
    SemanticRole,
    StudyDesign,
    Alternative,
    MissingPolicy,
    NonFinitePolicy,
)
from CleanSheet.engine.assumptions import run_assumption_diagnostics
from CleanSheet.engine.execution import LazyExecutor
from CleanSheet.services.recommend import check_eligibility
from CleanSheet.services.statistics import run_analysis, _select_method
from CleanSheet.jobs.workspace import Workspace


@dataclass
class DiscoveryConfig:
    """Configuration for discovery mode."""
    max_candidates: int = 40
    min_effect_size_threshold: float = 0.1  # Minimum |effect| to consider
    fdr_alpha: float = 0.05
    redundancy_threshold: float = 0.75  # |r| > 0.75 considered redundant
    min_group_size: int = 5
    min_correlation_n: int = 10
    relevance_boost_target: float = 0.2  # Boost for user-specified targets


class DiscoveryEngine:
    """Deterministic autonomous discovery engine."""

    def __init__(
        self,
        workspace: Workspace,
        dataset_ref,
        column_roles: list[ColumnRole],
        recipe_steps: list[dict[str, Any]] | None = None,
        target_column: str | None = None,
        config: DiscoveryConfig | None = None,
    ):
        self.ws = workspace
        self.dataset_ref = dataset_ref
        self.column_roles_list = column_roles
        self.column_roles = {cr.column: cr.semantic_role for cr in column_roles}
        self.recipe_steps = recipe_steps or []
        self.target_column = target_column
        self.config = config or DiscoveryConfig()
        self.executor = LazyExecutor(workspace, dataset_ref)
        self._df = None

    @property
    def df(self) -> pl.DataFrame:
        """Lazy load prepared data."""
        if self._df is None:
            if self.recipe_steps:
                lf = self.executor.source_lf
                from CleanSheet.engine.execution import build_preparation_pipeline
                lf = build_preparation_pipeline(lf, self.recipe_steps)
                # Get all columns that have semantic roles
                all_cols = list(self.column_roles.keys())
                self._df = lf.select(all_cols).collect(engine="streaming")
            else:
                all_cols = list(self.column_roles.keys())
                self._df = self.executor.materialize_for_profiling(all_cols)
        return self._df

    def run_discovery(self) -> list[DiscoveryCandidate]:
        """Run the full 9-step discovery pipeline."""
        # Step 1-3: Already done (types inferred, quality profiled, context captured)
        
        # Step 4: Generate eligible analytical questions
        candidates = self._generate_candidates()
        
        if not candidates:
            return []
        
        # Step 5: Check method eligibility and assumptions
        candidates = self._check_eligibility_and_assumptions(candidates)
        
        # Filter out blocked candidates
        candidates = [c for c in candidates if c.eligibility and c.eligibility.allowed]
        
        if not candidates:
            return []
        
        # Step 6: Run analyses and compute raw p-values
        candidates = self._run_candidate_analyses(candidates)
        
        # Step 7: Apply BH-FDR adjustment
        candidates = self._apply_bh_fdr(candidates)
        
        # Step 8: Filter by effect size and q-value
        candidates = self._filter_by_significance(candidates)
        
        # Step 9: Rank by composite score and prune redundancy
        candidates = self._rank_and_prune(candidates)
        
        # Limit to top results
        return candidates[:5]

    def _generate_candidates(self) -> list[DiscoveryCandidate]:
        """Generate candidate questions from variable pairs."""
        candidates = []
        
        # Get columns by semantic role
        continuous = [c for c, r in self.column_roles.items() if r == SemanticRole.CONTINUOUS]
        discrete = [c for c, r in self.column_roles.items() if r == SemanticRole.DISCRETE]
        ordinal = [c for c, r in self.column_roles.items() if r == SemanticRole.ORDINAL]
        nominal = [c for c, r in self.column_roles.items() if r == SemanticRole.NOMINAL]
        binary = [c for c, r in self.column_roles.items() if r == SemanticRole.BINARY]
        date_cols = [c for c, r in self.column_roles.items() if r in (SemanticRole.DATE, SemanticRole.DATETIME)]
        
        numeric_cols = continuous + discrete + ordinal
        categorical_cols = nominal + ordinal + binary
        
        # If target column specified, only generate questions involving it
        if self.target_column:
            if self.target_column not in self.column_roles:
                return []
            
            target_role = self.column_roles[self.target_column]
            
            if target_role in (SemanticRole.CONTINUOUS, SemanticRole.DISCRETE, SemanticRole.ORDINAL):
                # Target is numeric: compare across categorical, correlate with numeric
                for cat in categorical_cols:
                    if cat != self.target_column:
                        candidates.append(self._make_candidate(
                            Goal.COMPARE_K_MEANS if self._n_levels(cat) > 2 else Goal.COMPARE_TWO_MEANS,
                            {"outcome": self.target_column, "group": cat},
                            f"Compare {self.target_column} across {cat}"
                        ))
                
                for num in numeric_cols:
                    if num != self.target_column:
                        candidates.append(self._make_candidate(
                            Goal.EXPLORE_LINEAR_RELATIONSHIP,
                            {"outcome": self.target_column, "predictor": num},
                            f"Explore linear relationship: {self.target_column} vs {num}"
                        ))
                        candidates.append(self._make_candidate(
                            Goal.EXPLORE_ORDERED_RELATIONSHIP,
                            {"outcome": self.target_column, "predictor": num},
                            f"Explore monotonic relationship: {self.target_column} vs {num}"
                        ))
            
            elif target_role in (SemanticRole.NOMINAL, SemanticRole.ORDINAL, SemanticRole.BINARY):
                # Target is categorical: associate with other categorical, compare numeric across target
                for cat in categorical_cols:
                    if cat != self.target_column:
                        candidates.append(self._make_candidate(
                            Goal.CATEGORICAL_ASSOCIATION,
                            {"outcome": self.target_column, "group": cat},
                            f"Test association: {self.target_column} vs {cat}"
                        ))
                
                for num in numeric_cols:
                    candidates.append(self._make_candidate(
                        Goal.COMPARE_K_MEANS if self._n_levels(self.target_column) > 2 else Goal.COMPARE_TWO_MEANS,
                        {"outcome": num, "group": self.target_column},
                        f"Compare {num} across {self.target_column}"
                    ))
        else:
            # Full pairwise discovery
            
            # 1. Compare numeric across categorical (t-test/ANOVA/Kruskal-Wallis)
            for cat in categorical_cols:
                n_levels = self._n_levels(cat)
                if n_levels < 2 or n_levels > 15:
                    continue
                for num in numeric_cols:
                    goal = Goal.COMPARE_K_MEANS if n_levels > 2 else Goal.COMPARE_TWO_MEANS
                    candidates.append(self._make_candidate(
                        goal,
                        {"outcome": num, "group": cat},
                        f"Compare {num} across {cat}"
                    ))
            
            # 2. Numeric relationships (correlation)
            for i, x in enumerate(numeric_cols):
                for y in numeric_cols[i+1:]:
                    candidates.append(self._make_candidate(
                        Goal.EXPLORE_LINEAR_RELATIONSHIP,
                        {"outcome": x, "predictor": y},
                        f"Explore linear relationship: {x} vs {y}"
                    ))
                    candidates.append(self._make_candidate(
                        Goal.EXPLORE_ORDERED_RELATIONSHIP,
                        {"outcome": x, "predictor": y},
                        f"Explore monotonic relationship: {x} vs {y}"
                    ))
            
            # 3. Categorical associations (chi-square)
            for i, x in enumerate(categorical_cols):
                for y in categorical_cols[i+1:]:
                    candidates.append(self._make_candidate(
                        Goal.CATEGORICAL_ASSOCIATION,
                        {"outcome": x, "group": y},
                        f"Test association: {x} vs {y}"
                    ))
        
        # Limit candidate pool
        return candidates[:self.config.max_candidates]

    def _make_candidate(self, goal: Goal, variables: dict[str, str], label: str) -> DiscoveryCandidate:
        """Create a DiscoveryCandidate with basic info."""
        return DiscoveryCandidate(
            question=label,
            goal=goal,
            variables=variables,
            reason=f"Auto-generated from {goal.value.replace('_', ' ')}"
        )

    def _n_levels(self, col: str) -> int:
        """Get number of unique levels for a column."""
        if col in self.df.columns:
            return self.df[col].n_unique()
        return 0

    def _check_eligibility_and_assumptions(self, candidates: list[DiscoveryCandidate]) -> list[DiscoveryCandidate]:
        """Run eligibility checks and assumption diagnostics for each candidate."""
        for cand in candidates:
            # Determine group levels for categorical variables
            group_levels = None
            if cand.goal in (Goal.COMPARE_K_MEANS, Goal.COMPARE_TWO_MEANS):
                group_col = cand.variables.get("group")
                if group_col and group_col in self.df.columns:
                    levels = self.df[group_col].unique().to_list()
                    if len(levels) >= 2:
                        group_levels = [str(v) for v in levels]
            
            # Build analysis request
            request = AnalysisRequest(
                goal=cand.goal,
                variables=cand.variables,
                group_levels=group_levels,
                study_design=StudyDesign.INDEPENDENT,  # Default
                design_confirmation_source="inferred",
                estimand=cand.question,
                missing_policy=MissingPolicy.REQUIRED_COLUMNS_COMPLETE_CASES,
                nonfinite_policy=NonFinitePolicy.EXCLUDE_AND_REPORT,
                method=_select_method(cand.goal),
                alternative=Alternative.TWO_SIDED,
                confidence_level=0.95,
                seed=42,
            )
            
            # Check eligibility
            eligibility = check_eligibility(self.ws, self.dataset_ref, request, self.column_roles_list, self.recipe_steps)
            cand.eligibility = eligibility
            
            if eligibility.allowed:
                # Run assumption diagnostics
                required_cols = list(set(request.variables.values()))
                df_prep = self.df.select(required_cols)
                assumption_report = run_assumption_diagnostics(df_prep, request, self.column_roles)
                cand.assumption_report = assumption_report
                
                # Set suggested method from assumption report
                if assumption_report.recommended_method:
                    cand.eligibility.suggested_method = assumption_report.recommended_method
        
        return candidates

    def _run_candidate_analyses(self, candidates: list[DiscoveryCandidate]) -> list[DiscoveryCandidate]:
        """Run statistical analysis for each eligible candidate."""
        for cand in candidates:
            if not cand.eligibility or not cand.eligibility.allowed:
                continue
            
            # Determine group levels
            group_levels = None
            if cand.goal in (Goal.COMPARE_K_MEANS, Goal.COMPARE_TWO_MEANS):
                group_col = cand.variables.get("group")
                if group_col and group_col in self.df.columns:
                    levels = self.df[group_col].unique().to_list()
                    if len(levels) >= 2:
                        group_levels = [str(v) for v in levels]
            
            request = AnalysisRequest(
                goal=cand.goal,
                variables=cand.variables,
                group_levels=group_levels,
                study_design=StudyDesign.INDEPENDENT,
                design_confirmation_source="inferred",
                estimand=cand.question,
                missing_policy=MissingPolicy.REQUIRED_COLUMNS_COMPLETE_CASES,
                nonfinite_policy=NonFinitePolicy.EXCLUDE_AND_REPORT,
                method=cand.eligibility.suggested_method,
                alternative=Alternative.TWO_SIDED,
                confidence_level=0.95,
                seed=42,
            )
            
            try:
                result = run_analysis(self.ws, self.dataset_ref, request, self.recipe_steps, self.column_roles_list)
                if result.statistical_results:
                    stat = result.statistical_results[0]
                    cand.raw_p_value = stat.p_value
                    cand.q_value = None  # Will be set in BH-FDR step
                    cand.effect_size = stat.effect_size
                    cand.effect_magnitude = abs(stat.effect_size) if stat.effect_size else None
            except Exception as e:
                # Mark as failed
                cand.eligibility = EligibilityResult(
                    allowed=False,
                    reasons=[f"Analysis failed: {str(e)}"],
                    blocked_reason=str(e)
                )
        
        return candidates

    def _apply_bh_fdr(self, candidates: list[DiscoveryCandidate]) -> list[DiscoveryCandidate]:
        """Apply Benjamini-Hochberg FDR correction across all candidates."""
        # Extract valid p-values
        valid_candidates = [c for c in candidates if c.raw_p_value is not None]
        if not valid_candidates:
            return candidates
        
        p_values = [c.raw_p_value for c in valid_candidates]
        m = len(p_values)
        
        # BH procedure
        sorted_indices = np.argsort(p_values)
        sorted_p = np.array(p_values)[sorted_indices]
        
        q_values = np.zeros(m)
        for i, idx in enumerate(sorted_indices):
            q = sorted_p[i] * m / (i + 1)
            q_values[idx] = min(q, 1.0)
        
        # Ensure monotonicity
        for i in range(m - 2, -1, -1):
            q_values[i] = min(q_values[i], q_values[i + 1])
        
        # Assign back
        for i, cand in enumerate(valid_candidates):
            cand.q_value = float(q_values[i])
        
        return candidates

    def _filter_by_significance(self, candidates: list[DiscoveryCandidate]) -> list[DiscoveryCandidate]:
        """Filter candidates by q-value and effect size thresholds."""
        filtered = []
        for cand in candidates:
            # Check q-value
            if cand.q_value is not None and cand.q_value >= self.config.fdr_alpha:
                continue
            
            # Check effect size magnitude
            if cand.effect_magnitude is not None and cand.effect_magnitude < self.config.min_effect_size_threshold:
                continue
            
            filtered.append(cand)
        
        return filtered

    def _compute_composite_score(self, cand: DiscoveryCandidate) -> float:
        """Compute the composite discovery ranking score S(A_i)."""
        if cand.effect_magnitude is None or cand.q_value is None:
            return 0.0
        
        # Normalized effect magnitude (0-1)
        # Map effect sizes to Cohen's thresholds
        effect_norm = min(cand.effect_magnitude / 0.8, 1.0)  # 0.8 = large effect
        
        # Data validity score (1 - missingness - outlier penalty)
        validity = 1.0
        for var in cand.variables.values():
            if var in self.df.columns:
                col = self.df[var]
                missing_pct = col.null_count() / len(col)
                validity -= missing_pct * 0.5
        
        validity = max(0.0, min(1.0, validity))
        
        # Relevance score
        relevance = 0.5  # Base
        if self.target_column and self.target_column in cand.variables.values():
            relevance += self.config.relevance_boost_target
        
        # Interpretability score (prefer simpler comparisons)
        interpretability = 1.0
        if cand.goal in (Goal.COMPARE_K_MEANS, Goal.CATEGORICAL_ASSOCIATION):
            # Penalize many groups/categories
            for var in cand.variables.values():
                if var in self.df.columns:
                    n_unique = self.df[var].n_unique()
                    if n_unique > 6:
                        interpretability *= 0.7
                    if n_unique > 10:
                        interpretability *= 0.5
        
        # FDR-adjusted evidence score
        if cand.q_value < 0.01:
            evidence = 1.0
        elif cand.q_value < 0.05:
            evidence = 0.7
        elif cand.q_value < 0.10:
            evidence = 0.3
        else:
            evidence = 0.0
        
        # Composite score (weights from improvement plan)
        score = 100 * (
            0.30 * effect_norm +
            0.25 * validity +
            0.20 * relevance +
            0.15 * interpretability +
            0.10 * evidence
        )
        
        return score

    def _rank_and_prune(self, candidates: list[DiscoveryCandidate]) -> list[DiscoveryCandidate]:
        """Rank by composite score and apply redundancy pruning."""
        # Compute composite scores
        for cand in candidates:
            cand.composite_score = self._compute_composite_score(cand)
        
        # Sort by composite score descending
        candidates.sort(key=lambda c: c.composite_score or 0, reverse=True)
        
        # Redundancy pruning
        final = []
        for cand in candidates:
            is_redundant = False
            for kept in final:
                if self._are_redundant(cand, kept):
                    is_redundant = True
                    cand.is_redundant = True
                    cand.redundancy_penalty = 0.25
                    break
            
            if not is_redundant:
                final.append(cand)
        
        return final

    def _are_redundant(self, cand1: DiscoveryCandidate, cand2: DiscoveryCandidate) -> bool:
        """Check if two candidates are redundant (same outcome, highly correlated predictors)."""
        # Same outcome variable
        out1 = cand1.variables.get("outcome")
        out2 = cand2.variables.get("outcome")
        
        if out1 != out2:
            return False
        
        # Check if predictors are highly correlated
        pred1 = cand1.variables.get("group") or cand1.variables.get("predictor")
        pred2 = cand2.variables.get("group") or cand2.variables.get("predictor")
        
        if not pred1 or not pred2 or pred1 == pred2:
            return pred1 == pred2
        
        if pred1 not in self.df.columns or pred2 not in self.df.columns:
            return False
        
        # Compute correlation/association between predictors
        try:
            role1 = self.column_roles.get(pred1)
            role2 = self.column_roles.get(pred2)
            
            if role1 in (SemanticRole.CONTINUOUS, SemanticRole.DISCRETE, SemanticRole.ORDINAL) and \
               role2 in (SemanticRole.CONTINUOUS, SemanticRole.DISCRETE, SemanticRole.ORDINAL):
                # Numeric correlation
                x = self.df[pred1].to_numpy()
                y = self.df[pred2].to_numpy()
                # Filter valid
                mask = ~np.isnan(x) & ~np.isnan(y) & ~np.isinf(x) & ~np.isinf(y)
                if mask.sum() > 10:
                    r, _ = stats.pearsonr(x[mask], y[mask])
                    return abs(r) > self.config.redundancy_threshold
            
            elif role1 in (SemanticRole.NOMINAL, SemanticRole.ORDINAL, SemanticRole.BINARY) and \
                 role2 in (SemanticRole.NOMINAL, SemanticRole.ORDINAL, SemanticRole.BINARY):
                # Categorical association (Cramér's V)
                from scipy.stats import chi2_contingency
                ct = self.df.select(pred1, pred2).drop_nulls()
                if ct.height > 10:
                    contingency = ct.group_by(pred1, pred2).len().pivot(
                        values="len", index=pred1, on=pred2
                    ).fill_null(0)
                    if contingency.width > 1 and contingency.height > 1:
                        observed = contingency.select(pl.exclude(pred1)).to_numpy().astype(float)
                        if observed.size > 0:
                            chi2 = chi2_contingency(observed, correction=False)
                            n = observed.sum()
                            min_dim = min(observed.shape) - 1
                            if n > 0 and min_dim > 0:
                                cramers_v = np.sqrt(chi2.statistic / (n * min_dim))
                                return cramers_v > self.config.redundancy_threshold
        except Exception:
            pass
        
        return False


def run_autonomous_discovery(
    workspace: Workspace,
    dataset_ref,
    column_roles: list,
    recipe_steps: list[dict[str, Any]] | None = None,
    target_column: str | None = None,
) -> list[DiscoveryCandidate]:
    """Convenience function to run autonomous discovery."""
    engine = DiscoveryEngine(
        workspace=workspace,
        dataset_ref=dataset_ref,
        column_roles=column_roles,
        recipe_steps=recipe_steps,
        target_column=target_column,
    )
    return engine.run_discovery()