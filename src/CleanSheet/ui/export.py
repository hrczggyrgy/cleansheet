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
            st.session_state.current_stage = JobStatus.COMPLETE
            st.rerun()
        return

    st.title("📥 Export Results")
    st.caption("Download a complete, reproducible analysis bundle.")

    # Export options
    with st.form("export_options"):
        st.markdown("### Report Contents")

        col1, col2 = st.columns(2)
        with col1:
            include_report = st.checkbox("Markdown/HTML Report", value=True)
            include_results = st.checkbox("Results CSV", value=True)
            include_dict = st.checkbox("Data Dictionary", value=True)
        with col2:
            include_quality = st.checkbox("Quality Issues", value=True)
            include_recipe = st.checkbox("Recipe JSON", value=True)
            include_manifest = st.checkbox("Run Manifest", value=True)

        st.markdown("### Figures")
        include_figures = st.checkbox("Include Plot PNGs", value=True)

        st.markdown("### Data")
        include_data = st.checkbox("Include Prepared Data (CSV)", value=False,
                                   help="Warning: Includes potentially sensitive data")

        st.markdown("### Format")
        export_format = st.radio("Bundle format", ["ZIP (all files)", "Individual files"])

        submitted = st.form_submit_button("Generate Export", type="primary", use_container_width=True)

        if submitted:
            _generate_export(
                ws, dataset_ref, import_spec, column_roles, recipe,
                results, include_data, include_figures
            )

    # Back button
    if st.button("← Back to Results"):
        st.session_state.current_stage = JobStatus.COMPLETE
        st.rerun()


def _generate_export(
    ws: Workspace,
    dataset_ref,
    import_spec,
    column_roles,
    recipe,
    results,
    include_data: bool,
    include_figures: bool,
) -> None:
    """Generate the export bundle."""
    with st.spinner("Generating export bundle..."):
        try:
            # Run profiling for data dictionary
            profile = run_profiling(ws, dataset_ref)

            # Generate bundle
            export_path = generate_export_bundle(
                ws=ws,
                result=results,
                dataset_ref=dataset_ref,
                import_spec=import_spec,
                column_roles=column_roles,
                recipe=recipe,
                profile=profile,
                include_data=include_data,
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
