"""Results screen - Display analysis results with standardized 9-part Result Card."""

from __future__ import annotations

import numpy as np
import polars as pl
import streamlit as st

from CleanSheet.contracts import (
    Alternative,
    AnalysisRequest,
    Goal,
    IntervalMethod,
    JobStatus,
    MissingPolicy,
    NonFinitePolicy,
    StudyDesign,
)
from CleanSheet.engine.execution import LazyExecutor, get_or_create_prepared
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.statistics import run_analysis
from CleanSheet.services.visualize import (
    PlotType,
    create_plot_spec,
    generate_plots,
)
from CleanSheet.ui.accessibility import (
    render_skip_link,
    set_page_main_content_id,
    announce_to_screen_reader,
    render_focus_visible_style,
)


def render_results(ws: Workspace) -> None:
    """Render analysis results screen with 9-part Result Card."""
    dataset_ref = st.session_state.get("dataset_ref")
    recipe = st.session_state.get("recipe", [])
    analysis_plan = st.session_state.get("analysis_plan")
    assumption_report = st.session_state.get("assumption_report")
    results = st.session_state.get("results")

    # Accessibility
    render_skip_link()
    render_focus_visible_style()
    set_page_main_content_id()

    if dataset_ref is None or analysis_plan is None:
        st.error("No analysis to display.")
        if st.button("← Back"):
            st.session_state.current_stage = JobStatus.PLAN_READY.value
            st.rerun()
        return

    st.title("📈 Results")
    announce_to_screen_reader("Analysis results page loaded. Review the statistical findings and visualizations.")

    # Run analysis if not done
    if results is None and st.session_state.current_stage == JobStatus.RUNNING.value:
        with st.spinner("Running analysis..."):
            try:
                recipe = st.session_state.get("recipe", [])
                recipe_steps = [s.model_dump() for s in recipe]
                column_roles = st.session_state.get("column_roles", [])
                result = run_analysis(ws, dataset_ref, analysis_plan, recipe_steps, column_roles)
                st.session_state.results = result
                st.session_state.current_stage = JobStatus.COMPLETE.value
                st.rerun()
            except Exception as e:
                st.error(f"Analysis failed: {e}")
                st.session_state.current_stage = JobStatus.FAILED.value
                return

    results = st.session_state.results
    if results is None:
        st.info("Analysis in progress...")
        return

    # Render 9-part Result Card for each statistical result
    for i, stat_result in enumerate(results.statistical_results):
        _render_result_card(stat_result, analysis_plan, assumption_report, i)

    # Generate and display plots
    if "plots" not in st.session_state or not st.session_state.plots:
        _generate_result_plots(ws, dataset_ref, recipe, analysis_plan, results)

    if st.session_state.plots:
        st.divider()
        st.markdown("### Visualizations")
        _render_plots(st.session_state.plots)

    # Navigation
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("← Change question", use_container_width=True):
            st.session_state.current_stage = JobStatus.PLAN_READY.value
            st.session_state.results = None
            st.session_state.plots = []
            if "analysis_plan" in st.session_state:
                del st.session_state.analysis_plan
            if "assumption_report" in st.session_state:
                del st.session_state.assumption_report
            st.rerun()

    with col2:
        if st.button("🔄 Re-run", use_container_width=True):
            st.session_state.current_stage = JobStatus.RUNNING.value
            st.session_state.results = None
            st.rerun()

    with col3:
        if st.button("Download report →", type="primary", use_container_width=True):
            st.session_state.current_stage = JobStatus.EXPORT_READY.value
            st.rerun()


def _render_result_card(stat_result, plan, assumption_report, index: int) -> None:
    """Render a single 9-part Result Card."""
    goal = plan.goal

    # Zone 1: Context & Trust Header Strip
    _render_header_strip(stat_result, assumption_report, index)

    # Zone 2: Question-Led Headline + Zone 3: Plain-Language Finding
    _render_headline_and_finding(stat_result, plan)

    # Zone 4: Primary Visualization (placeholder - actual plot rendered separately)
    st.markdown("### 📊 Visualization")
    st.caption("See visualization section below for the chart.")

    # Zone 5: Effect Magnitude & Uncertainty Strip
    _render_effect_magnitude(stat_result, plan)

    # Zone 6: Data-Quality & Assumption Warnings Banner
    _render_warnings_banner(stat_result, assumption_report)

    # Zone 7: "What Cannot Be Concluded" Boundary Box
    _render_scope_limits(stat_result, plan)

    # Zone 8: Expandable Methods & Technical Details Drawer
    _render_methods_drawer(stat_result, plan)

    # Zone 9: Justified Next Actions & Export Controls
    _render_next_actions(stat_result, plan, index)

    st.divider()


def _render_header_strip(stat_result, assumption_report, index: int) -> None:
    """Render the context header strip."""
    cols = st.columns([2, 2, 2, 2])

    # Analysis mode badge
    with cols[0]:
        st.markdown("**Mode:**")
        if index == 0 and assumption_report and assumption_report.auto_routed:
            st.badge("🔄 Auto-Routed", color="orange")
        else:
            st.badge("👤 Guided", color="blue")

    # Assumption status badge
    with cols[1]:
        st.markdown("**Assumptions:**")
        if assumption_report and assumption_report.auto_routed:
            st.badge("⚠️ Adjusted", color="orange")
        elif assumption_report and assumption_report.has_errors:
            st.badge("🛑 Blocked", color="red")
        else:
            st.badge("✅ Met", color="green")

    # Sample size badge
    with cols[2]:
        st.markdown("**Sample:**")
        n = _get_n_included(stat_result, None)
        st.badge(f"n = {n:,}", color="gray")

    # Method badge
    with cols[3]:
        st.markdown("**Method:**")
        method_name = stat_result.method.value.replace("_", " ").title()
        st.badge(method_name, color="violet")


def _render_headline_and_finding(stat_result, plan) -> None:
    """Render the question-led headline and plain-language finding."""
    goal = plan.goal

    st.markdown("### 🎯 Answer")

    if goal == Goal.COMPARE_TWO_MEANS:
        _render_compare_headline(stat_result, plan)
    elif goal == Goal.COMPARE_K_MEANS:
        _render_k_compare_headline(stat_result, plan)
    elif goal == Goal.COMPARE_PAIRED_MEANS:
        _render_paired_headline(stat_result, plan)
    elif goal in (Goal.EXPLORE_LINEAR_RELATIONSHIP, Goal.EXPLORE_ORDERED_RELATIONSHIP):
        _render_correlation_headline(stat_result, plan)
    elif goal in (Goal.CATEGORICAL_ASSOCIATION, Goal.SPARSE_2X2_TABLE):
        _render_categorical_headline(stat_result, plan)
    else:
        _render_descriptive_headline(stat_result, plan)


def _render_compare_headline(stat_result, plan) -> None:
    """Headline for two-group comparison."""
    outcome = plan.variables.get("outcome", "outcome")
    levels = plan.group_levels or []
    contrast = plan.contrast or ""

    if contrast and "_minus_" in contrast:
        first_label, second_label = contrast.split("_minus_", 1)
    elif len(levels) >= 2:
        first_label, second_label = levels[0], levels[1]
    else:
        first_label, second_label = "Group 1", "Group 2"

    if stat_result.estimate is not None and stat_result.interval and stat_result.interval_status == "computed":
        diff = stat_result.estimate
        direction = "higher" if diff > 0 else "lower"
        higher_label = first_label if diff > 0 else second_label
        lower_label = second_label if diff > 0 else first_label

        st.markdown(f"""
        **In the analyzed data, {higher_label} averaged {abs(diff):.2f} units {direction} than {lower_label} on {outcome}.**

        The {plan.confidence_level:.0%} confidence interval for the difference ({first_label} minus {second_label}) is **[{stat_result.interval[0]:.2f}, {stat_result.interval[1]:.2f}]**.

        *This comparison does not establish that group membership caused the difference.*
        """)
    else:
        st.info("Unable to compute a reliable estimate for this comparison.")


def _render_k_compare_headline(stat_result, plan) -> None:
    """Headline for k-group comparison."""
    outcome = plan.variables.get("outcome", "outcome")
    group = plan.variables.get("group", "group")

    if stat_result.p_value is not None:
        if stat_result.p_value < 0.05:
            st.markdown(f"""
            **There are statistically significant differences in {outcome} across {group}.**  
            The omnibus test indicates at least one group differs from the others (p = {stat_result.p_value:.4f}).

            *See post-hoc comparisons below for specific group differences.*
            """)
        else:
            st.markdown(f"""
            **No statistically significant differences detected in {outcome} across {group}.**  
            The observed differences are consistent with random variation (p = {stat_result.p_value:.4f}).
            """)
    else:
        st.info("Unable to compute a reliable test result.")


def _render_paired_headline(stat_result, plan) -> None:
    """Headline for paired comparison."""
    outcome = plan.variables.get("outcome", "outcome")
    contrast = plan.contrast or ""

    if stat_result.estimate is not None and stat_result.interval and stat_result.interval_status == "computed":
        diff = stat_result.estimate

        if contrast and "_minus_" in contrast:
            first_label, second_label = contrast.split("_minus_", 1)
        else:
            first_label, second_label = "before", "after"

        if diff > 0:
            direction = "higher"
            higher_label = first_label
            lower_label = second_label
        else:
            direction = "lower"
            higher_label = second_label
            lower_label = first_label

        st.markdown(f"""
        **In the analyzed data, {outcome} was {abs(diff):.2f} units {direction} in {higher_label} than in {lower_label}.**  

        The {plan.confidence_level:.0%} confidence interval for the mean paired difference ({first_label} minus {second_label}) is **[{stat_result.interval[0]:.2f}, {stat_result.interval[1]:.2f}]**.

        *This comparison does not establish that the occasion caused the change.*
        """)
    else:
        st.info("Unable to compute a reliable estimate for this comparison.")


def _render_correlation_headline(stat_result, plan) -> None:
    """Headline for correlation."""
    x = plan.variables.get("outcome", "X")
    y = plan.variables.get("predictor", "Y")
    method_name = "Pearson" if stat_result.method.value == "pearson_r" else "Spearman"

    if stat_result.estimate is not None:
        strength = _interpret_strength(abs(stat_result.estimate))
        direction = "positive" if stat_result.estimate > 0 else "negative"

        if stat_result.interval and stat_result.interval_status == "computed":
            interval_text = f"The {plan.confidence_level:.0%} confidence interval is [{stat_result.interval[0]:.3f}, {stat_result.interval[1]:.3f}]."
        else:
            interval_text = "A confidence interval is unavailable for this result."

        st.markdown(f"""
        **There is a {strength} {direction} {method_name} correlation ({stat_result.estimate:.3f}) between {x} and {y}.**  

        {interval_text}

        *Correlation does not imply causation. This analysis does not establish that changes in one variable cause changes in the other.*
        """)
    else:
        st.info("Unable to compute a reliable correlation estimate.")


def _render_categorical_headline(stat_result, plan) -> None:
    """Headline for categorical association."""
    row = plan.variables.get("outcome", "row")
    col = plan.variables.get("group", "column")

    if stat_result.estimate is not None:
        p_text = f"{stat_result.p_value:.4f}" if stat_result.p_value is not None else "Unavailable"
        sig_text = "found a statistically significant association" if stat_result.p_value is not None and stat_result.p_value < 0.05 else "did not find a statistically significant association"

        st.markdown(f"""
        **There is an association between {row} and {col}.**  

        The {stat_result.method.value.replace('_', ' ').title()} test {sig_text} (p = {p_text}).

        *Association does not imply causation.*
        """)
    else:
        st.info("Unable to compute a reliable association estimate.")


def _render_descriptive_headline(stat_result, plan) -> None:
    """Headline for descriptive analysis."""
    st.markdown("""
    **Descriptive statistics for your dataset.**  

    Review the tables and charts below to understand the distribution and quality of your variables.
    """)


def _render_effect_magnitude(stat_result, plan) -> None:
    """Render effect magnitude strip with confidence intervals."""
    st.markdown("### 📏 Effect Magnitude & Uncertainty")

    if stat_result.effect_size is not None:
        cols = st.columns(3)

        # Effect size value
        with cols[0]:
            st.metric(
                "Standardized Effect Size",
                f"{stat_result.effect_size:.3f}",
                help=f"Interpretation: {stat_result.effect_size_interpretation}"
            )

        # Effect size CI if available
        with cols[1]:
            if stat_result.effect_size_ci:
                st.metric(
                    f"{plan.confidence_level:.0%} CI",
                    f"[{stat_result.effect_size_ci[0]:.3f}, {stat_result.effect_size_ci[1]:.3f}]"
                )
            else:
                st.metric("CI", "Not computed")

        # Magnitude label with visual bar
        with cols[2]:
            label = stat_result.effect_magnitude_label or stat_result.effect_size_interpretation or "unknown"
            st.metric("Magnitude", label.title())

            # Visual magnitude bar
            magnitudes = ["negligible", "small", "moderate", "large"]
            if label in magnitudes:
                idx = magnitudes.index(label)
                bar = "█" * (idx + 1) + "░" * (3 - idx)
                st.caption(f"[{bar}]")


def _render_warnings_banner(stat_result, assumption_report) -> None:
    """Render conditional warnings banner."""
    warnings = []

    # Check assumption report
    if assumption_report:
        for check in assumption_report.checks:
            if check.severity == "warning" and check.passed is False:
                warnings.append(check.message)

    # Check for missing data
    if stat_result.exclusions:
        total_excluded = sum(stat_result.exclusions.values())
        if total_excluded > 0:
            warnings.append(f"{total_excluded:,} observations excluded from analysis (missing/non-finite)")

    # Check for multiple testing
    if stat_result.m_comparisons > 1:
        warnings.append(f"Adjusted for {stat_result.m_comparisons} comparisons (method: {stat_result.multiplicity.get('method', 'none') if hasattr(stat_result, 'multiplicity') else 'none'})")

    if warnings:
        with st.container(border=True):
            st.markdown("### ⚠️ Important Considerations")
            for w in warnings:
                st.warning(w)


def _render_scope_limits(stat_result, plan) -> None:
    """Render the 'What Cannot Be Concluded' boundary box."""
    st.markdown("### 🛑 What This Analysis Cannot Prove")

    goal = plan.goal
    collection_type = "observational"

    # Get study context if available
    study_context = st.session_state.get("study_context")
    if study_context:
        collection_type = study_context.collection_type

    limits = []

    if goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS, Goal.COMPARE_PAIRED_MEANS):
        if collection_type == "observational":
            limits.append("Because this is observational data, this analysis shows that groups differ, **NOT** that group membership causes the difference. Unmeasured confounding variables could explain the observed effect.")
        limits.append("The confidence interval reflects sampling uncertainty, not the probability that the true effect lies in the interval.")
        if stat_result.effect_size is not None and abs(stat_result.effect_size) < 0.2:
            limits.append("The effect size is negligible — even if statistically significant, the practical importance may be minimal.")

    elif goal in (Goal.EXPLORE_LINEAR_RELATIONSHIP, Goal.EXPLORE_ORDERED_RELATIONSHIP):
        limits.append("**Correlation does not imply causation.** This analysis does not establish that changes in one variable cause changes in the other.")
        limits.append("The relationship may be explained by a third variable not included in this analysis (confounding).")
        limits.append("Do not extrapolate beyond the observed range of the data.")

    elif goal in (Goal.CATEGORICAL_ASSOCIATION, Goal.SPARSE_2X2_TABLE):
        if collection_type == "observational":
            limits.append("Association does not imply causation. The relationship may be due to confounding or selection effects.")
        limits.append("Do not assume that changing one variable will change the other.")

    else:
        limits.append("Descriptive summaries do not support inferential conclusions about populations or causal relationships.")

    # Always include these
    limits.append("Results are based on the cleaned/prepared dataset — original raw data may differ.")
    limits.append(f"Missing data handled via {plan.missing_policy.value}; results may be biased if missingness is not at random.")

    for limit in limits:
        st.markdown(f"- {limit}")


def _render_methods_drawer(stat_result, plan) -> None:
    """Render expandable technical details."""
    with st.expander("📐 Technical Details & Methods"):
        st.markdown(f"**Method:** {stat_result.method.value.replace('_', ' ').title()}")

        if stat_result.statistic is not None:
            st.markdown(f"**Test Statistic:** {stat_result.statistic:.4f}")
        if stat_result.degrees_of_freedom is not None:
            st.markdown(f"**Degrees of Freedom:** {stat_result.degrees_of_freedom}")
        if stat_result.p_value is not None:
            p_text = f"{stat_result.p_value:.6f}" if stat_result.p_value >= 0.0001 else "< 0.0001"
            st.markdown(f"**P-value:** {p_text}")
        if stat_result.adjusted_p_value is not None:
            st.markdown(f"**Adjusted P-value:** {stat_result.adjusted_p_value:.6f}")
        if stat_result.q_value is not None:
            st.markdown(f"**FDR q-value:** {stat_result.q_value:.6f}")

        # Effect size details
        if stat_result.effect_size is not None:
            st.markdown(f"**Effect Size ({stat_result.effect_size_interpretation}):** {stat_result.effect_size:.4f}")
        if stat_result.unstandardized_effect is not None:
            st.markdown(f"**Unstandardized Effect:** {stat_result.unstandardized_effect:.4f}")

        # Interval details
        if stat_result.interval and stat_result.interval_status == "computed":
            st.markdown(f"**{plan.confidence_level:.0%} CI:** [{stat_result.interval[0]:.4f}, {stat_result.interval[1]:.4f}]")
            st.markdown(f"**Interval Method:** {stat_result.interval_method.value}")

        # Assumption checks
        if stat_result.assumption_checks:
            st.markdown("**Assumption Diagnostics:**")
            for k, v in stat_result.assumption_checks.items():
                if isinstance(v, dict):
                    st.markdown(f"- **{k}**:")
                    for k2, v2 in v.items():
                        st.markdown(f"  - {k2}: {v2}")
                else:
                    st.markdown(f"- **{k}**: {v}")

        # Exclusions
        if stat_result.exclusions:
            st.markdown("**Exclusions:**")
            for k, v in stat_result.exclusions.items():
                st.markdown(f"- {k}: {v}")

        # APA-style citation
        st.markdown("**APA-style citation:**")
        _render_apa_citation(stat_result, plan)


def _render_apa_citation(stat_result, plan) -> None:
    """Generate APA-style statistical citation."""
    method = stat_result.method.value
    goal = plan.goal

    if method == "welch_t":
        df_str = f"{stat_result.degrees_of_freedom:.1f}" if stat_result.degrees_of_freedom else "?"
        st.code(f"t({df_str}) = {stat_result.statistic:.2f}, p = {stat_result.p_value:.4f}, Hedges' g = {stat_result.effect_size:.2f}, 95% CI [{stat_result.interval[0]:.2f}, {stat_result.interval[1]:.2f}]")
    elif method == "paired_t":
        st.code(f"t({int(stat_result.degrees_of_freedom)}) = {stat_result.statistic:.2f}, p = {stat_result.p_value:.4f}, Hedges' g = {stat_result.effect_size:.2f}, 95% CI [{stat_result.interval[0]:.2f}, {stat_result.interval[1]:.2f}]")
    elif method == "mann_whitney_u":
        st.code(f"U = {stat_result.statistic:.0f}, p = {stat_result.p_value:.4f}, rank-biserial r = {stat_result.effect_size:.2f}, Hodges-Lehmann median difference = {stat_result.estimate:.2f}")
    elif method == "wilcoxon_signed_rank":
        st.code(f"W = {stat_result.statistic:.0f}, p = {stat_result.p_value:.4f}, matched rank-biserial r = {stat_result.effect_size:.2f}, Hodges-Lehmann median difference = {stat_result.estimate:.2f}")
    elif method == "kruskal_wallis":
        st.code(f"H({int(stat_result.degrees_of_freedom)}) = {stat_result.statistic:.2f}, p = {stat_result.p_value:.4f}, ε² = {stat_result.effect_size:.3f}")
    elif method in ("pearson_r", "spearman_rho"):
        name = "Pearson r" if method == "pearson_r" else "Spearman ρ"
        st.code(f"{name}({int(stat_result.degrees_of_freedom) if stat_result.degrees_of_freedom else '?'}) = {stat_result.estimate:.3f}, p = {stat_result.p_value:.4f}, 95% CI [{stat_result.interval[0]:.3f}, {stat_result.interval[1]:.3f}]")
    elif method == "chi2_independence":
        st.code(f"χ²({int(stat_result.degrees_of_freedom)}) = {stat_result.statistic:.2f}, p = {stat_result.p_value:.4f}, Cramér's V = {stat_result.effect_size:.3f}")
    elif method == "fisher_exact":
        st.code(f"Fisher's exact test: p = {stat_result.p_value:.4f}, OR = {stat_result.estimate:.2f}")
    else:
        st.code("Descriptive statistics only")


def _render_next_actions(stat_result, plan, index: int) -> None:
    """Render suggested follow-up actions."""
    st.markdown("### 🔍 Suggested Next Steps")

    actions = []

    # Sensitivity check for outliers
    if stat_result.assumption_checks.get("outliers", {}).get("passed") is False:
        actions.append({
            "label": "🧪 Re-run without outliers",
            "description": "Check if conclusion holds when extreme values are excluded",
            "key": f"sensitivity_{index}",
            "type": "sensitivity",
        })

    # Post-hoc for k-groups
    if plan.goal == Goal.COMPARE_K_MEANS and stat_result.p_value is not None and stat_result.p_value < 0.05:
        actions.append({
            "label": "📊 View pairwise comparisons",
            "description": "See which specific groups differ significantly",
            "key": f"posthoc_{index}",
            "type": "posthoc",
        })

    # Confounder check
    if plan.goal in (Goal.COMPARE_TWO_MEANS, Goal.EXPLORE_LINEAR_RELATIONSHIP):
        actions.append({
            "label": "🔍 Check for confounding",
            "description": "Stratify by potential confounders (e.g., region, time period)",
            "key": f"confounder_{index}",
            "type": "confounder",
        })

    # Subgroup analysis
    if plan.goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS):
        actions.append({
            "label": "📈 Subgroup analysis",
            "description": "Check if effect varies across subgroups",
            "key": f"subgroup_{index}",
            "type": "subgroup",
        })

    if actions:
        cols = st.columns(min(len(actions), 3))
        for i, action in enumerate(actions):
            with cols[i % 3]:
                if st.button(action["label"], key=action["key"], use_container_width=True):
                    _handle_followup_action(action["type"], stat_result, plan, index, ws, dataset_ref, recipe, column_roles)
    else:
        st.caption("No specific follow-ups suggested for this analysis.")


def _handle_followup_action(action_type: str, stat_result, plan, index: int, ws, dataset_ref, recipe, column_roles) -> None:
    """Handle follow-up action buttons."""
    if action_type == "sensitivity":
        _run_sensitivity_analysis(stat_result, plan, index, ws, dataset_ref, recipe, column_roles)
    elif action_type == "posthoc":
        st.info("Pairwise comparisons are already shown in the post-hoc results above.")
    elif action_type == "confounder":
        _run_confounder_check(stat_result, plan, index, ws, dataset_ref, recipe, column_roles)
    elif action_type == "subgroup":
        _run_subgroup_analysis(stat_result, plan, index, ws, dataset_ref, recipe, column_roles)


def _run_confounder_check(stat_result, plan, index: int, ws, dataset_ref, recipe, column_roles) -> None:
    """Run Simpson's Paradox / Confounder detection and stratified analysis.
    
    Identifies third variables that:
    1. Are associated with both X and Y
    2. When stratified by, change the direction or magnitude of the X-Y relationship
    """
    from CleanSheet.services.statistics import run_analysis
    from CleanSheet.engine.execution import LazyExecutor
    from CleanSheet.contracts import Goal, StudyDesign, Alternative, MissingPolicy, NonFinitePolicy
    import numpy as np
    
    st.markdown("---")
    st.markdown("### 🔍 Confounder / Simpson's Paradox Check")
    st.caption("Testing whether a third variable explains or reverses the observed relationship...")
    
    # Get variables from the analysis
    goal = plan.goal
    vars_ = plan.variables
    
    if goal not in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS, Goal.EXPLORE_LINEAR_RELATIONSHIP, Goal.EXPLORE_ORDERED_RELATIONSHIP):
        st.info("Confounder check available for group comparisons and correlation analyses.")
        return
    
    # Identify X and Y
    if goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS):
        x_var = vars_.get("group")      # Predictor (categorical)
        y_var = vars_.get("outcome")    # Outcome (numeric)
        x_type = "categorical"
        y_type = "numeric"
    else:
        x_var = vars_.get("outcome")    # X
        y_var = vars_.get("predictor")  # Y
        x_type = "numeric"
        y_type = "numeric"
    
    if not x_var or not y_var:
        st.warning("Cannot identify variables for confounder check.")
        return
    
    # Load full data
    executor = LazyExecutor(ws, dataset_ref)
    df = get_or_create_prepared(ws, dataset_ref, [s.model_dump() for s in recipe]) if recipe else executor.preview(10000)
    
    # Find candidate confounders: categorical variables associated with both X and Y
    candidate_confounders = []
    
    for cr in column_roles:
        z_var = cr.column
        if z_var in [x_var, y_var]:
            continue
        if z_var not in df.columns:
            continue
        
        z_role = cr.semantic_role
        if z_role.value not in ("nominal", "ordinal", "binary"):
            continue
        
        # Check if Z is associated with X
        x_assoc_p = _test_association(df, z_var, x_var)
        if x_assoc_p is None or x_assoc_p >= 0.1:
            continue
        
        # Check if Z is associated with Y
        y_assoc_p = _test_association(df, z_var, y_var)
        if y_assoc_p is None or y_assoc_p >= 0.1:
            continue
        
        candidate_confounders.append({
            "variable": z_var,
            "x_assoc_p": x_assoc_p,
            "y_assoc_p": y_assoc_p,
            "n_levels": df[z_var].n_unique(),
        })
    
    if not candidate_confounders:
        st.success("✅ **No confounders detected**: No third variable in your data is associated with both X and Y at p < 0.1.")
        return
    
    # Sort by combined association strength
    candidate_confounders.sort(key=lambda c: c["x_assoc_p"] * c["y_assoc_p"])
    
    st.markdown(f"**Found {len(candidate_confounders)} potential confounder(s):**")
    
    for conf in candidate_confounders[:3]:  # Top 3
        with st.container(border=True):
            st.markdown(f"**Potential Confounder: `{conf['variable']}`** ({conf['n_levels']} levels)")
            st.caption(f"Association with X: p = {conf['x_assoc_p']:.4f} | Association with Y: p = {conf['y_assoc_p']:.4f}")
            
            if st.button(f"🔍 Stratify by `{conf['variable']}`", key=f"stratify_{index}_{conf['variable']}", type="primary"):
                _run_stratified_analysis(plan, x_var, y_var, conf['variable'], ws, dataset_ref, recipe, column_roles)


def _test_association(df: pl.DataFrame, var1: str, var2: str) -> float | None:
    """Test association between two variables, return p-value."""
    from scipy import stats
    import numpy as np
    
    if var1 not in df.columns or var2 not in df.columns:
        return None
    
    # Determine types
    s1 = df[var1]
    s2 = df[var2]
    
    is_cat1 = s1.dtype in (pl.String, pl.Categorical) or s1.n_unique() / len(s1) < 0.05
    is_cat2 = s2.dtype in (pl.String, pl.Categorical) or s2.n_unique() / len(s2) < 0.05
    
    try:
        if is_cat1 and is_cat2:
            # Chi-square
            ct = df.select(var1, var2).drop_nulls()
            if ct.height < 5:
                return None
            contingency = ct.group_by(var1, var2).len().pivot(
                values="len", index=var1, on=var2
            ).fill_null(0)
            observed = contingency.select(pl.exclude(var1)).to_numpy().astype(float)
            if observed.size < 4:
                return None
            _, p, _, _ = stats.chi2_contingency(observed, correction=False)
            return p
        elif is_cat1 and not is_cat2:
            # ANOVA / Kruskal-Wallis
            clean = df.select(var1, var2).drop_nulls()
            if clean.height < 5:
                return None
            groups = [g[var2].to_numpy() for _, g in clean.group_by(var1)]
            groups = [g for g in groups if len(g) >= 2]
            if len(groups) < 2:
                return None
            _, p = stats.f_oneway(*groups)
            return p
        elif not is_cat1 and is_cat2:
            # ANOVA / Kruskal-Wallis (reversed)
            return _test_association(df, var2, var1)
        else:
            # Correlation
            clean = df.select(var1, var2).drop_nulls()
            clean = clean.filter(
                ~pl.col(var1).is_infinite() & ~pl.col(var1).is_nan() &
                ~pl.col(var2).is_infinite() & ~pl.col(var2).is_nan()
            )
            if clean.height < 5:
                return None
            x = clean[var1].to_numpy()
            y = clean[var2].to_numpy()
            _, p = stats.pearsonr(x, y)
            return p
    except Exception:
        return None


def _run_stratified_analysis(plan, x_var: str, y_var: str, z_var: str, ws, dataset_ref, recipe, column_roles) -> None:
    """Run the original analysis stratified by Z and show results."""
    from CleanSheet.services.statistics import run_analysis
    from CleanSheet.contracts import Goal, StudyDesign, Alternative, MissingPolicy, NonFinitePolicy
    from CleanSheet.engine.execution import LazyExecutor
    
    st.markdown("---")
    st.markdown(f"### 📊 Stratified Analysis by `{z_var}`")
    
    executor = LazyExecutor(ws, dataset_ref)
    df = get_or_create_prepared(ws, dataset_ref, [s.model_dump() for s in recipe]) if recipe else executor.preview(10000)
    
    if z_var not in df.columns:
        st.warning(f"Stratification variable `{z_var}` not found in data.")
        return
    
    levels = df[z_var].unique().to_list()
    if len(levels) > 6:
        st.warning(f"Too many levels ({len(levels)}) in `{z_var}` for stratified display. Consider grouping rare levels.")
        levels = levels[:6]
    
    goal = plan.goal
    
    strata_results = []
    
    for level in levels:
        stratum_df = df.filter(pl.col(z_var) == level)
        
        if len(stratum_df) < 5:
            st.caption(f"Skipping `{level}` (n={len(stratum_df)} < 5)")
            continue
        
        # Build request for this stratum
        if goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS):
            request = AnalysisRequest(
                goal=Goal.COMPARE_TWO_MEANS if df[x_var].n_unique() == 2 else Goal.COMPARE_K_MEANS,
                variables={"outcome": y_var, "group": x_var},
                group_levels=None,
                study_design=StudyDesign.INDEPENDENT,
                design_confirmation_source="inferred",
                estimand=f"Stratum: {z_var} = {level}",
                missing_policy=MissingPolicy.REQUIRED_COLUMNS_COMPLETE_CASES,
                nonfinite_policy=NonFinitePolicy.EXCLUDE_AND_REPORT,
                alternative=Alternative.TWO_SIDED,
                confidence_level=0.95,
                seed=42,
            )
        else:
            request = AnalysisRequest(
                goal=Goal.EXPLORE_LINEAR_RELATIONSHIP,
                variables={"outcome": x_var, "predictor": y_var},
                study_design=StudyDesign.INDEPENDENT,
                design_confirmation_source="inferred",
                estimand=f"Stratum: {z_var} = {level}",
                missing_policy=MissingPolicy.REQUIRED_COLUMNS_COMPLETE_CASES,
                nonfinite_policy=NonFinitePolicy.EXCLUDE_AND_REPORT,
                alternative=Alternative.TWO_SIDED,
                confidence_level=0.95,
                seed=42,
            )
        
        try:
            result = run_analysis(ws, dataset_ref, request, None, column_roles)
            if result.statistical_results:
                stat = result.statistical_results[0]
                strata_results.append({
                    "level": str(level),
                    "n": len(stratum_df),
                    "estimate": stat.estimate,
                    "ci": stat.interval,
                    "p_value": stat.p_value,
                    "effect_size": stat.effect_size,
                })
        except Exception as e:
            st.caption(f"Stratum `{level}` failed: {e}")
    
    if not strata_results:
        st.warning("No valid strata produced results.")
        return
    
    # Display results table
    st.markdown("**Stratum-Specific Results:**")
    
    import pandas as pd
    display_df = pd.DataFrame([{
        f"`{z_var}` Level": r["level"],
        "n": r["n"],
        "Estimate": f"{r['estimate']:.4f}" if r["estimate"] is not None else "N/A",
        "95% CI": f"[{r['ci'][0]:.4f}, {r['ci'][1]:.4f}]" if r["ci"] else "N/A",
        "P-value": f"{r['p_value']:.4f}" if r["p_value"] is not None else "N/A",
        "Effect Size": f"{r['effect_size']:.4f}" if r["effect_size"] is not None else "N/A",
    } for r in strata_results])
    st.dataframe(display_df, hide_index=True, use_container_width=True)
    
    # Check for Simpson's Paradox
    _check_simpsons_paradox(strata_results, plan, x_var, y_var, z_var)


def _check_simpsons_paradox(strata_results, plan, x_var, y_var, z_var):
    """Check if direction of effect reverses across strata."""
    # Get overall effect direction
    overall_estimate = None
    for stat in plan.__dict__.get("statistical_results", []):
        if stat.estimate is not None:
            overall_estimate = stat.estimate
            break
    
    if overall_estimate is None:
        return
    
    overall_sign = 1 if overall_estimate > 0 else (-1 if overall_estimate < 0 else 0)
    if overall_sign == 0:
        return
    
    # Check stratum signs
    stratum_signs = []
    for r in strata_results:
        if r["estimate"] is not None:
            s = 1 if r["estimate"] > 0 else (-1 if r["estimate"] < 0 else 0)
            if s != 0:
                stratum_signs.append(s)
    
    if not stratum_signs:
        return
    
    # Simpson's paradox: all strata have opposite sign to overall
    opposite_signs = sum(1 for s in stratum_signs if s != overall_sign)
    if opposite_signs == len(stratum_signs) and len(stratum_signs) > 1:
        st.error(f"🚨 **Simpson's Paradox Detected!** The overall effect is {overall_sign:+d} but ALL {len(stratum_signs)} strata show the opposite direction ({-overall_sign:+d}). The variable `{z_var}` is a strong confounder.")
    elif opposite_signs > 0:
        st.warning(f"⚠️ **Partial Reversal**: {opposite_signs} of {len(stratum_signs)} strata show opposite direction to overall effect. Variable `{z_var}` may be a confounder.")
    else:
        st.success(f"✅ **Consistent Direction**: All {len(stratum_signs)} strata show the same direction as the overall effect ({overall_sign:+d}).")


def _run_subgroup_analysis(stat_result, plan, index: int, ws, dataset_ref, recipe, column_roles) -> None:
    """Run subgroup analysis - similar to confounder check but user-guided."""
    st.markdown("---")
    st.markdown("### 📈 Subgroup Analysis")
    st.caption("Select a variable to test whether the effect varies across its levels.")
    
    # Get available stratification variables
    executor = LazyExecutor(ws, dataset_ref)
    df = get_or_create_prepared(ws, dataset_ref, [s.model_dump() for s in recipe]) if recipe else executor.preview(10000)
    
    # Categorical variables only
    strat_vars = []
    for cr in column_roles:
        if cr.semantic_role.value in ("nominal", "ordinal", "binary"):
            if cr.column in df.columns:
                n_levels = df[cr.column].n_unique()
                if 2 <= n_levels <= 10:
                    strat_vars.append((cr.column, n_levels))
    
    if not strat_vars:
        st.info("No suitable categorical variables for subgroup analysis (need 2-10 levels).")
        return
    
    selected = st.selectbox(
        "Stratify by:",
        options=[v[0] for v in strat_vars],
        format_func=lambda x: f"{x} ({dict(strat_vars)[x]} levels)",
        key=f"subgroup_var_{index}",
    )
    
    if st.button(f"Run Subgroup Analysis by `{selected}`", key=f"run_subgroup_{index}", type="primary"):
        # Determine X and Y
        goal = plan.goal
        if goal in (Goal.COMPARE_TWO_MEANS, Goal.COMPARE_K_MEANS):
            x_var = plan.variables.get("group")
            y_var = plan.variables.get("outcome")
        else:
            x_var = plan.variables.get("outcome")
            y_var = plan.variables.get("predictor")
        
        _run_stratified_analysis(plan, x_var, y_var, selected, ws, dataset_ref, recipe, column_roles)


def _run_sensitivity_analysis(stat_result, plan, index: int, ws, dataset_ref, recipe, column_roles) -> None:
    """Run sensitivity analysis excluding outliers and show comparison."""
    from CleanSheet.services.statistics import run_analysis
    from CleanSheet.engine.execution import LazyExecutor
    import numpy as np
    
    # Check if outliers were flagged
    outlier_check = stat_result.assumption_checks.get("outliers", {})
    if outlier_check.get("passed") is not False:
        st.info("No outliers were flagged in the original analysis.")
        return
    
    # Get the outcome variable and find outlier bounds
    outcome_col = plan.variables.get("outcome")
    if not outcome_col:
        st.warning("Cannot determine outcome variable for sensitivity analysis.")
        return
    
    # Load data to compute outlier bounds
    executor = LazyExecutor(ws, dataset_ref)
    df = get_or_create_prepared(ws, dataset_ref, [s.model_dump() for s in recipe]) if recipe else executor.preview(10000)
    
    if outcome_col not in df.columns:
        st.warning(f"Outcome column '{outcome_col}' not found in data.")
        return
    
    # Compute IQR bounds
    finite = df.filter(
        pl.col(outcome_col).is_not_null() &
        ~pl.col(outcome_col).is_infinite() &
        ~pl.col(outcome_col).is_nan()
    )
    
    if len(finite) < 10:
        st.warning("Insufficient data for sensitivity analysis.")
        return
    
    vals = finite[outcome_col].to_numpy()
    q1 = np.percentile(vals, 25)
    q3 = np.percentile(vals, 75)
    iqr = q3 - q1
    lower = q1 - 3 * iqr
    upper = q3 + 3 * iqr
    
    # Filter outliers
    df_no_outliers = finite.filter(
        (pl.col(outcome_col) >= lower) & (pl.col(outcome_col) <= upper)
    )
    
    n_removed = len(finite) - len(df_no_outliers)
    if n_removed == 0:
        st.info("No outliers to remove.")
        return
    
    # Store outlier bounds for use in filtered analysis
    st.session_state[f"sensitivity_bounds_{index}"] = {
        "outcome_col": outcome_col,
        "lower": float(lower),
        "upper": float(upper),
        "n_removed": n_removed,
    }
    
    # Run analysis on filtered data
    with st.spinner("Running sensitivity analysis..."):
        try:
            # Create a temporary filter recipe
            filter_recipe = recipe + [{
                "operation": "filter",
                "arguments": {
                    "expression": f"(pl.col('{outcome_col}') >= {lower}) & (pl.col('{outcome_col}') <= {upper})"
                },
                "input_schema": {},
                "output_schema": {},
                "affected_row_count": len(df_no_outliers),
                "affected_column_count": 0,
                "step_id": len(recipe),
                "operation_type": "filter",
                "timestamp": "2026-10-27T00:00:00",
                "reversible": True,
            }]
            
            filtered_result = run_analysis(
                ws, dataset_ref, plan, 
                [s.model_dump() for s in filter_recipe],
                column_roles
            )
            
            if filtered_result.statistical_results:
                filtered_stat = filtered_result.statistical_results[0]
                _render_sensitivity_comparison(stat_result, filtered_stat, plan, n_removed, lower, upper)
            else:
                st.warning("Sensitivity analysis did not produce results.")
        except Exception as e:
            st.error(f"Sensitivity analysis failed: {e}")


def _render_sensitivity_comparison(original_stat, filtered_stat, plan, n_removed: int, lower: float, upper: float) -> None:
    """Render side-by-side sensitivity comparison."""
    st.markdown("---")
    st.markdown(f"### 🧪 Sensitivity Analysis: Excluding {n_removed} Outlier(s)")
    st.caption(f"Outliers defined as values outside [{lower:.2f}, {upper:.2f}] (3×IQR)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Original (with outliers)**")
        if original_stat.estimate is not None:
            st.metric("Estimate", f"{original_stat.estimate:.4f}")
        if original_stat.interval and original_stat.interval_status == "computed":
            st.metric(f"{plan.confidence_level:.0%} CI", f"[{original_stat.interval[0]:.4f}, {original_stat.interval[1]:.4f}]")
        if original_stat.p_value is not None:
            p_text = f"{original_stat.p_value:.6f}" if original_stat.p_value >= 0.001 else "< 0.001"
            st.metric("P-value", p_text)
        if original_stat.effect_size is not None:
            st.metric("Effect Size", f"{original_stat.effect_size:.4f} ({original_stat.effect_size_interpretation})")
    
    with col2:
        st.markdown("**Filtered (outliers excluded)**")
        if filtered_stat.estimate is not None:
            delta = filtered_stat.estimate - original_stat.estimate if original_stat.estimate else 0
            st.metric("Estimate", f"{filtered_stat.estimate:.4f}", delta=f"{delta:+.4f}")
        if filtered_stat.interval and filtered_stat.interval_status == "computed":
            st.metric(f"{plan.confidence_level:.0%} CI", f"[{filtered_stat.interval[0]:.4f}, {filtered_stat.interval[1]:.4f}]")
        if filtered_stat.p_value is not None:
            p_text = f"{filtered_stat.p_value:.6f}" if filtered_stat.p_value >= 0.001 else "< 0.001"
            delta_p = filtered_stat.p_value - original_stat.p_value if original_stat.p_value else 0
            st.metric("P-value", p_text, delta=f"{delta_p:+.6f}")
        if filtered_stat.effect_size is not None:
            delta_es = filtered_stat.effect_size - original_stat.effect_size if original_stat.effect_size else 0
            st.metric("Effect Size", f"{filtered_stat.effect_size:.4f} ({filtered_stat.effect_size_interpretation})", delta=f"{delta_es:+.4f}")
    
    # Determine robustness
    conclusion_changed = False
    if original_stat.p_value is not None and filtered_stat.p_value is not None:
        orig_sig = original_stat.p_value < 0.05
        filt_sig = filtered_stat.p_value < 0.05
        if orig_sig != filt_sig:
            conclusion_changed = True
    
    if conclusion_changed:
        st.error("⚠️ **Conclusion Changed**: The statistical significance differs when outliers are excluded. Results may not be robust.")
    else:
        st.success("✅ **Robust**: The conclusion (significant / not significant) remains the same after excluding outliers.")
        if original_stat.estimate is not None and filtered_stat.estimate is not None:
            pct_change = abs((filtered_stat.estimate - original_stat.estimate) / original_stat.estimate * 100) if original_stat.estimate != 0 else 0
            if pct_change < 10:
                st.caption(f"Effect size changed by only {pct_change:.1f}% — minimal practical impact.")
            else:
                st.warning(f"⚠️ Effect size changed by {pct_change:.1f}% — consider reporting both results.")


def _interpret_strength(r: float) -> str:
    """Interpret correlation strength."""
    if r < 0.1:
        return "negligible"
    elif r < 0.3:
        return "weak"
    elif r < 0.5:
        return "moderate"
    elif r < 0.7:
        return "strong"
    else:
        return "very strong"


def _get_n_included(stat_result, plan) -> int:
    """Get the correct number of included observations based on analysis method."""
    method = stat_result.method.value
    counts = stat_result.group_counts

    if method == "welch_t":
        return sum(counts.values())
    elif method == "paired_t":
        return counts.get("pairs", sum(counts.values()))
    elif method in ("pearson_r", "spearman_rho"):
        return counts.get("n", sum(counts.values()))
    elif method in ("chi2_independence", "fisher_exact"):
        return counts.get("n", sum(counts.values()))
    elif method == "descriptive":
        return counts.get("n_rows", sum(counts.values()))
    else:
        return sum(counts.values())


def _generate_result_plots(
    ws: Workspace,
    dataset_ref,
    recipe: list,
    plan,
    results,
) -> None:
    """Generate plots for the analysis results."""
    executor = LazyExecutor(ws, dataset_ref)
    df = get_or_create_prepared(ws, dataset_ref, [s.model_dump() for s in recipe]) if recipe else executor.preview(10000)

    plot_specs = []

    for stat_result in results.statistical_results:
        if stat_result.method.value == "welch_t":
            # Boxplot by group
            plot_specs.append(create_plot_spec(
                PlotType.BOXPLOT,
                {"x": plan.variables["group"], "y": plan.variables["outcome"]},
                df,
                max_points=5000,
            ))
            # Estimate with CI
            if stat_result.interval:
                plot_specs.append(create_plot_spec(
                    PlotType.ESTIMATE_INTERVAL,
                    {},
                    df,
                    transform={
                        "estimates": [{
                            "label": f"{plan.variables['group']} diff",
                            "estimate": stat_result.estimate,
                            "lower": stat_result.interval[0],
                            "upper": stat_result.interval[1],
                        }]
                    },
                ))

        elif stat_result.method.value == "paired_t":
            # Paired slope plot
            plot_specs.append(create_plot_spec(
                PlotType.PAIRED_SLOPE,
                {"x": plan.variables["occasion"], "y": plan.variables["outcome"]},
                df,
                max_points=5000,
            ))

        elif stat_result.method.value in ("pearson_r", "spearman_rho"):
            # Scatterplot
            plot_specs.append(create_plot_spec(
                PlotType.SCATTERPLOT,
                {"x": plan.variables["outcome"], "y": plan.variables["predictor"]},
                df,
                max_points=5000,
            ))

        elif stat_result.method.value in ("chi2_independence", "fisher_exact"):
            # Count chart
            plot_specs.append(create_plot_spec(
                PlotType.COUNT_CHART,
                {"x": plan.variables["group"], "hue": plan.variables["outcome"]},
                df,
            ))

        elif stat_result.method.value == "kruskal_wallis":
            # Raincloud plot
            plot_specs.append(create_plot_spec(
                PlotType.RAINCLOUD,
                {"x": plan.variables["group"], "y": plan.variables["outcome"]},
                df,
                max_points=5000,
            ))

    # Generate plots
    if plot_specs:
        with st.spinner("Generating visualizations..."):
            try:
                plot_results = generate_plots(ws, dataset_ref, plot_specs)
                st.session_state.plots = plot_results
            except Exception as e:
                st.warning(f"Could not generate plots: {e}")
                st.session_state.plots = []


def _render_plots(plots) -> None:
    """Render plot results with accessible data table fallback."""
    for plot in plots:
        # Render the chart
        st.image(
            plot.png_bytes, 
            caption=f"{plot.spec.plot_type.value.replace('_', ' ').title()}", 
            width="stretch"
        )
        
        # Download button
        col1, col2 = st.columns([1, 3])
        with col1:
            st.download_button(
                "⬇️ Download PNG",
                data=plot.png_bytes,
                file_name=f"plot_{plot.spec.plot_type.value}.png",
                mime="image/png",
                key=f"dl_{id(plot)}",
            )
        
        # Accessible data table fallback
        _render_accessible_plot_table(plot)


def _render_accessible_plot_table(plot) -> None:
    """Render an accessible table representation of the plot data.
    
    This provides a keyboard-navigable, screen-reader-friendly alternative
    to the visual chart.
    """
    # Generate summary data from the plot specification
    spec = plot.spec
    vars_map = spec.variables
    
    with st.expander("📋 View Chart Data as Accessible Table", expanded=False):
        st.markdown(f"**Chart Type:** {spec.plot_type.value.replace('_', ' ').title()}")
        st.markdown(f"**Variables:** {', '.join(f'{k}={v}' for k, v in vars_map.items() if v)}")
        
        # Generate a descriptive text summary
        summary = _generate_plot_text_summary(plot)
        st.markdown(f"**Description:** {summary}")
        
        # Provide downloadable CSV of the underlying data
        csv_data = _generate_plot_csv(plot)
        if csv_data:
            st.download_button(
                "⬇️ Download Data as CSV",
                data=csv_data,
                file_name=f"plot_{spec.plot_type.value}_data.csv",
                mime="text/csv",
                key=f"dl_csv_{id(plot)}",
            )


def _generate_plot_text_summary(plot) -> str:
    """Generate a human-readable text summary of the plot."""
    spec = plot.spec
    vars_map = spec.variables
    plot_type = spec.plot_type.value
    
    # Build context
    parts = []
    if "x" in vars_map and vars_map["x"]:
        parts.append(f"X-axis: {vars_map['x']}")
    if "y" in vars_map and vars_map["y"]:
        parts.append(f"Y-axis: {vars_map['y']}")
    if "hue" in vars_map and vars_map["hue"]:
        parts.append(f"Grouped by: {vars_map['hue']}")
    if "col" in vars_map and vars_map["col"]:
        parts.append(f"Facets: {vars_map['col']}")
    
    context = "; ".join(parts) if parts else "No variables specified"
    
    type_descriptions = {
        "histogram": "A histogram showing the distribution of values",
        "ecdf": "An empirical cumulative distribution function plot",
        "boxplot": "A box plot showing distribution quartiles and outliers",
        "raincloud": "A raincloud plot combining box plot, violin plot, and raw data points",
        "strip_plot": "A strip plot showing individual data points",
        "scatterplot": "A scatter plot showing the relationship between two variables",
        "paired_slope": "A slope graph showing paired before/after measurements",
        "spaghetti": "A spaghetti plot showing individual trajectories over time",
        "count_chart": "A bar chart showing counts per category",
        "correlation_heatmap": "A heatmap showing correlations between variables",
        "missingness_matrix": "A heatmap showing missing data patterns",
        "estimate_interval": "A point estimate with confidence interval",
    }
    
    desc = type_descriptions.get(plot_type, f"A {plot_type} chart")
    return f"{desc} ({context})."


def _generate_plot_csv(plot) -> str | None:
    """Generate CSV data for the plot's underlying data."""
    # The plot object doesn't have the raw data, but we can provide a template
    # In a full implementation, this would use the actual data
    spec = plot.spec
    vars_map = spec.variables
    
    # Create a simple CSV template
    headers = list(vars_map.values())
    if not headers or not any(headers):
        return None
    
    # Filter out None values
    headers = [h for h in headers if h is not None]
    if not headers:
        return None
    
    csv_lines = [",".join(headers)]
    csv_lines.append("# Data rows would be populated from the actual dataset")
    return "\n".join(csv_lines)