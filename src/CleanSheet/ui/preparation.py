"""Data preparation screen - Reversible transformations with issue detection cards."""

from __future__ import annotations

import polars as pl
import streamlit as st

from CleanSheet.contracts import (
    CleaningStep,
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
)
from CleanSheet.services.profile import run_profiling
from CleanSheet.ui.accessibility import (
    announce_to_screen_reader,
    render_focus_visible_style,
    render_skip_link,
    set_page_main_content_id,
)


def render_preparation(ws: Workspace) -> None:
    """Render data preparation screen with issue detection cards."""
    dataset_ref = st.session_state.get("dataset_ref")
    column_roles = st.session_state.get("column_roles", [])
    recipe = st.session_state.get("recipe", [])

    # Accessibility
    render_skip_link()
    render_focus_visible_style()
    set_page_main_content_id()

    if dataset_ref is None:
        st.error("No dataset loaded.")
        return

    st.title("🛠️ Prepare Data")
    st.caption("Apply reversible transformations. Each step can be undone.")
    announce_to_screen_reader("Data preparation page loaded. Review and apply reversible transformations.")

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
                announce_to_screen_reader(f"Undid step {i+1}: {step.operation.value}")
                st.rerun()
                st.rerun()
        st.divider()

    # Data quality issue cards
    profile = run_profiling(ws, dataset_ref)
    _render_issue_cards(executor, recipe, current_df, column_roles, profile)

    # Data preview
    st.markdown("### Current Data Preview")
    st.dataframe(current_df.head(100).to_pandas(), hide_index=True, use_container_width=True)

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


def _render_issue_cards(
    executor: LazyExecutor,
    recipe: list[CleaningStep],
    current_df: pl.DataFrame,
    column_roles: list[ColumnRole],
    profile,
) -> None:
    """Render data quality issue detection cards with one-click fixes."""
    issues = profile.quality_issues

    has_issues = any(issues.get(k) for k in ["duplicates", "constant_columns", "high_cardinality", "missingness", "numeric_issues"])

    if not has_issues:
        st.success("✅ No critical data quality issues detected.")
        return

    st.markdown("### 🔍 Data Quality Issues")

    # Track applied fixes in session state
    if "applied_fixes" not in st.session_state:
        st.session_state.applied_fixes = set()

    # 1. Exact Duplicate Rows
    if issues.get("duplicates"):
        for dup in issues["duplicates"]:
            if dup["type"] == "full_row" and dup["count"] > 0:
                fix_key = f"deduplicate_{dup['count']}"
                _render_issue_card(
                    title=f"🔄 {dup['count']} Exact Duplicate Row(s)",
                    description=f"Found {dup['count']} completely identical rows across all columns.",
                    fix_key=fix_key,
                    fix_button_label="Remove Duplicates",
                    on_fix=lambda: _apply_deduplicate(executor, recipe, current_df),
                    fix_applied=fix_key in st.session_state.applied_fixes,
                )

    # 2. Constant Columns
    if issues.get("constant_columns"):
        const_cols = issues["constant_columns"]
        fix_key = f"drop_constant_{len(const_cols)}"
        _render_issue_card(
            title=f"📋 {len(const_cols)} Constant Column(s)",
            description=f"Columns with identical values: {', '.join(f'`{c}`' for c in const_cols)}",
            fix_key=fix_key,
            fix_button_label="Drop Constant Columns",
            on_fix=lambda: _apply_drop_constant(executor, recipe, current_df, const_cols),
            fix_applied=fix_key in st.session_state.applied_fixes,
        )

    # 3. High Missingness
    if issues.get("missingness"):
        high_missing = [m for m in issues["missingness"] if m["severity"] in ("high", "medium")]
        if high_missing:
            for m in high_missing:
                fix_key = f"drop_missing_{m['column']}"
                _render_issue_card(
                    title=f"❓ High Missingness: `{m['column']}` ({m['null_pct']:.1f}%)",
                    description=f"Column has {m['null_count']} missing values ({m['null_pct']:.1f}%). Consider dropping if not essential.",
                    fix_key=fix_key,
                    fix_button_label="Drop Column",
                    on_fix=lambda col=m["column"]: _apply_drop_column(executor, recipe, current_df, col),
                    fix_applied=fix_key in st.session_state.applied_fixes,
                )

    # 4. Numeric Issues (NaN, Inf)
    if issues.get("numeric_issues"):
        for ni in issues["numeric_issues"]:
            fix_key = f"fix_numeric_{ni['column']}_{ni['issue']}"
            _render_issue_card(
                title=f"⚠️ Numeric Issue: `{ni['column']}` ({ni['issue']}: {ni['count']})",
                description=f"Column contains {ni['count']} {ni['issue'].lower()} values that may affect analysis.",
                fix_key=fix_key,
                fix_button_label="Drop Non-Finite Rows",
                on_fix=lambda col=ni["column"]: _apply_drop_nonfinite(executor, recipe, current_df, col),
                fix_applied=fix_key in st.session_state.applied_fixes,
            )

    # 5. High Cardinality Categorical
    if issues.get("high_cardinality"):
        for hc in issues["high_cardinality"]:
            fix_key = f"recode_cardinality_{hc['column']}"
            _render_issue_card(
                title=f"🏷️ High Cardinality: `{hc['column']}` ({hc['unique_count']} unique)",
                description="Column has many categories. Consider grouping rare categories into 'Other'.",
                fix_key=fix_key,
                fix_button_label="Group Rare Categories",
                on_fix=lambda col=hc["column"]: _apply_group_rare(executor, recipe, current_df, col),
                fix_applied=fix_key in st.session_state.applied_fixes,
            )

    # 6. Outlier Detection (using IQR)
    _render_outlier_cards(executor, recipe, current_df, column_roles)


def _render_issue_card(
    title: str,
    description: str,
    fix_key: str,
    fix_button_label: str,
    on_fix: callable,
    fix_applied: bool = False,
) -> None:
    """Render a single issue card with fix action."""
    with st.container(border=True):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"**{title}**")
            st.caption(description)
        with col2:
            if fix_applied:
                st.success("✅ Applied")
                if st.button("↩️ Undo", key=f"undo_{fix_key}"):
                    # Remove from applied fixes and undo last recipe step
                    st.session_state.applied_fixes.discard(fix_key)
                    recipe = st.session_state.get("recipe", [])
                    if recipe:
                        st.session_state.recipe = recipe[:-1]
                    st.rerun()
            elif st.button(fix_button_label, key=f"fix_{fix_key}", type="primary"):
                on_fix()
                st.session_state.applied_fixes.add(fix_key)
                st.rerun()


def _apply_deduplicate(executor, recipe, current_df):
    """Apply deduplication step."""
    step = create_transform_step(
        TransformOp.DEDUPLICATE,
        {"subset": None, "keep": "first"},
        {c: str(current_df[c].dtype) for c in current_df.columns},
        {c: str(current_df[c].dtype) for c in current_df.columns},
        current_df.height,
        0,
    )
    step.step_id = len(recipe)
    result = apply_transform(executor, recipe, step)
    st.session_state.recipe = result.recipe


def _apply_drop_constant(executor, recipe, current_df, const_cols):
    """Drop constant columns."""
    step = create_transform_step(
        TransformOp.DROP_COLUMNS,
        {"columns": const_cols},
        {c: str(current_df[c].dtype) for c in current_df.columns},
        {c: str(current_df[c].dtype) for c in current_df.columns if c not in const_cols},
        current_df.height,
        len(const_cols),
    )
    step.step_id = len(recipe)
    result = apply_transform(executor, recipe, step)
    st.session_state.recipe = result.recipe


def _apply_drop_column(executor, recipe, current_df, col):
    """Drop a single column."""
    step = create_transform_step(
        TransformOp.DROP_COLUMNS,
        {"columns": [col]},
        {c: str(current_df[c].dtype) for c in current_df.columns},
        {c: str(current_df[c].dtype) for c in current_df.columns if c != col},
        current_df.height,
        1,
    )
    step.step_id = len(recipe)
    result = apply_transform(executor, recipe, step)
    st.session_state.recipe = result.recipe


def _apply_drop_nonfinite(executor, recipe, current_df, col):
    """Drop rows with non-finite values in a column."""
    # Filter out NaN and Inf
    step = create_transform_step(
        TransformOp.FILTER,
        {"expression": f"(pl.col('{col}').is_not_null() & ~pl.col('{col}').is_infinite() & ~pl.col('{col}').is_nan())"},
        {c: str(current_df[c].dtype) for c in current_df.columns},
        {c: str(current_df[c].dtype) for c in current_df.columns},
        current_df.height,
        0,
    )
    step.step_id = len(recipe)
    result = apply_transform(executor, recipe, step)
    st.session_state.recipe = result.recipe


def _apply_group_rare(executor, recipe, current_df, col):
    """Group rare categories into 'Other'."""
    # Find categories with < 5 observations
    vc = current_df[col].value_counts()
    rare = vc.filter(pl.col("count") < 5)[col].to_list()
    if not rare:
        st.info("No rare categories found (all have ≥5 observations)")
        return

    # Create recode mapping
    mapping = {cat: "Other" for cat in rare}

    step = create_transform_step(
        TransformOp.RECODE_CATEGORICAL,
        {"mapping": {col: mapping}},
        {c: str(current_df[c].dtype) for c in current_df.columns},
        {c: str(current_df[c].dtype) for c in current_df.columns},
        current_df.height,
        1,
    )
    step.step_id = len(recipe)
    result = apply_transform(executor, recipe, step)
    st.session_state.recipe = result.recipe


def _render_outlier_cards(executor, recipe, current_df, column_roles):
    """Render outlier detection cards for continuous variables."""
    continuous_roles = [cr for cr in column_roles if cr.semantic_role == SemanticRole.CONTINUOUS]

    for cr in continuous_roles:
        col = cr.column
        if col not in current_df.columns:
            continue

        s = current_df[col]
        if not s.dtype.is_numeric():
            continue

        finite = s.drop_nulls()
        if len(finite) < 10:
            continue

        q1 = finite.quantile(0.25)
        q3 = finite.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 3 * iqr
        upper = q3 + 3 * iqr

        outliers = finite.filter((pl.col(col) < lower) | (pl.col(col) > upper))
        n_outliers = len(outliers)

        if n_outliers > 0:
            fix_key = f"outliers_{col}"
            pct = n_outliers / len(finite) * 100

            _render_issue_card(
                title=f"📊 Outliers: `{col}` ({n_outliers} values, {pct:.1f}%)",
                description=f"Values outside [{lower:.2f}, {upper:.2f}] (3×IQR). Range: {finite.min():.2f}–{finite.max():.2f}, IQR: [{q1:.2f}, {q3:.2f}]",
                fix_key=fix_key,
                fix_button_label="Flag & Exclude Outliers",
                on_fix=lambda c=col, lo=lower, hi=upper: _apply_flag_outliers(executor, recipe, current_df, c, lo, hi),
                fix_applied=fix_key in st.session_state.applied_fixes,
            )


def _apply_flag_outliers(executor, recipe, current_df, col, lower, upper):
    """Flag outliers by adding a boolean column and optionally filtering."""
    # Add outlier flag column
    step = create_transform_step(
        TransformOp.FLAG_OUTLIERS,
        {"column": col, "lower": float(lower), "upper": float(upper), "flag_column": f"{col}_outlier"},
        {c: str(current_df[c].dtype) for c in current_df.columns},
        {**{c: str(current_df[c].dtype) for c in current_df.columns}, f"{col}_outlier": "Boolean"},
        current_df.height,
        1,
    )
    step.step_id = len(recipe)
    result = apply_transform(executor, recipe, step)
    st.session_state.recipe = result.recipe


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
            st.info("Free-text filter expressions are not allowed for security. Use the range/selection controls above.")
            expr = "pl.lit(True)"

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
