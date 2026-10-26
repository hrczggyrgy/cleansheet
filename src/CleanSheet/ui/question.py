"""Question screen - Select analysis goal and variables."""

from __future__ import annotations

import streamlit as st

from CleanSheet.contracts import (
    Alternative,
    AnalysisRequest,
    Goal,
    JobStatus,
    MissingPolicy,
    NonFinitePolicy,
    StudyDesign,
)
from CleanSheet.engine.execution import LazyExecutor, get_or_create_prepared
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.recommend import check_eligibility


def render_question(ws: Workspace) -> None:
    """Render analysis question selection screen."""
    dataset_ref = st.session_state.get("dataset_ref")
    column_roles = st.session_state.get("column_roles", [])
    recipe = st.session_state.get("recipe", [])

    if dataset_ref is None:
        st.error("No dataset loaded.")
        return

    st.title("❓ Ask a Question")
    st.caption("Choose what you want to learn from your data.")

    # Get prepared data for recommendations
    executor = LazyExecutor(ws, dataset_ref)
    df = get_or_create_prepared(ws, dataset_ref, [s.model_dump() for s in recipe]) if recipe else executor.preview(1000)

    # Build role mapping
    role_map = {r.column: r.semantic_role.value for r in column_roles}
    continuous_cols = [c for c, r in role_map.items() if r == "continuous"]
    categorical_cols = [c for c, r in role_map.items() if r == "categorical"]
    ordinal_cols = [c for c, r in role_map.items() if r == "ordinal"]
    date_cols = [c for c, r in role_map.items() if r == "date"]
    id_cols = [c for c, r in role_map.items() if r == "identifier"]

    # Question cards
    st.markdown("### What would you like to know?")

    questions = [
        {
            "goal": Goal.COMPARE_TWO_MEANS,
            "label": "Compare two groups",
            "icon": "📊",
            "description": "Compare a numeric outcome between two groups (e.g., treatment vs control)",
            "requires": ["continuous outcome", "categorical group (2 levels)"],
        },
        {
            "goal": Goal.COMPARE_PAIRED_MEANS,
            "label": "Compare before/after",
            "icon": "🔄",
            "description": "Compare the same units measured twice (e.g., pre/post treatment)",
            "requires": ["continuous outcome", "pair identifier", "occasion variable"],
        },
        {
            "goal": Goal.EXPLORE_LINEAR_RELATIONSHIP,
            "label": "Explore linear relationship",
            "icon": "📈",
            "description": "Measure linear association between two numeric variables",
            "requires": ["two continuous variables"],
        },
        {
            "goal": Goal.EXPLORE_ORDERED_RELATIONSHIP,
            "label": "Explore ordered relationship",
            "icon": "📉",
            "description": "Measure monotonic association (Spearman) for continuous or ordinal variables",
            "requires": ["two continuous or ordinal variables"],
        },
        {
            "goal": Goal.CATEGORICAL_ASSOCIATION,
            "label": "Test category association",
            "icon": "🔗",
            "description": "Test if two categorical variables are associated",
            "requires": ["two categorical variables"],
        },
        {
            "goal": Goal.SPARSE_2X2_TABLE,
            "label": "Analyze 2×2 table",
            "icon": "🎯",
            "description": "Fisher's exact test for sparse 2×2 contingency tables",
            "requires": ["two binary categorical variables"],
        },
        {
            "goal": Goal.DESCRIBE_DATA,
            "label": "Describe my data",
            "icon": "📋",
            "description": "Get comprehensive descriptive statistics and visualizations",
            "requires": ["any data"],
        },
    ]

    # Display as cards
    cols = st.columns(3)
    for i, q in enumerate(questions):
        with cols[i % 3], st.container(border=True):
            st.markdown(f"### {q['icon']} {q['label']}")
            st.caption(q["description"])
            st.caption(f"Requires: {', '.join(q['requires'])}")
            if st.button("Select", key=f"select_{q['goal'].value}", use_container_width=True):
                st.session_state.selected_goal = q["goal"]
                st.rerun()

    # If goal selected, show configuration
    if "selected_goal" in st.session_state:
        goal = st.session_state.selected_goal
        st.divider()
        _render_goal_config(ws, goal, df, role_map, continuous_cols, categorical_cols, ordinal_cols, date_cols, id_cols, dataset_ref)

    # Back button
    if st.button("← Back to Preparation"):
        st.session_state.current_stage = JobStatus.DATA_READY
        if "selected_goal" in st.session_state:
            del st.session_state.selected_goal
        st.rerun()


def _render_goal_config(
    ws: Workspace,
    goal: Goal,
    df,
    role_map: dict,
    continuous_cols: list,
    categorical_cols: list,
    ordinal_cols: list,
    date_cols: list,
    id_cols: list,
    dataset_ref,
) -> None:
    """Render configuration for selected goal."""
    st.markdown(f"### Configure: {goal.value.replace('_', ' ').title()}")

    with st.form("analysis_config"):
        variables = {}
        group_levels = None
        contrast = None
        pair_id = None
        occasion = None

        if goal == Goal.COMPARE_TWO_MEANS:
            st.write("**Compare a numeric outcome between two groups**")
            variables["outcome"] = st.selectbox("Outcome (continuous)", continuous_cols)
            variables["group"] = st.selectbox("Group (categorical)", categorical_cols)

            if variables["group"] in df.columns:
                levels = df[variables["group"]].unique().to_list()
                if len(levels) >= 2:
                    group_levels = st.multiselect("Select two groups", levels, default=levels[:2])
                    if len(group_levels) == 2:
                        contrast = st.selectbox(
                            "Contrast direction",
                            [f"{group_levels[0]} minus {group_levels[1]}", f"{group_levels[1]} minus {group_levels[0]}"],
                        )
                        contrast = contrast.replace(" minus ", "_minus_")

        elif goal == Goal.COMPARE_PAIRED_MEANS:
            st.write("**Compare the same units measured twice**")
            variables["outcome"] = st.selectbox("Outcome (continuous)", continuous_cols)
            variables["pair_id"] = st.selectbox("Pair identifier", id_cols + categorical_cols)
            variables["occasion"] = st.selectbox("Occasion (time/condition)", date_cols + categorical_cols)

            if variables["occasion"] in df.columns:
                occasions = df[variables["occasion"]].unique().to_list()
                if len(occasions) >= 2:
                    selected = st.multiselect("Select two occasions", occasions, default=occasions[:2])
                    if len(selected) == 2:
                        contrast = st.selectbox(
                            "Contrast direction",
                            [f"{selected[0]} minus {selected[1]}", f"{selected[1]} minus {selected[0]}"],
                        )
                        contrast = contrast.replace(" minus ", "_minus_")

        elif goal in (Goal.EXPLORE_LINEAR_RELATIONSHIP, Goal.EXPLORE_ORDERED_RELATIONSHIP):
            st.write(f"**Explore {'linear' if goal == Goal.EXPLORE_LINEAR_RELATIONSHIP else 'monotonic'} relationship**")
            variables["outcome"] = st.selectbox("Variable X", continuous_cols + ordinal_cols)
            variables["predictor"] = st.selectbox("Variable Y", [c for c in continuous_cols + ordinal_cols if c != variables["outcome"]])

        elif goal == Goal.CATEGORICAL_ASSOCIATION:
            st.write("**Test association between two categorical variables**")
            variables["outcome"] = st.selectbox("Row variable", categorical_cols)
            variables["group"] = st.selectbox("Column variable", [c for c in categorical_cols if c != variables["outcome"]])

        elif goal == Goal.SPARSE_2X2_TABLE:
            st.write("**Fisher's exact test for 2×2 table**")
            variables["outcome"] = st.selectbox("Row variable (binary)", [c for c in categorical_cols if df[c].n_unique() == 2])
            variables["group"] = st.selectbox("Column variable (binary)", [c for c in categorical_cols if df[c].n_unique() == 2 and c != variables["outcome"]])

        elif goal == Goal.DESCRIBE_DATA:
            st.write("**Generate descriptive statistics for all variables**")
            # No variables needed

        # Study design
        st.markdown("### Study Design")
        study_design = st.radio(
            "How were observations collected?",
            [StudyDesign.INDEPENDENT, StudyDesign.PAIRED, StudyDesign.UNKNOWN],
            format_func=lambda x: {
                StudyDesign.INDEPENDENT: "Independent observations (different units in each group)",
                StudyDesign.PAIRED: "Paired observations (same units measured twice)",
                StudyDesign.UNKNOWN: "Unknown / Not sure",
            }[x],
            horizontal=False,
        )

        if study_design == StudyDesign.UNKNOWN:
            st.warning("⚠️ With unknown design, only descriptive results will be available.")

        # Advanced options
        with st.expander("Advanced Options"):
            col1, col2 = st.columns(2)
            with col1:
                confidence = st.slider("Confidence level", 0.80, 0.99, 0.95, 0.01)
                alternative = st.selectbox("Alternative hypothesis", [a.value for a in Alternative])
            with col2:
                missing_policy = st.selectbox("Missing data policy", [m.value for m in MissingPolicy])
                nonfinite_policy = st.selectbox("Non-finite values", [n.value for n in NonFinitePolicy])

            seed = st.number_input("Random seed", 0, 2**31 - 1, 42)

        # Submit
        submitted = st.form_submit_button("Check Eligibility", type="primary", use_container_width=True)

        if submitted:
            # Validate group levels
            if goal == Goal.COMPARE_TWO_MEANS and (not group_levels or len(group_levels) != 2):
                st.error("Please select exactly two groups")
                return

            # For paired means, get pair_id and occasion from variables
            _pair_id = variables.get("pair_id")
            _occasion = variables.get("occasion")
            if goal == Goal.COMPARE_PAIRED_MEANS:
                if not _pair_id or not _occasion:
                    st.error("Please provide pair identifier and occasion")
                    return

            # Build request
            request = AnalysisRequest(
                goal=goal,
                variables=variables,
                group_levels=group_levels,
                contrast=contrast,
                study_design=study_design,
                design_confirmation_source="user",
                estimand=_get_estimand_description(goal, variables),
                missing_policy=MissingPolicy(missing_policy),
                nonfinite_policy=NonFinitePolicy(nonfinite_policy),
                alternative=Alternative(alternative),
                confidence_level=confidence,
                seed=seed,
            )

            # Check eligibility
            with st.spinner("Checking eligibility..."):
                recipe = st.session_state.get("recipe", [])
                recipe_steps = [s.model_dump() for s in recipe]
                column_roles = st.session_state.get("column_roles", [])
                eligibility = check_eligibility(ws, dataset_ref, request, column_roles, recipe_steps)

            if not eligibility.allowed:
                st.error("**Analysis not eligible:**")
                for reason in eligibility.reasons:
                    st.error(f"- {reason}")
                if eligibility.warnings:
                    for w in eligibility.warnings:
                        st.warning(w)
                return

            # Show eligibility result
            st.success("✅ Analysis is eligible!")
            if eligibility.warnings:
                for w in eligibility.warnings:
                    st.warning(w)

            # Store request for confirmation
            st.session_state.pending_analysis_request = request

    # Confirmation button OUTSIDE the form
    if "pending_analysis_request" in st.session_state:
        if st.button("Run Analysis", type="primary", use_container_width=True):
            st.session_state.analysis_plan = st.session_state.pending_analysis_request
            del st.session_state.pending_analysis_request
            st.session_state.current_stage = JobStatus.RUNNING
            st.rerun()


def _get_estimand_description(goal: Goal, variables: dict) -> str:
    """Generate human-readable estimand description."""
    descriptions = {
        Goal.COMPARE_TWO_MEANS: f"Difference in mean {variables.get('outcome', 'outcome')} between {variables.get('group', 'groups')}",
        Goal.COMPARE_PAIRED_MEANS: f"Mean paired difference in {variables.get('outcome', 'outcome')}",
        Goal.EXPLORE_LINEAR_RELATIONSHIP: f"Pearson correlation between {variables.get('outcome', 'X')} and {variables.get('predictor', 'Y')}",
        Goal.EXPLORE_ORDERED_RELATIONSHIP: f"Spearman correlation between {variables.get('outcome', 'X')} and {variables.get('predictor', 'Y')}",
        Goal.CATEGORICAL_ASSOCIATION: f"Association between {variables.get('outcome', 'row')} and {variables.get('group', 'column')}",
        Goal.SPARSE_2X2_TABLE: f"Odds ratio for {variables.get('outcome', 'row')} by {variables.get('group', 'column')}",
        Goal.DESCRIBE_DATA: "Descriptive statistics for all variables",
    }
    return descriptions.get(goal, "Analysis")
