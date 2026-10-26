"""Data preparation screen - Reversible transformations."""

from __future__ import annotations

import polars as pl
import streamlit as st

from CleanSheet.contracts import (
    ColumnRole,
    JobStatus,
    SemanticRole,
    TransformOp,
)
from CleanSheet.engine.execution import LazyExecutor, get_or_create_prepared
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.prepare import (
    apply_transform,
    create_transform_step,
    suggest_transformations,
)
from CleanSheet.services.profile import run_profiling


def render_preparation(ws: Workspace) -> None:
    """Render data preparation screen."""
    dataset_ref = st.session_state.get("dataset_ref")
    column_roles = st.session_state.get("column_roles", [])
    recipe = st.session_state.get("recipe", [])

    if dataset_ref is None:
        st.error("No dataset loaded.")
        return

    st.title("🛠️ Prepare Data")
    st.caption("Apply reversible transformations. Each step can be undone.")

    # Get executor and current data
    executor = LazyExecutor(ws, dataset_ref)
    current_df = get_or_create_prepared(ws, dataset_ref, [s.model_dump() for s in recipe]) if recipe else executor.preview(1000)

    # Show current recipe
    if recipe:
        st.markdown("### Recipe")
        for i, step in enumerate(recipe):
            col1, col2, col3 = st.columns([3, 1, 1])
            col1.markdown(f"**{i+1}.** {step.operation.value}: {step.arguments}")
            col2.caption(f"Rows: {step.affected_row_count:,}")
            if col3.button("↩️ Undo", key=f"undo_{i}"):
                st.session_state.recipe = recipe[:i]
                st.rerun()
        st.divider()

    # Data preview
    st.markdown("### Current Data Preview")
    st.dataframe(current_df.head(100).to_pandas(), hide_index=True, use_container_width=True)

    # Suggested transformations
    profile = run_profiling(ws, dataset_ref)
    suggestions = suggest_transformations(profile)

    if suggestions:
        st.markdown("### Suggested Transformations")
        for sug in suggestions:
            with st.expander(f"💡 {sug['reason']} ({sug['priority']})"):
                st.write(sug["reason"])
                if st.button("Apply", key=f"suggest_{sug['operation']}_{hash(str(sug))}"):
                    _apply_suggestion(executor, recipe, sug, current_df)
                    st.rerun()

    # Manual transformations
    st.markdown("### Add Transformation")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Rename", "Filter", "Cast", "Drop", "Recode"])

    with tab1:
        _render_rename_tab(executor, recipe, current_df, column_roles)

    with tab2:
        _render_filter_tab(executor, recipe, current_df, column_roles)

    with tab3:
        _render_cast_tab(executor, recipe, current_df, column_roles)

    with tab4:
        _render_drop_tab(executor, recipe, current_df, column_roles)

    with tab5:
        _render_recode_tab(executor, recipe, current_df, column_roles)

    # Role confirmation
    st.divider()
    st.markdown("### Column Roles")
    _render_role_editor(column_roles)

    # Navigation
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            st.session_state.current_stage = JobStatus.IMPORT_REVIEW
            st.rerun()

    with col2:
        if st.button("Continue to Question →", type="primary", use_container_width=True):
            st.session_state.column_roles = column_roles
            st.session_state.recipe = recipe
            st.session_state.current_stage = JobStatus.PLAN_READY
            st.rerun()


def _render_rename_tab(executor, recipe, current_df, column_roles):
    cols = current_df.columns
    with st.form("rename_form"):
        st.write("Rename columns")
        rename_map = {}
        for col in cols:
            new_name = st.text_input(f"Rename `{col}`", value=col, key=f"rename_{col}")
            if new_name != col:
                rename_map[col] = new_name

        if st.form_submit_button("Apply Rename"):
            if rename_map:
                step = create_transform_step(
                    TransformOp.RENAME,
                    {"mapping": rename_map},
                    {c: str(current_df[c].dtype) for c in current_df.columns},
                    {rename_map.get(c, c): str(current_df[c].dtype) for c in current_df.columns},
                    current_df.height,
                    len(rename_map),
                )
                step.step_id = len(recipe)
                result = apply_transform(executor, recipe, step)
                st.session_state.recipe = result.recipe
                st.rerun()


def _render_filter_tab(executor, recipe, current_df, column_roles):
    with st.form("filter_form"):
        st.write("Filter rows")
        col = st.selectbox("Column", current_df.columns)
        dtype = current_df[col].dtype

        if dtype.is_numeric():
            min_val = float(current_df[col].min()) if current_df[col].min() is not None else 0
            max_val = float(current_df[col].max()) if current_df[col].max() is not None else 100
            range_vals = st.slider("Range", min_val, max_val, (min_val, max_val))
            expr = f"(pl.col('{col}') >= {range_vals[0]}) & (pl.col('{col}') <= {range_vals[1]})"
        elif dtype in (pl.String, pl.Categorical):
            values = current_df[col].unique().to_list()
            selected = st.multiselect("Keep values", values, default=values)
            if selected:
                expr = f"pl.col('{col}').is_in({selected})"
            else:
                expr = "pl.lit(False)"
        else:
            expr = st.text_input("Polars expression", placeholder="pl.col('col') > 0")

        if st.form_submit_button("Apply Filter"):
            step = create_transform_step(
                TransformOp.FILTER,
                {"expression": expr},
                {c: str(current_df[c].dtype) for c in current_df.columns},
                {c: str(current_df[c].dtype) for c in current_df.columns},
                current_df.height,
                0,
            )
            step.step_id = len(recipe)
            result = apply_transform(executor, recipe, step)
            st.session_state.recipe = result.recipe
            st.rerun()


def _render_cast_tab(executor, recipe, current_df, column_roles):
    with st.form("cast_form"):
        st.write("Cast column types")
        col = st.selectbox("Column", current_df.columns)
        target_type = st.selectbox("Target type", ["Int64", "Float64", "String", "Boolean", "Date"])

        if st.form_submit_button("Apply Cast"):
            step = create_transform_step(
                TransformOp.CAST,
                {"casts": {col: target_type}},
                {c: str(current_df[c].dtype) for c in current_df.columns},
                {**{c: str(current_df[c].dtype) for c in current_df.columns if c != col}, col: target_type},
                current_df.height,
                1,
            )
            step.step_id = len(recipe)
            result = apply_transform(executor, recipe, step)
            st.session_state.recipe = result.recipe
            st.rerun()


def _render_drop_tab(executor, recipe, current_df, column_roles):
    with st.form("drop_form"):
        st.write("Drop columns")
        cols_to_drop = st.multiselect("Columns to drop", current_df.columns)

        if st.form_submit_button("Drop Columns"):
            if cols_to_drop:
                step = create_transform_step(
                    TransformOp.DROP_COLUMNS,
                    {"columns": cols_to_drop},
                    {c: str(current_df[c].dtype) for c in current_df.columns},
                    {c: str(current_df[c].dtype) for c in current_df.columns if c not in cols_to_drop},
                    current_df.height,
                    len(cols_to_drop),
                )
                step.step_id = len(recipe)
                result = apply_transform(executor, recipe, step)
                st.session_state.recipe = result.recipe
                st.rerun()


def _render_recode_tab(executor, recipe, current_df, column_roles):
    with st.form("recode_form"):
        st.write("Recode categorical values")
        cat_cols = [c for c in current_df.columns if current_df[c].dtype in (pl.String, pl.Categorical)]
        if not cat_cols:
            st.info("No categorical columns available")
            return

        col = st.selectbox("Column", cat_cols)
        values = current_df[col].unique().to_list()

        st.write("Map values (old → new):")
        recode_map = {}
        for val in values[:20]:  # Limit to 20
            new_val = st.text_input(f"`{val}` →", value=val, key=f"recode_{col}_{val}")
            if new_val != val:
                recode_map[val] = new_val

        if st.form_submit_button("Apply Recode"):
            if recode_map:
                step = create_transform_step(
                    TransformOp.RECODE_CATEGORICAL,
                    {"mapping": {col: recode_map}},
                    {c: str(current_df[c].dtype) for c in current_df.columns},
                    {c: str(current_df[c].dtype) for c in current_df.columns},
                    current_df.height,
                    1,
                )
                step.step_id = len(recipe)
                result = apply_transform(executor, recipe, step)
                st.session_state.recipe = result.recipe
                st.rerun()


def _render_role_editor(column_roles: list[ColumnRole]) -> None:
    """Edit column semantic roles."""
    for i, role in enumerate(column_roles):
        cols = st.columns([2, 2, 2, 1])
        cols[0].write(f"`{role.column}`")
        cols[1].write(role.physical_dtype.value)

        new_semantic = cols[2].selectbox(
            "Role",
            [r.value for r in SemanticRole],
            index=[r.value for r in SemanticRole].index(role.semantic_role.value),
            key=f"role_{i}",
        )

        if new_semantic != role.semantic_role.value:
            column_roles[i] = ColumnRole(
                column=role.column,
                physical_dtype=role.physical_dtype,
                semantic_role=SemanticRole(new_semantic),
                confirmed=role.confirmed,
            )

        if cols[3].button("✓" if role.confirmed else "○", key=f"confirm_{i}"):
            column_roles[i] = ColumnRole(
                column=role.column,
                physical_dtype=role.physical_dtype,
                semantic_role=role.semantic_role,
                confirmed=not role.confirmed,
            )
            st.rerun()
