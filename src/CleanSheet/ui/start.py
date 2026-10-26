"""Start screen - Choose data source."""

from __future__ import annotations

import streamlit as st

from CleanSheet.config import get_settings
from CleanSheet.contracts import ImportSpec, JobStatus
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.ingest import ingest_file, validate_upload


def render_start(ws: Workspace) -> None:
    """Render the start screen."""
    settings = get_settings()

    st.title("📊 CleanSheet")
    st.markdown("**No-code statistical analysis for tabular data**")
    st.markdown("")

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
                    st.success(f"✅ Valid {fmt.upper()} file ({len(data) / 1024 / 1024:.1f} MB)")
                except Exception as e:
                    st.error(f"❌ {e}")
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
    """Process the uploaded file."""
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
            st.session_state.current_stage = JobStatus.IMPORT_REVIEW
            st.session_state.pending_upload = None
        except Exception as e:
            st.error(f"Failed to process file: {e}")


def _load_demo(ws: Workspace, dataset_name: str) -> None:
    """Load a demo dataset."""
    import polars as pl
    import seaborn as sns

    try:
        # Load from seaborn
        pdf = sns.load_dataset(dataset_name)
        df = pl.from_pandas(pdf)

        # Convert to bytes
        import io
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

    except Exception as e:
        st.error(f"Failed to load demo dataset: {e}")
