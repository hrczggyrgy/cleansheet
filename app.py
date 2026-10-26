"""CleanSheet - Main Streamlit application entry point."""

from __future__ import annotations

import uuid
import streamlit as st

from CleanSheet.config import get_settings
from CleanSheet.contracts import JobStatus
from CleanSheet.jobs.workspace import get_workspace_manager, Workspace
from CleanSheet.ui.start import render_start
from CleanSheet.ui.import_review import render_import_review
from CleanSheet.ui.preparation import render_preparation
from CleanSheet.ui.question import render_question
from CleanSheet.ui.results import render_results
from CleanSheet.ui.export import render_export

settings = get_settings()


# Friendly step labels for user-facing navigation
STEP_LABELS = {
    JobStatus.EMPTY.value: "1. Add data",
    JobStatus.IMPORT_REVIEW.value: "2. Review data",
    JobStatus.DATA_READY.value: "3. Prepare data (optional)",
    JobStatus.PLAN_READY.value: "4. Ask a question",
    JobStatus.RUNNING.value: "5. Analyzing…",
    JobStatus.COMPLETE.value: "5. Understand results",
    JobStatus.PARTIAL.value: "5. Understand results",
    JobStatus.EXPORT_READY.value: "6. Download report",
}


def init_session() -> None:
    """Initialize session state."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid.uuid4().hex[:12]
        st.session_state.workspace_id = None
        st.session_state.current_stage = JobStatus.EMPTY.value
        st.session_state.dataset_ref = None
        st.session_state.import_spec = None
        st.session_state.column_roles = []
        st.session_state.recipe = []
        st.session_state.recipe_hash = None
        st.session_state.analysis_plan = None
        st.session_state.active_job_id = None
        st.session_state.results = None
        st.session_state.plots = []
        st.session_state.warnings = []
        st.session_state.stale_results = False
        # Pending states that need validation before execution
        st.session_state.pending_analysis_request = None
        st.session_state.pending_import_spec = None
        st.session_state.show_reset_confirm = False


def get_or_create_workspace() -> Workspace:
    """Get or create workspace for current session."""
    ws_manager = get_workspace_manager()

    if st.session_state.workspace_id is None:
        ws = ws_manager.create()
        st.session_state.workspace_id = ws.workspace_id
        return ws

    ws = ws_manager.get(st.session_state.workspace_id)
    if ws is None:
        ws = ws_manager.create(st.session_state.workspace_id)
    return ws


def reset_session(confirm: bool = False) -> None:
    """Reset session state for new analysis."""
    if not confirm:
        # Show confirmation dialog
        st.session_state.show_reset_confirm = True
        st.rerun()
        return

    ws_manager = get_workspace_manager()
    if st.session_state.workspace_id:
        ws_manager.remove(st.session_state.workspace_id, force=True)

    # Keep session_id but reset everything else
    session_id = st.session_state.session_id
    st.session_state.clear()
    st.session_state.session_id = session_id
    st.session_state.workspace_id = None
    st.session_state.current_stage = JobStatus.EMPTY.value
    st.session_state.dataset_ref = None
    st.session_state.import_spec = None
    st.session_state.column_roles = []
    st.session_state.recipe = []
    st.session_state.recipe_hash = None
    st.session_state.analysis_plan = None
    st.session_state.active_job_id = None
    st.session_state.results = None
    st.session_state.plots = []
    st.session_state.warnings = []
    st.session_state.stale_results = False
    st.session_state.pending_analysis_request = None
    st.session_state.pending_import_spec = None
    st.session_state.show_reset_confirm = False


def render_sidebar() -> None:
    """Render sidebar with session info and navigation."""
    with st.sidebar:
        st.markdown("### CleanSheet")
        st.caption("Understand your data without writing code")

        # Current dataset
        dataset_ref = st.session_state.get("dataset_ref")
        if dataset_ref:
            ref = dataset_ref
            st.markdown("**Your data**")
            st.caption(f"{ref.row_count:,} rows × {ref.column_count} cols")
            st.caption(f"Format: {ref.format.upper()}")

        # Progress indicator with friendly labels
        stages = [
            JobStatus.EMPTY.value,
            JobStatus.IMPORT_REVIEW.value,
            JobStatus.DATA_READY.value,
            JobStatus.PLAN_READY.value,
            JobStatus.RUNNING.value,
            JobStatus.COMPLETE.value,
            JobStatus.EXPORT_READY.value,
        ]
        current_stage = st.session_state.get("current_stage", JobStatus.EMPTY.value)
        current_idx = stages.index(current_stage) if current_stage in stages else 0

        st.markdown("**Progress**")
        for i, stage in enumerate(stages):
            label = STEP_LABELS.get(stage, stage.replace('_', ' ').title())
            if i < current_idx:
                st.markdown(f"✅ {label}")
            elif i == current_idx:
                st.markdown(f"▶️ **{label}**")
            else:
                st.markdown(f"⬜ {label}")

        # Actions
        st.divider()
        if st.button("🔄 Start over", use_container_width=True, type="secondary"):
            reset_session(confirm=False)

        if st.session_state.get("show_reset_confirm"):
            st.warning("This will clear your current analysis. Are you sure?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Yes, start over", type="primary", use_container_width=True):
                    reset_session(confirm=True)
            with col2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.show_reset_confirm = False
                    st.rerun()

        if current_stage in [JobStatus.COMPLETE.value, JobStatus.EXPORT_READY.value]:
            if st.button("📥 Download report", use_container_width=True, type="primary"):
                st.session_state.current_stage = JobStatus.EXPORT_READY.value
                st.rerun()

        # Technical details (collapsed)
        with st.expander("Technical details"):
            session_id = st.session_state.get("session_id", "")
            st.caption(f"Session: `{session_id[:8]}`")
            if dataset_ref:
                st.caption(f"Source hash: `{dataset_ref.source_sha256[:12]}`")

        # Demo mode indicator
        if settings.demo_mode:
            st.divider()
            st.info("🎭 Demo Mode — Using bundled data")


def main() -> None:
    """Main application entry point."""
    st.set_page_config(
        page_title="CleanSheet - Statistical Analysis",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_session()
    ws = get_or_create_workspace()
    render_sidebar()

    # Route to appropriate stage
    stage = st.session_state.get("current_stage", JobStatus.EMPTY.value)

    if stage == JobStatus.EMPTY.value:
        render_start(ws)
    elif stage == JobStatus.IMPORT_REVIEW.value:
        render_import_review(ws)
    elif stage == JobStatus.DATA_READY.value:
        render_preparation(ws)
    elif stage == JobStatus.PLAN_READY.value:
        render_question(ws)
    elif stage in [JobStatus.RUNNING.value, JobStatus.COMPLETE.value, JobStatus.PARTIAL.value]:
        render_results(ws)
    elif stage == JobStatus.EXPORT_READY.value:
        render_export(ws)
    elif stage == JobStatus.FAILED.value:
        # Render failure screen instead of rerun loop
        st.error("Analysis failed. Please check the error message and try again.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Retry", type="primary", use_container_width=True):
                st.session_state.current_stage = JobStatus.RUNNING.value
                st.rerun()
        with col2:
            if st.button("← Back to Question", use_container_width=True):
                st.session_state.current_stage = JobStatus.PLAN_READY.value
                st.rerun()
    else:
        st.error(f"Unknown stage: {stage}")
        if st.button("Reset Session"):
            reset_session(confirm=True)
        st.rerun()


if __name__ == "__main__":
    main()