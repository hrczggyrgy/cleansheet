"""Import review screen - Review data preview, import settings, and confirm semantic types."""

from __future__ import annotations

import polars as pl
import streamlit as st

from CleanSheet.contracts import (
    ColumnRole,
    ImportSpec,
    JobStatus,
    PhysicalDtype,
    SemanticRole,
    StudyContext,
)
from CleanSheet.engine.semantic_typing import (
    confirm_column_role,
    get_ambiguous_columns,
    infer_column_roles,
)
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.ingest import ingest_file
from CleanSheet.ui.accessibility import (
    announce_to_screen_reader,
    render_focus_visible_style,
    render_skip_link,
    set_page_main_content_id,
)


def render_import_review(ws: Workspace) -> None:
    """Render import review screen with study context and semantic type confirmation."""
    preview = st.session_state.get("preview")
    metadata = st.session_state.get("import_metadata")
    dataset_ref = st.session_state.get("dataset_ref")
    raw_data = st.session_state.get("raw_upload_data")
    study_context = st.session_state.get("study_context")

    # Accessibility
    render_skip_link()
    render_focus_visible_style()
    set_page_main_content_id()

    # If study context not yet collected, show it first
    if study_context is None:
        from CleanSheet.ui.start import render_study_context
        render_study_context(ws)
        return

    if preview is None:
        st.error("No data preview available. Please go back and upload a file.")
        if st.button("← Back to Upload"):
            st.session_state.current_stage = JobStatus.EMPTY
            st.rerun()
        return

    st.title("📋 Review Data Import")
    announce_to_screen_reader("Data import review page loaded. Review import settings and confirm variable types.")

    # Study context summary
    _render_study_context_summary(study_context)

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
    st.dataframe(schema_df, hide_index=True, width="stretch")

    # Data preview
    st.markdown("### Data Preview (First 100 rows)")
    st.dataframe(preview.to_pandas(), hide_index=True, width="stretch")

    # Settings status indicator
    if "import_settings_confirmed" in st.session_state:
        draft = st.session_state.import_settings_draft
        confirmed = st.session_state.import_settings_confirmed
        if draft != confirmed:
            st.warning("⚠️ Settings have been changed since last preview update. Click 'Update Preview' to re-parse with current settings.")
        else:
            st.success("✅ Preview is up to date with current settings.")

    # Update preview button
    if st.button("🔄 Update Preview", type="secondary", width="stretch"):
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

    # Semantic Type Confirmation
    _render_semantic_type_confirmation(preview)

    # Submit form - only confirms already-previewed settings
    with st.form("confirm_import"):
        st.markdown("### Confirm Import & Continue")

        # Show what will be committed
        draft = st.session_state.import_settings_draft
        st.caption(f"Will use: {draft['encoding']} encoding, '{draft['delimiter']}' delimiter, decimal_comma={draft['decimal_comma']}")

        submitted = st.form_submit_button("Confirm Import & Continue", type="primary", width="stretch")

        if submitted:
            # Commit the confirmed settings
            import_spec = ImportSpec(**st.session_state.import_settings_confirmed)
            st.session_state.import_spec = import_spec
            st.session_state.pending_import_spec = import_spec

            # Get confirmed column roles
            column_roles = st.session_state.get("confirmed_column_roles", [])
            st.session_state.column_roles = column_roles

            st.session_state.current_stage = JobStatus.DATA_READY
            st.rerun()

    # Back button
    if st.button("← Back to Study Context", width="stretch"):
        st.session_state.current_stage = JobStatus.IMPORT_REVIEW
        if "study_context" in st.session_state:
            del st.session_state.study_context
        st.rerun()


def _render_study_context_summary(context: StudyContext) -> None:
    """Render a summary of the study context."""
    with st.expander("📋 Study Context (confirmed)", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Row structure:** {'Independent' if context.row_independence == 'independent' else 'Paired/Repeated'}")
            if context.subject_id_column:
                st.write(f"**Subject ID column:** `{context.subject_id_column}`")
        with col2:
            st.write(f"**Collection type:** {'Observational' if context.collection_type == 'observational' else 'Experimental/RCT'}")
            if context.auto_detected:
                st.caption(f"Auto-detected: {context.detection_notes}")


def _render_semantic_type_confirmation(preview: pl.DataFrame) -> None:
    """Render the semantic type confirmation UI."""
    st.markdown("### 🔍 Confirm Variable Types")
    st.caption("CleanSheet automatically infers what each column represents. Please review and correct any ambiguous classifications.")

    # Infer roles if not already done
    if "inferred_roles" not in st.session_state:
        roles_dict = infer_column_roles(preview)
        st.session_state.inferred_roles = roles_dict

    roles_dict = st.session_state.inferred_roles

    # Convert to ColumnRole objects
    if "column_roles" not in st.session_state or not st.session_state.column_roles:
        column_roles = []
        for col, info in roles_dict.items():
            column_roles.append(ColumnRole(
                column=col,
                physical_dtype=PhysicalDtype(info["physical_dtype"]),
                semantic_role=SemanticRole(info["semantic_role"]),
                ordinal_order=info.get("ordinal_order"),
                confidence=info.get("confidence", "medium"),
                ambiguity_reason=info.get("ambiguity_reason"),
                is_excluded=info.get("is_excluded", False),
            ))
        st.session_state.column_roles = column_roles

    column_roles = st.session_state.column_roles

    # Find ambiguous columns
    ambiguous_cols = get_ambiguous_columns(roles_dict)

    if ambiguous_cols:
        st.warning(f"⚠️ **{len(ambiguous_cols)} column(s) need your confirmation** — they have ambiguous or low-confidence classifications.")

        for col in ambiguous_cols:
            info = roles_dict[col]
            with st.container(border=True):
                cols = st.columns([2, 2, 3, 1])
                cols[0].write(f"**`{col}`**")
                cols[1].write(f"Physical: `{info['physical_dtype'].value}`")
                cols[1].write(f"Inferred: **{info['semantic_role'].value}**")

                if info.get("ambiguity_reason"):
                    cols[2].caption(f"⚠️ {info['ambiguity_reason']}")

                # Type selector
                current_role = info["semantic_role"]
                role_options = [r.value for r in SemanticRole]
                try:
                    current_idx = role_options.index(current_role.value)
                except ValueError:
                    current_idx = 0

                new_role = cols[3].selectbox(
                    "Type",
                    role_options,
                    index=current_idx,
                    key=f"role_confirm_{col}",
                    label_visibility="collapsed",
                )

                # If ordinal, show order editor
                if new_role == "ordinal":
                    unique_vals = preview[col].drop_nulls().unique().to_list()
                    unique_str = [str(v) for v in unique_vals]
                    current_order = info.get("ordinal_order") or unique_str

                    with st.expander(f"Set order for `{col}`", expanded=True):
                        st.caption("Drag to reorder (top = lowest rank)")
                        # Simple text-based ordering
                        order_str = st.text_area(
                            "Order (one per line, top = lowest):",
                            value="\n".join(current_order),
                            key=f"ordinal_order_{col}",
                            height=100,
                        )
                        new_order = [line.strip() for line in order_str.split("\n") if line.strip()]
                    new_order_val = new_order
                else:
                    new_order_val = None

                # Update the role object
                for i, cr in enumerate(column_roles):
                    if cr.column == col:
                        column_roles[i] = confirm_column_role(
                            current_role=SemanticRole(new_role),
                            new_role=SemanticRole(new_role),
                            ordinal_order=new_order_val,
                        )
                        column_roles[i].column = col
                        column_roles[i].physical_dtype = PhysicalDtype(info["physical_dtype"])
                        break

    # Show all columns in a table
    st.markdown("### All Columns")
    role_data = []
    for cr in column_roles:
        info = roles_dict.get(cr.column, {})
        role_data.append({
            "Column": cr.column,
            "Physical Type": cr.physical_dtype.value,
            "Semantic Role": cr.semantic_role.value,
            "Confidence": cr.confidence,
            "Confirmed": "✅" if cr.confirmed else ("⚠️" if cr.column in ambiguous_cols else "✓"),
            "Excluded": "Yes" if cr.is_excluded else "No",
            "Missing %": f"{info.get('null_pct', 0):.1f}%",
            "Unique": info.get("n_unique", 0),
        })

    if role_data:
        st.dataframe(pl.DataFrame(role_data), hide_index=True, width="stretch")

    # Store confirmed roles
    st.session_state.confirmed_column_roles = column_roles


# Alias for backwards compatibility
render_import_review = render_import_review
