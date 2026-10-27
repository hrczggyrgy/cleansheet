"""Export screen - Download reproducible report bundle."""

from __future__ import annotations

import hashlib

import streamlit as st

from CleanSheet.contracts import JobStatus
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.profile import run_profiling
from CleanSheet.services.reports import generate_export_bundle
from CleanSheet.ui.accessibility import (
    announce_to_screen_reader,
    render_focus_visible_style,
    render_skip_link,
    set_page_main_content_id,
)


def _compute_export_signature(results, recipe, column_roles, import_spec, include_charts: bool, include_data: bool) -> str:
    """Compute a signature that uniquely identifies this export configuration."""
    parts = [
        results.run_id if results else "no_results",
        results.request.goal.value if results and results.request else "no_request",
        str([s.model_dump() for s in recipe]) if recipe else "no_recipe",
        str([c.model_dump() for c in column_roles]) if column_roles else "no_roles",
        import_spec.model_dump_json() if import_spec else "no_spec",
        str(include_charts),
        str(include_data),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def render_export(ws: Workspace) -> None:
    """Render export screen."""
    dataset_ref = st.session_state.get("dataset_ref")
    recipe = st.session_state.get("recipe", [])
    column_roles = st.session_state.get("column_roles", [])
    import_spec = st.session_state.get("import_spec")
    results = st.session_state.get("results")
    plots = st.session_state.get("plots", [])
    assumption_report = st.session_state.get("assumption_report")

    # Accessibility
    render_skip_link()
    render_focus_visible_style()
    set_page_main_content_id()

    if dataset_ref is None or results is None:
        st.error("No analysis to export.")
        if st.button("← Back"):
            st.session_state.current_stage = JobStatus.COMPLETE.value
            st.rerun()
        return

    st.title("📥 Download Report")
    st.caption("Your analysis is complete. Download a reproducible report bundle.")
    announce_to_screen_reader("Export page loaded. Choose export options and download your report bundle.")

    st.markdown("### What's included")
    st.markdown("""
    - **Analysis summary** — Your question, the answer, and key limitations
    - **Statistical results** — Estimates, confidence intervals, and test details
    - **Assumption diagnostics** — Complete assumption check report
    - **Charts** — Visualizations from your analysis
    - **Data dictionary** — Column descriptions and quality flags
    - **Quality issues** — Detected data quality problems
    - **Reproducibility files** — Recipe, run manifest, and software versions
    """)

    # Options
    include_charts = st.checkbox("Include charts", value=True, key="export_include_charts")
    include_data = st.checkbox(
        "Include prepared data (CSV)",
        value=False,
        help="Warning: Includes potentially sensitive data from your analysis",
        key="export_include_data",
    )
    include_assumptions = st.checkbox("Include assumption diagnostics", value=True, key="export_include_assumptions")

    st.divider()

    # Generate and download
    if st.button("📦 Prepare Report", type="primary", width="stretch"):
        _generate_export(
            ws, dataset_ref, import_spec, column_roles,
            recipe, results, plots, assumption_report,
            include_charts, include_data, include_assumptions
        )

    # Show download if ready
    if "export_zip_data" in st.session_state:
        # Verify the export is still valid for current settings
        current_signature = _compute_export_signature(
            st.session_state.get("results"),
            st.session_state.get("recipe", []),
            st.session_state.get("column_roles", []),
            st.session_state.get("import_spec"),
            st.session_state.get("export_include_charts", True),
            st.session_state.get("export_include_data", False),
        )

        if st.session_state.get("export_signature") == current_signature:
            st.success("✅ Report ready!")
            st.download_button(
                "⬇️ Download Report",
                data=st.session_state.export_zip_data,
                file_name=st.session_state.export_filename,
                mime="application/zip",
                width="stretch",
            )
        else:
            st.warning("⚠️ Your report settings or analysis have changed. The previous report is no longer valid.")
            if st.button("Clear old report"):
                for key in ["export_zip_data", "export_filename", "export_signature"]:
                    st.session_state.pop(key, None)
                st.rerun()

    st.divider()
    if st.button("← Back to Results", width="stretch"):
        st.session_state.current_stage = JobStatus.COMPLETE.value
        st.rerun()


def _generate_export(
    workspace: Workspace,
    dataset_ref,
    import_spec,
    column_roles,
    recipe,
    results,
    plots: list,
    assumption_report,
    include_charts: bool,
    include_data: bool,
    include_assumptions: bool,
) -> None:
    """Generate the export bundle."""
    with st.spinner("Generating report..."):
        try:
            # Run profiling for data dictionary
            profile = run_profiling(workspace, dataset_ref)

            # Generate bundle
            export_path = generate_export_bundle(
                workspace=workspace,
                result=results,
                dataset_ref=dataset_ref,
                import_spec=import_spec,
                column_roles=column_roles,
                recipe=recipe,
                profile=profile,
                include_data=include_data,
                plots=plots if include_charts else [],
                assumption_report=assumption_report if include_assumptions else None,
            )

            # Read the zip file
            zip_data = export_path.read_bytes()

            # Compute signature for validation
            signature = _compute_export_signature(
                results,
                st.session_state.get("recipe", []),
                st.session_state.get("column_roles", []),
                st.session_state.get("import_spec"),
                st.session_state.get("export_include_charts", True),
                st.session_state.get("export_include_data", False),
            )

            # Store in session state for persistent download
            st.session_state.export_zip_data = zip_data
            st.session_state.export_filename = export_path.name
            st.session_state.export_signature = signature

            st.rerun()

        except Exception as e:
            st.error(f"Export failed: {e}")
