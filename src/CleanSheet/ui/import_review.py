"""Import review screen - Review data preview and import settings."""

from __future__ import annotations

import io
import polars as pl
import streamlit as st

from CleanSheet.contracts import ColumnRole, ImportSpec, JobStatus, PhysicalDtype, SemanticRole
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.ingest import ingest_file, infer_column_roles


def render_import_review(ws: Workspace) -> None:
    """Render import review screen."""
    preview = st.session_state.get("preview")
    metadata = st.session_state.get("import_metadata")
    dataset_ref = st.session_state.get("dataset_ref")
    raw_data = st.session_state.get("raw_upload_data")

    if preview is None:
        st.error("No data preview available. Please go back and upload a file.")
        if st.button("← Back to Upload"):
            st.session_state.current_stage = JobStatus.EMPTY.value
            st.rerun()
        return

    st.title("📋 Review Data Import")

    # File info
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows", f"{metadata.get('row_count', 0):,}")
    col2.metric("Columns", metadata.get("column_count", 0))
    col3.metric("Format", metadata.get("format", "").upper())
    col4.metric("Encoding", metadata.get("encoding", "utf-8"))

    # Import settings - outside form for live preview updates
    st.markdown("### Import Settings")

    col1, col2 = st.columns(2)
    with col1:
        encoding = st.selectbox(
            "Encoding",
            ["utf-8", "latin-1", "cp1252", "utf-16"],
            index=0,
            key="import_encoding",
        )
        delimiter = st.selectbox(
            "Delimiter",
            [",", ";", "\t", "|"],
            index=0,
            key="import_delimiter",
        )
    with col2:
        decimal_comma = st.checkbox("Decimal comma (European)", value=False, key="import_decimal_comma")
        date_format = st.text_input("Date format (optional)", placeholder="%Y-%m-%d", key="import_date_format")

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

    # Update preview button
    if st.button("🔄 Update Preview", type="secondary", use_container_width=True):
        if raw_data:
            with st.spinner("Re-parsing with new settings..."):
                temp_spec = ImportSpec(
                    encoding=st.session_state.import_encoding,
                    delimiter=st.session_state.import_delimiter,
                    decimal_comma=st.session_state.import_decimal_comma,
                    date_format=st.session_state.import_date_format if st.session_state.import_date_format else None,
                )
                try:
                    dataset_ref, new_preview, new_metadata = ingest_file(ws, raw_data, "uploaded_file", temp_spec)
                    st.session_state.dataset_ref = dataset_ref
                    st.session_state.preview = new_preview
                    st.session_state.import_metadata = new_metadata
                    st.success("Preview updated!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to parse: {e}")

    st.divider()

    # Submit form
    with st.form("confirm_import"):
        st.markdown("### Confirm Import")

        st.caption("Current settings will be used for analysis. You can update the preview above before confirming.")

        submitted = st.form_submit_button("Confirm Import & Continue", type="primary", use_container_width=True)

        if submitted:
            # Update import spec
            import_spec = ImportSpec(
                encoding=st.session_state.import_encoding,
                delimiter=st.session_state.import_delimiter,
                decimal_comma=st.session_state.import_decimal_comma,
                date_format=st.session_state.import_date_format if st.session_state.import_date_format else None,
            )
            st.session_state.import_spec = import_spec
            st.session_state.pending_import_spec = import_spec

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

            st.session_state.current_stage = JobStatus.DATA_READY.value
            st.rerun()

    # Back button
    if st.button("← Back to Upload"):
        st.session_state.current_stage = JobStatus.EMPTY.value
        st.rerun()
