"""Export screen - Download reproducible report bundle."""

from __future__ import annotations

import streamlit as st

from CleanSheet.contracts import JobStatus
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.profile import run_profiling
from CleanSheet.services.reports import generate_export_bundle


def render_export(ws: Workspace) -> None:
    """Render export screen."""
    dataset_ref = st.session_state.get("dataset_ref")
    recipe = st.session_state.get("recipe", [])
    column_roles = st.session_state.get("column_roles", [])
    import_spec = st.session_state.get("import_spec")
    results = st.session_state.get("results")

    if dataset_ref is None or results is None:
        st.error("No analysis to export.")
        if st.button("← Back"):
            st.session_state.current_stage = JobStatus.COMPLETE.value
            st.rerun()
        return

    st.title("📥 Export Results")
    st.caption("Download a complete, reproducible analysis bundle.")

    # Export options
    with st.form("export_options_form"):
        st.markdown("### Report Contents")

        col1, col2 = st.columns(2)
        with col1:
            st.checkbox("Markdown/HTML Report", value=True, disabled=True)
            st.checkbox("Results CSV", value=True, disabled=True)
            st.checkbox("Data Dictionary", value=True, disabled=True)
        with col2:
            st.checkbox("Quality Issues", value=True, disabled=True)
            st.checkbox("Recipe JSON", value=True, disabled=True)
            st.checkbox("Run Manifest", value=True, disabled=True)

        st.markdown("### Figures")
        include_figures = st.checkbox("Include Plot PNGs", value=True, key="export_include_figures")

        st.markdown("### Data")
        include_data = st.checkbox("Include Prepared Data (CSV)", value=False,
                                   help="Warning: Includes potentially sensitive data",
                                   key="export_include_data")

        st.markdown("### Format")
        st.radio("Bundle format", ["ZIP (all files)"], disabled=True)

        submitted = st.form_submit_button("Generate Export", type="primary", use_container_width=True)

        if submitted:
            st.session_state._export_config = {
                "include_data": include_data,
                "include_figures": include_figures,
            }
            st.session_state.generate_export = True

    # Generate export outside the form
    if st.session_state.get("generate_export"):
        plots = st.session_state.get("plots", [])
        config = st.session_state.get("_export_config", {})
        _generate_export(
            ws, dataset_ref, import_spec, column_roles, recipe,
            results, config.get("include_data", False), config.get("include_figures", True),
            plots
        )
        st.session_state.generate_export = False

    # Back button
    if st.button("← Back to Results"):
        st.session_state.current_stage = JobStatus.COMPLETE.value
        st.rerun()


def _generate_export(
    workspace: Workspace,
    dataset_ref,
    import_spec,
    column_roles,
    recipe,
    results,
    include_data: bool,
    include_figures: bool,
    plots: list,
) -> None:
    """Generate the export bundle."""
    with st.spinner("Generating export bundle..."):
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
                plots=plots,
            )

            # Read the zip file
            zip_data = export_path.read_bytes()

            st.success(f"✅ Export ready! ({len(zip_data) / 1024:.1f} KB)")

            # Download button
            st.download_button(
                "⬇️ Download Export Bundle",
                data=zip_data,
                file_name=export_path.name,
                mime="application/zip",
                use_container_width=True,
            )

            # Show contents
            st.markdown("### Bundle Contents")
            st.code("""
cleansheet_export_<run_id>.zip
├── report.md              # Markdown report
├── report.html            # HTML report with styling
├── results.csv            # Statistical results table
├── data_dictionary.csv    # Column metadata & summaries
├── quality_issues.csv     # Data quality flags
├── recipe.json            # Preparation recipe
├── run_manifest.json      # Reproducibility manifest
└── figures/
    ├── plot_1_boxplot.png
    ├── plot_2_scatterplot.png
    └── ...
""")

        except Exception as e:
            st.error(f"Export failed: {e}")
