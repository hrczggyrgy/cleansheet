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

    # Import settings - tracked in session state for atomic commit
    if "import_settings_draft" not in st.session_state:
        st.session_state.import_settings_draft = {
            "encoding": "utf-8",
            "delimiter": ",",
            "decimal_comma": False,
            "date_format": None,
        }

    # Initialize draft from confirmed settings if not set
    if "import_settings_confirmed" in st.session_state:
        confirmed = st.session_state.import_settings_confirmed
        for key in st.session_state.import_settings_draft:
            if key not in st.session_state:
                st.session_state.import_settings_draft[key] = confirmed.get(key, st.session_state.import_settings_draft[key])

    st.markdown("### Import Settings")

    col1, col2 = st.columns(2)
    with col1:
        encoding = st.selectbox(
            "Encoding",
            ["utf-8", "latin-1", "cp1252", "utf-16"],
            index=["utf-8", "latin-1", "cp1252", "utf-16"].index(st.session_state.import_settings_draft["encoding"]),
            key="import_encoding",
        )
        delimiter = st.selectbox(
            "Delimiter",
            [",", ";", "\t", "|"],
            index=[",", ";", "\t", "|"].index(st.session_state.import_settings_draft["delimiter"]),
            key="import_delimiter",
        )
    with col2:
        decimal_comma = st.checkbox("Decimal comma (European)", 
                                    value=st.session_state.import_settings_draft["decimal_comma"],
                                    key="import_decimal_comma")
        date_format = st.text_input("Date format (optional)", 
                                    value=st.session_state.import_settings_draft["date_format"] or "",
                                    placeholder="%Y-%m-%d", 
                                    key="import_date_format")

    # Update draft settings in real-time
    st.session_state.import_settings_draft = {
        "encoding": encoding,
        "delimiter": delimiter,
        "decimal_comma": decimal_comma,
        "date_format": date_format if date_format else None,
    }

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

    # Settings status indicator
    if "import_settings_confirmed" in st.session_state:
        draft = st.session_state.import_settings_draft
        confirmed = st.session_state.import_settings_confirmed
        if draft != confirmed:
            st.warning("⚠️ Settings have been changed since last preview update. Click 'Update Preview' to re-parse with current settings.")
        else:
            st.success("✅ Preview is up to date with current settings.")

    # Update preview button
    if st.button("🔄 Update Preview", type="secondary", use_container_width=True):
        if raw_data:
            with st.spinner("Re-parsing with current settings..."):
                temp_spec = ImportSpec(
                    encoding=st.session_state.import_settings_draft["encoding"],
                    delimiter=st.session_state.import_settings_draft["delimiter"],
                    decimal_comma=st.session_state.import_settings_draft["decimal_comma"],
                    date_format=st.session_state.import_settings_draft["date_format"] if st.session_state.import_settings_draft["date_format"] else None,
                )
                try:
                    dataset_ref, new_preview, new_metadata = ingest_file(ws, raw_data, "uploaded_file", temp_spec)
                    st.session_state.dataset_ref = dataset_ref
                    st.session_state.preview = new_preview
                    st.session_state.import_metadata = new_metadata
                    # Commit the settings that produced this preview
                    st.session_state.import_settings_confirmed = st.session_state.import_settings_draft.copy()
                    st.session_state.import_spec = ImportSpec(**st.session_state.import_settings_confirmed)
                    st.success("Preview updated!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to parse: {e}")

    st.divider()

    # Submit form - only confirms already-previewed settings
    with st.form("confirm_import"):
        st.markdown("### Confirm Import")

        # Show what will be committed
        draft = st.session_state.import_settings_draft
        st.caption(f"Will use: {draft['encoding']} encoding, '{draft['delimiter']}' delimiter, decimal_comma={draft['decimal_comma']}")

        submitted = st.form_submit_button("Confirm Import & Continue", type="primary", use_container_width=True)

        if submitted:
            # Commit the confirmed settings
            import_spec = ImportSpec(**st.session_state.import_settings_confirmed)
            st.session_state.import_spec = import_spec
            st.session_state.pending_import_spec = import_spec

            # Infer column roles from current preview
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
