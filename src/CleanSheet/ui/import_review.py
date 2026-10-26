"""Import review screen - Review data preview and import settings."""

from __future__ import annotations

import polars as pl
import streamlit as st

from CleanSheet.contracts import ColumnRole, ImportSpec, JobStatus, PhysicalDtype, SemanticRole
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.ingest import infer_column_roles


def render_import_review(ws: Workspace) -> None:
    """Render import review screen."""
    preview = st.session_state.get("preview")
    metadata = st.session_state.get("import_metadata")
    dataset_ref = st.session_state.get("dataset_ref")

    if preview is None:
        st.error("No data preview available. Please go back and upload a file.")
        if st.button("← Back to Upload"):
            st.session_state.current_stage = JobStatus.EMPTY
            st.rerun()
        return

    st.title("📋 Review Data Import")

    # File info
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows", f"{metadata.get('row_count', 0):,}")
    col2.metric("Columns", metadata.get("column_count", 0))
    col3.metric("Format", metadata.get("format", "").upper())
    col4.metric("Encoding", metadata.get("encoding", "utf-8"))

    # Import settings form
    with st.form("import_settings"):
        st.markdown("### Import Settings")

        col1, col2 = st.columns(2)
        with col1:
            encoding = st.selectbox(
                "Encoding",
                ["utf-8", "latin-1", "cp1252", "utf-16"],
                index=0,
            )
            delimiter = st.selectbox(
                "Delimiter",
                [",", ";", "\t", "|"],
                index=0,
            )
        with col2:
            decimal_comma = st.checkbox("Decimal comma (European)", value=False)
            date_format = st.text_input("Date format (optional)", placeholder="%Y-%m-%d")

        # Schema preview
        st.markdown("### Column Schema Preview")
        schema_df = pl.DataFrame({
            "Column": list(metadata.get("dtypes", {}).keys()),
            "Detected Type": list(metadata.get("dtypes", {}).values()),
        })
        st.dataframe(schema_df, hide_index=True, use_container_width=True)

        # Data preview
        st.markdown("### Data Preview (first 100 rows)")
        st.dataframe(preview.to_pandas(), hide_index=True, use_container_width=True)

        # Submit
        submitted = st.form_submit_button("Confirm Import & Continue", type="primary", use_container_width=True)

        if submitted:
            # Update import spec
            import_spec = ImportSpec(
                encoding=encoding,
                delimiter=delimiter,
                decimal_comma=decimal_comma,
                date_format=date_format if date_format else None,
            )
            st.session_state.import_spec = import_spec

            # Infer column roles
            roles_dict = infer_column_roles(preview)
            column_roles = []
            for col, info in roles_dict.items():
                column_roles.append(ColumnRole(
                    column=col,
                    physical_dtype=PhysicalDtype(info["physical_dtype"]),
                    semantic_role=SemanticRole(info["semantic_role"]),
                    confirmed=False,
                ))
            st.session_state.column_roles = column_roles

            st.session_state.current_stage = JobStatus.DATA_READY
            st.rerun()

    # Back button
    if st.button("← Back to Upload"):
        st.session_state.current_stage = JobStatus.EMPTY
        st.rerun()
