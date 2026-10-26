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
        if st.button("← New Question", use_container_width=True):
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
        if st.button("Continue to Export →", type="primary", use_container_width=True):
            st.session_state.current_stage = JobStatus.EXPORT_READY.value
            st.rerun()


def _render_statistical_result(result, plan, index: int) -> None:
    """Render a single statistical result."""
    st.markdown(f"### Analysis {index + 1}: {result.method.value.replace('_', ' ').title()}")

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
        st.image(plot.png_bytes, caption=f"{plot.spec.plot_type.value.replace('_', ' ').title()}", use_column_width=True)

        # Download button
        st.download_button(
            "⬇️ Download PNG",
            data=plot.png_bytes,
            file_name=f"plot_{plot.spec.plot_type.value}.png",
            mime="image/png",
            key=f"dl_{id(plot)}",
        )
