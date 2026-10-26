"""Results screen - Display analysis results and visualizations."""

from __future__ import annotations

import streamlit as st

from CleanSheet.contracts import IntervalMethod, JobStatus
from CleanSheet.engine.execution import LazyExecutor, get_or_create_prepared
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.statistics import run_analysis
from CleanSheet.services.visualize import (
    PlotType,
    create_plot_spec,
    generate_plots,
)


def render_results(ws: Workspace) -> None:
    """Render analysis results screen."""
    dataset_ref = st.session_state.get("dataset_ref")
    recipe = st.session_state.get("recipe", [])
    analysis_plan = st.session_state.get("analysis_plan")
    results = st.session_state.get("results")

    if dataset_ref is None or analysis_plan is None:
        st.error("No analysis to display.")
        if st.button("← Back"):
            st.session_state.current_stage = JobStatus.PLAN_READY.value
            st.rerun()
        return

    st.title("📈 Results")

    # Run analysis if not done
    if results is None and st.session_state.current_stage == JobStatus.RUNNING.value:
        with st.spinner("Running analysis..."):
            try:
                recipe = st.session_state.get("recipe", [])
                recipe_steps = [s.model_dump() for s in recipe]
                result = run_analysis(ws, dataset_ref, analysis_plan, recipe_steps)
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

    # Lead with the question and plain-language summary
    _render_summary(results, analysis_plan)

    # Display results
    for i, stat_result in enumerate(results.statistical_results):
        _render_statistical_result(stat_result, analysis_plan, i)

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


def _render_summary(results, plan) -> None:
    """Render plain-language summary at the top."""
    if not results.statistical_results:
        return

    stat = results.statistical_results[0]
    goal = plan.goal

    # Build plain-language answer
    if goal.value == "compare_two_means":
        _render_compare_summary(stat, plan)
    elif goal.value == "compare_paired_means":
        _render_paired_summary(stat, plan)
    elif goal.value in ("explore_linear_relationship", "explore_ordered_relationship"):
        _render_correlation_summary(stat, plan)
    elif goal.value in ("categorical_association", "sparse_2x2_table"):
        _render_categorical_summary(stat, plan)
    else:
        _render_descriptive_summary(stat, plan)

    # Show sample counts and exclusions prominently
    st.markdown("### Data used")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Observations included", sum(stat.group_counts.values()))
    with col2:
        excluded = sum(stat.exclusions.values()) if stat.exclusions else 0
        if excluded > 0:
            st.metric("Observations excluded", excluded)
            with st.expander("Why were observations excluded?"):
                for k, v in stat.exclusions.items():
                    st.write(f"- {k}: {v}")
        else:
            st.metric("Observations excluded", 0)


def _render_compare_summary(stat, plan) -> None:
    """Render summary for two-group comparison."""
    outcome = plan.variables.get("outcome", "outcome")
    group = plan.variables.get("group", "group")
    levels = plan.group_levels or []

    if stat.estimate is not None and stat.interval and stat.interval_status == "computed":
        direction = "higher" if stat.estimate > 0 else "lower"
        st.markdown(f"""
        **In the analyzed data, {levels[0] if stat.estimate > 0 else levels[1]} averaged {abs(stat.estimate):.2f} units {direction} than {levels[1] if stat.estimate > 0 else levels[0]} on {outcome}.**  

        The {plan.confidence_level:.0%} confidence interval for the difference is **[{stat.interval[0]:.2f}, {stat.interval[1]:.2f}]**.

        *This comparison does not establish that group membership caused the difference.*
        """)
    else:
        st.info("Unable to compute a reliable estimate for this comparison.")


def _render_paired_summary(stat, plan) -> None:
    """Render summary for paired comparison."""
    outcome = plan.variables.get("outcome", "outcome")
    occasion = plan.variables.get("occasion", "occasion")

    if stat.estimate is not None and stat.interval and stat.interval_status == "computed":
        direction = "increased" if stat.estimate > 0 else "decreased"
        st.markdown(f"""
        **In the analyzed data, {outcome} {direction} by {abs(stat.estimate):.2f} units on average from {plan.contrast.split('_minus_')[1] if stat.estimate < 0 else plan.contrast.split('_minus_')[0]} to {plan.contrast.split('_minus_')[0] if stat.estimate < 0 else plan.contrast.split('_minus_')[1]}.**  

        The {plan.confidence_level:.0%} confidence interval for the mean paired difference is **[{stat.interval[0]:.2f}, {stat.interval[1]:.2f}]**.

        *This comparison does not establish that the occasion caused the change.*
        """)
    else:
        st.info("Unable to compute a reliable estimate for this comparison.")


def _render_correlation_summary(stat, plan) -> None:
    """Render summary for correlation."""
    x = plan.variables.get("outcome", "X")
    y = plan.variables.get("predictor", "Y")
    method_name = "Pearson" if stat.method.value == "pearson_r" else "Spearman"

    if stat.estimate is not None:
        strength = _interpret_strength(abs(stat.estimate))
        direction = "positive" if stat.estimate > 0 else "negative"
        st.markdown(f"""
        **There is a {strength} {direction} {method_name} correlation ({stat.estimate:.3f}) between {x} and {y}.**  

        The {stat.interval_status == "computed" and f"{stat.confidence_level:.0%} confidence interval is [{stat.interval[0]:.3f}, {stat.interval[1]:.3f}]" if stat.interval and stat.interval_status == "computed" else "A confidence interval could not be computed."}

        *Correlation does not imply causation. This analysis does not establish that changes in one variable cause changes in the other.*
        """)
    else:
        st.info("Unable to compute a reliable correlation estimate.")


def _render_categorical_summary(stat, plan) -> None:
    """Render summary for categorical association."""
    row = plan.variables.get("outcome", "row")
    col = plan.variables.get("group", "column")

    if stat.estimate is not None:
        st.markdown(f"""
        **There is an association between {row} and {col}.**  

        The {stat.method.value.replace('_', ' ').title()} test {'found a statistically significant association' if stat.p_value and stat.p_value < 0.05 else 'did not find a statistically significant association'} (p = {stat.p_value:.4f if stat.p_value else 'N/A'}).

        *Association does not imply causation.*
        """)
    else:
        st.info("Unable to compute a reliable association estimate.")


def _render_descriptive_summary(stat, plan) -> None:
    """Render summary for descriptive analysis."""
    st.markdown("""
    **Descriptive statistics for your dataset.**  

    Review the tables and charts below to understand the distribution and quality of your variables.
    """)


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


def _render_statistical_result(result, plan, index: int) -> None:
    """Render a single statistical result."""
    st.markdown(f"### {result.method.value.replace('_', ' ').title()}")

    # Main metrics
    cols = st.columns(4)

    if result.estimate is not None:
        cols[0].metric("Estimate", f"{result.estimate:.4f}")

    if result.interval and result.interval_status == "computed":
        ci_text = f"[{result.interval[0]:.4f}, {result.interval[1]:.4f}]"
        cols[1].metric(f"{plan.confidence_level:.0%} CI", ci_text)

    if result.p_value is not None:
        p_text = f"{result.p_value:.6f}" if result.p_value >= 0.001 else "< 0.001"
        cols[2].metric("P-value", p_text)

    if result.effect_size is not None:
        cols[3].metric("Effect Size", f"{result.effect_size:.4f} ({result.effect_size_interpretation})")

    # Details in expandable sections
    with st.expander("📊 Sample Sizes"):
        for k, v in result.group_counts.items():
            st.write(f"- **{k}**: n = {v:,}")

    with st.expander("📐 Test Details"):
        if result.statistic is not None:
            st.write(f"**Statistic**: {result.statistic:.4f}")
        if result.degrees_of_freedom is not None:
            st.write(f"**Degrees of Freedom**: {result.degrees_of_freedom}")
        if result.interval_method != IntervalMethod.NOT_APPLICABLE:
            st.write(f"**Interval Method**: {result.interval_method.value}")
            st.write(f"**Interval Status**: {result.interval_status}")

    with st.expander("⚠️ Assumption Checks"):
        for k, v in result.assumption_checks.items():
            if isinstance(v, dict):
                st.write(f"**{k}**:")
                for k2, v2 in v.items():
                    st.write(f"  - {k2}: {v2}")
            else:
                st.write(f"- **{k}**: {v}")

    with st.expander("🚫 Exclusions"):
        if result.exclusions:
            for k, v in result.exclusions.items():
                st.write(f"- {k}: {v}")
        else:
            st.write("No exclusions")

    # Warnings
    if hasattr(result, "warnings") and result.warnings:
        for w in result.warnings:
            st.warning(w)


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

    # Result-specific plots
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
            # Paired plot
            plot_specs.append(create_plot_spec(
                PlotType.BOXPLOT,
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
    """Render plot results."""
    for plot in plots:
        st.image(plot.png_bytes, caption=f"{plot.spec.plot_type.value.replace('_', ' ').title()}", width="stretch")

        # Download button
        st.download_button(
            "⬇️ Download PNG",
            data=plot.png_bytes,
            file_name=f"plot_{plot.spec.plot_type.value}.png",
            mime="image/png",
            key=f"dl_{id(plot)}",
        )