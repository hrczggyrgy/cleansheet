"""CleanSheet - Main Streamlit application entry point."""

from __future__ import annotations

import uuid
import streamlit as st

from CleanSheet.config import get_settings
from CleanSheet.jobs.workspace import get_workspace_manager, Workspace
from CleanSheet.ui.start import render_start
from CleanSheet.ui.import_review import render_import_review
from CleanSheet.ui.preparation import render_preparation
from CleanSheet.ui.question import render_question
from CleanSheet.ui.results import render_results
from CleanSheet.ui.export import render_export

settings = get_settings()


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


def reset_session() -> None:
    """Reset session state for new analysis."""
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


def render_sidebar() -> None:
    """Render sidebar with session info and navigation."""
    with st.sidebar:
        st.markdown("### CleanSheet")
        st.caption(f"Session: `{st.session_state.session_id[:8]}`")

        # Current dataset
        if st.session_state.dataset_ref:
            ref = st.session_state.dataset_ref
            st.markdown("**Dataset**")
            st.caption(f"{ref.row_count:,} rows × {ref.column_count} cols")
            st.caption(f"Hash: `{ref.source_sha256[:12]}`")

        # Progress indicator
        stages = [
            JobStatus.EMPTY.value,
            JobStatus.IMPORT_REVIEW.value,
            JobStatus.DATA_READY.value,
            JobStatus.PLAN_READY.value,
            JobStatus.RUNNING.value,
            JobStatus.COMPLETE.value,
            JobStatus.EXPORT_READY.value,
        ]
        current_idx = stages.index(st.session_state.current_stage) if st.session_state.current_stage in stages else 0

        st.markdown("**Progress**")
        for i, stage in enumerate(stages):
            if i <= current_idx:
                st.markdown(f"✅ {stage.replace('_', ' ').title()}")
            else:
                st.markdown(f"⬜ {stage.replace('_', ' ').title()}")

        # Actions
        st.divider()
        if st.button("🔄 New Analysis", use_container_width=True, type="secondary"):
            reset_session()
            st.rerun()

        if st.session_state.current_stage in [JobStatus.COMPLETE.value, JobStatus.EXPORT_READY.value]:
            if st.button("📥 Export Results", use_container_width=True, type="primary"):
                st.session_state.current_stage = JobStatus.EXPORT_READY.value
                st.rerun()

        # Demo mode indicator
        if settings.demo_mode:
            st.divider()
            st.info("🎭 Demo Mode - Using bundled data")


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
    stage = st.session_state.current_stage

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
    else:
        st.error(f"Unknown stage: {stage}")
        if st.button("Reset Session"):
            reset_session()
            st.rerun()


if __name__ == "__main__":
    main()