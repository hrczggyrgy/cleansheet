"""Start screen - Choose data source and set study context."""

from __future__ import annotations

import io

import polars as pl
import seaborn as sns
import streamlit as st

from CleanSheet.config import get_settings
from CleanSheet.contracts import ImportSpec, JobStatus, StudyContext
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.ingest import ingest_file, validate_upload
from CleanSheet.ui.accessibility import (
    announce_to_screen_reader,
    render_focus_visible_style,
    render_skip_link,
    set_page_main_content_id,
)


def render_start(ws: Workspace) -> None:
    """Render the start screen."""
    settings = get_settings()

    # Accessibility: skip link and focus styles
    render_skip_link()
    render_focus_visible_style()
    set_page_main_content_id()

    st.title("📊 CleanSheet")
    st.markdown("**No-code statistical analysis for tabular data**")
    st.markdown("")

    # Announce page load to screen readers
    announce_to_screen_reader("CleanSheet start page loaded. Choose to upload a file or try an example dataset.")

    # Mode selector
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📁 Upload Your Data")
        st.markdown("Analyze your own CSV or Parquet file locally.")

        uploaded = st.file_uploader(
            "Choose a file",
            type=["csv", "parquet", "pq"],
            help="CSV or Parquet files up to 50 MB",
            label_visibility="collapsed",
        )

        if uploaded:
            with st.spinner("Validating file..."):
                try:
                    data = uploaded.getvalue()
                    fmt, import_spec = validate_upload(data, uploaded.name)
                    st.session_state.import_spec = import_spec
                    st.session_state.pending_upload = {
                        "data": data,
                        "filename": uploaded.name,
                        "format": fmt,
                    }
                    # Store raw data for re-parsing
                    st.session_state.raw_upload_data = data
                    st.success(f"✅ Valid {fmt.upper()} file ({len(data) / 1024 / 1024:.1f} MB)")
                    announce_to_screen_reader(f"File uploaded successfully: {fmt.upper()} file, {len(data) / 1024 / 1024:.1f} megabytes")
                except Exception as e:
                    st.error(f"❌ {e}")
                    announce_to_screen_reader(f"File upload failed: {e}")
                    st.stop()

        if st.session_state.get("pending_upload"):
            if st.button("Continue with this file", type="primary", use_container_width=True):
                _process_upload(ws)
                st.rerun()

    with col2:
        st.markdown("### 🎯 Try an Example")
        st.markdown("Explore CleanSheet with built-in datasets.")

        demo_datasets = {
            "Palmer Penguins": "penguins",
            "Iris": "iris",
            "Tips": "tips",
            "Titanic": "titanic",
        }

        selected = st.selectbox("Choose a dataset", list(demo_datasets.keys()))

        if st.button("Load Example", type="primary", use_container_width=True):
            _load_demo(ws, demo_datasets[selected])
            announce_to_screen_reader(f"Loaded example dataset: {selected}")
            st.rerun()

    # Information
    st.divider()
    st.markdown("""
    **What CleanSheet does:**
    - 📥 Import CSV/Parquet files
    - 🔍 Review data quality & structure
    - 🛠️ Prepare data with reversible steps
    - ❓ Ask statistical questions in plain language
    - 📈 Get estimates with confidence intervals
    - 📥 Download reproducible reports

    **Privacy:** Your data never leaves this browser session when running locally.
    """)


def _process_upload(ws: Workspace) -> None:
    """Process the uploaded file and show study context intake."""
    pending = st.session_state.pending_upload
    data = pending["data"]
    filename = pending["filename"]
    fmt = pending["format"]
    import_spec = st.session_state.import_spec

    with st.spinner("Processing file..."):
        try:
            dataset_ref, preview, metadata = ingest_file(ws, data, filename, import_spec)
            st.session_state.dataset_ref = dataset_ref
            st.session_state.preview = preview
            st.session_state.import_metadata = metadata
            st.session_state.raw_upload_data = data

            # Check for repeated IDs to inform study context
            _detect_repeated_ids(preview)

            # Move to study context intake
            st.session_state.current_stage = JobStatus.IMPORT_REVIEW
            st.session_state.pending_upload = None
        except Exception as e:
            st.error(f"Failed to process file: {e}")


def _detect_repeated_ids(df: pl.DataFrame) -> None:
    """Detect columns that might be subject IDs with repeated values."""
    candidate_ids = []

    for col in df.columns:
        s = df[col]
        n_unique = s.n_unique()
        n_rows = len(s)

        # Check if column name suggests ID
        col_lower = col.lower()
        id_keywords = ["id", "key", "uuid", "guid", "code", "number", "num", "subject", "patient", "participant", "entity"]
        is_id_name = any(kw in col_lower for kw in id_keywords)

        # Check for repeated values (1 < unique < total)
        has_repeats = 1 < n_unique < n_rows

        if is_id_name and has_repeats:
            candidate_ids.append({
                "column": col,
                "unique": n_unique,
                "total": n_rows,
                "repetition_rate": n_rows / n_unique,
            })

    if candidate_ids:
        # Store for study context screen
        st.session_state.detected_repeated_ids = candidate_ids


def _load_demo(ws: Workspace, dataset_name: str) -> None:
    """Load a demo dataset."""

    try:
        # Load from seaborn
        pdf = sns.load_dataset(dataset_name)
        df = pl.from_pandas(pdf)

        # Convert to bytes
        buf = io.BytesIO()
        df.write_parquet(buf)
        data = buf.getvalue()

        # Ingest
        import_spec = ImportSpec()
        dataset_ref, preview, metadata = ingest_file(ws, data, f"{dataset_name}.parquet", import_spec)

        st.session_state.dataset_ref = dataset_ref
        st.session_state.preview = preview
        st.session_state.import_metadata = metadata
        st.session_state.current_stage = JobStatus.IMPORT_REVIEW
        st.session_state.demo_mode = True
        st.session_state.raw_upload_data = data

        # Check for repeated IDs
        _detect_repeated_ids(preview)

    except Exception as e:
        st.error(f"Failed to load demo dataset: {e}")


def render_study_context(ws: Workspace) -> None:
    """Render the study context intake screen (called from import_review)."""
    dataset_ref = st.session_state.get("dataset_ref")
    preview = st.session_state.get("preview")
    detected_ids = st.session_state.get("detected_repeated_ids", [])

    if dataset_ref is None or preview is None:
        st.error("No data loaded.")
        return

    st.title("📋 Study Context")
    st.caption("Help CleanSheet understand your data structure before analysis.")

    # Show dataset summary
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows", f"{dataset_ref.row_count:,}")
    col2.metric("Columns", dataset_ref.column_count)
    col3.metric("Format", dataset_ref.format.upper())
    col4.metric("Source Hash", dataset_ref.source_sha256[:12])

    # Data preview
    st.markdown("### Data Preview (first 5 rows)")
    st.dataframe(preview.head(5).to_pandas(), hide_index=True, use_container_width=True)

    st.divider()

    # Question 1: Row independence
    st.markdown("### 1. What does each row represent?")

    # Check if we detected repeated IDs
    if detected_ids:
        st.info(f"🔍 **Auto-detected**: Found {len(detected_ids)} candidate ID column(s) with repeated values.")
        for cid in detected_ids:
            st.caption(f"• `{cid['column']}`: {cid['unique']:,} unique values across {cid['total']:,} rows (~{cid['repetition_rate']:.1f} rows per ID)")

    row_independence = st.radio(
        "Row structure:",
        ["independent", "paired"],
        format_func=lambda x: {
            "independent": "✅ Separate people, items, or transactions (Independent rows)",
            "paired": "🔄 Repeated measurements on the same person/item over time (Paired/Panel)",
        }[x],
        horizontal=False,
        key="study_row_independence",
        help="Independent: Each row is a different subject. Paired: Same subjects measured multiple times (e.g., before/after).",
    )

    # If paired, ask for subject ID column
    subject_id_column = None
    if row_independence == "paired":
        id_cols = [c["column"] for c in detected_ids] if detected_ids else []
        all_cols = preview.columns
        subject_id_column = st.selectbox(
            "Subject ID column (identifies repeated measures on the same unit):",
            options=id_cols + [c for c in all_cols if c not in id_cols],
            index=0 if id_cols else None,
            key="study_subject_id",
            help="Select the column that identifies which rows belong to the same subject.",
        )

    st.divider()

    # Question 2: Data collection type
    st.markdown("### 2. How was this data gathered?")

    collection_type = st.radio(
        "Data collection:",
        ["observational", "experimental"],
        format_func=lambda x: {
            "observational": "📊 Observational records, operations logs, or survey responses",
            "experimental": "🧪 Randomized experiment or A/B test with controlled assignment",
        }[x],
        horizontal=False,
        key="study_collection_type",
        help="Observational: Data collected without intervention. Experimental: Randomized treatment assignment.",
    )

    st.divider()

    # Confirm button
    if st.button("Continue to Data Review →", type="primary", use_container_width=True):
        # Create study context
        context = StudyContext(
            row_independence=row_independence,
            collection_type=collection_type,
            subject_id_column=subject_id_column,
            confirmed_by_user=True,
            auto_detected=len(detected_ids) > 0,
            detection_notes=f"Detected {len(detected_ids)} candidate ID columns" if detected_ids else None,
        )
        st.session_state.study_context = context
        st.session_state.current_stage = JobStatus.DATA_READY
        st.rerun()

    # Back button
    if st.button("← Back to Upload"):
        st.session_state.current_stage = JobStatus.EMPTY
        st.rerun()
