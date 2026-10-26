"""Question screen - Select analysis goal and variables."""

from __future__ import annotations

import hashlib
import json
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

    # Question cards - simplified to 4 main goals
    st.markdown("### What would you like to know?")

    question_cards = [
        {
            "goal": Goal.COMPARE_TWO_MEANS,
            "label": "Compare groups",
            "icon": "📊",
            "description": "Compare a numeric outcome between two groups",
            "requires": ["continuous outcome", "categorical group (2 levels)"],
        },
        {
            "goal": Goal.COMPARE_PAIRED_MEANS,
            "label": "Compare before/after",
            "icon": "🔄",
            "description": "Compare the same units measured twice",
            "requires": ["continuous outcome", "pair identifier", "occasion variable"],
        },
        {
            "goal": Goal.EXPLORE_LINEAR_RELATIONSHIP,
            "label": "Explore a relationship",
            "icon": "📈",
            "description": "Explore how two variables relate",
            "requires": ["two numeric or ordinal variables"],
        },
        {
            "goal": Goal.DESCRIBE_DATA,
            "label": "Describe my data",
            "icon": "📋",
            "description": "Get comprehensive summaries and visualizations",
            "requires": ["any data"],
        },
    ]

    # Display as cards
    cols = st.columns(2)
    for i, q in enumerate(question_cards):
        with cols[i % 2], st.container(border=True):
            st.markdown(f"### {q['icon']} {q['label']}")
            st.caption(q["description"])
            st.caption(f"Requires: {', '.join(q['requires'])}")
            if st.button("Select", key=f"select_{q['goal'].value}", use_container_width=True):
                # Invalidate any pending analysis when goal changes
                if st.session_state.get("selected_goal") != q["goal"]:
                    _invalidate_pending_analysis()
                st.session_state.selected_goal = q["goal"]
                st.rerun()

    # If goal selected, show configuration
    if "selected_goal" in st.session_state:
        goal = st.session_state.selected_goal
        st.divider()
        _render_goal_config(ws, goal, df, role_map, continuous_cols, categorical_cols, ordinal_cols, date_cols, id_cols, dataset_ref)

    # Back button
    if st.button("← Back to Preparation"):
        st.session_state.current_stage = JobStatus.DATA_READY.value
        if "selected_goal" in st.session_state:
            del st.session_state.selected_goal
        st.rerun()


def _invalidate_pending_analysis() -> None:
    """Invalidate any pending analysis when configuration changes."""
    if "pending_analysis_request" in st.session_state:
        del st.session_state.pending_analysis_request
    if "analysis_plan" in st.session_state:
        del st.session_state.analysis_plan
    if "results" in st.session_state:
        st.session_state.results = None
    if "plots" in st.session_state:
        st.session_state.plots = []


def _compute_config_hash(goal, variables, group_levels, contrast, study_design, confidence, alternative, missing_policy, nonfinite_policy, seed) -> str:
    """Compute a hash of the analysis configuration for change detection."""
    import hashlib
    import json
    config = {
        "goal": goal.value if goal else None,
        "variables": variables,
        "group_levels": group_levels,
        "contrast": contrast,
        "study_design": study_design.value if study_design else None,
        "confidence": confidence,
        "alternative": alternative,
        "missing_policy": missing_policy,
        "nonfinite_policy": nonfinite_policy,
        "seed": seed,
    }
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]


def _check_and_invalidate_config(goal, variables, group_levels, contrast, study_design, confidence, alternative, missing_policy, nonfinite_policy, seed) -> None:
    """Check if configuration changed and invalidate pending analysis if so."""
    import hashlib
    import json
    
    current_hash = _compute_config_hash(goal, variables, group_levels, contrast, study_design, confidence, alternative, missing_policy, nonfinite_policy, seed)
    last_hash = st.session_state.get("last_analysis_config_hash")
    
    if last_hash is not None and last_hash != current_hash:
        _invalidate_pending_analysis()
    
    st.session_state.last_analysis_config_hash = current_hash


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

    # Define sub-goals for "Explore a relationship"
    if goal == Goal.EXPLORE_LINEAR_RELATIONSHIP:
        sub_goals = {
            Goal.EXPLORE_LINEAR_RELATIONSHIP: ("Linear relationship (Pearson)", "Measures linear association between two numeric variables", "two continuous variables"),
            Goal.EXPLORE_ORDERED_RELATIONSHIP: ("Ordered relationship (Spearman)", "Measures monotonic association for numeric or ordinal variables", "two numeric or ordinal variables"),
        }
    elif goal == Goal.COMPARE_TWO_MEANS:
        sub_goals = {goal: (goal.value.replace('_', ' ').title(), "Compare a numeric outcome between two groups", "continuous outcome, categorical group (2 levels)")}
    elif goal == Goal.COMPARE_PAIRED_MEANS:
        sub_goals = {goal: (goal.value.replace('_', ' ').title(), "Compare the same units measured twice", "continuous outcome, pair identifier, occasion variable")}
    else:  # DESCRIBE_DATA
        sub_goals = {goal: (goal.value.replace('_', ' ').title(), "Get comprehensive summaries and visualizations", "any data")}

    # Show sub-goal selection for Explore relationship
    actual_goal = goal
    if goal == Goal.EXPLORE_LINEAR_RELATIONSHIP:
        st.markdown("### What kind of relationship?")
        sub_goal_labels = {k: v[0] for k, v in sub_goals.items()}
        selected_sub = st.radio(
            "Relationship type",
            options=list(sub_goals.keys()),
            format_func=lambda k: sub_goal_labels[k],
            horizontal=True,
            key="sub_goal_radio",
        )
        actual_goal = selected_sub
        st.caption(sub_goals[actual_goal][1])
        st.caption(f"Requires: {sub_goals[actual_goal][2]}")
    else:
        st.caption(sub_goals[actual_goal][1])
        st.caption(f"Requires: {sub_goals[actual_goal][2]}")

    # Configuration form
    with st.form("analysis_config"):
        variables = {}
        group_levels = None
        contrast = None

        if actual_goal == Goal.COMPARE_TWO_MEANS:
            st.write("**Compare a numeric outcome between two groups**")
            variables["outcome"] = st.selectbox("Outcome (continuous)", continuous_cols, key="outcome_select")
            variables["group"] = st.selectbox("Group (categorical)", categorical_cols, key="group_select")

            if variables["group"] in df.columns:
                levels = df[variables["group"]].unique().to_list()
                if len(levels) >= 2:
                    group_levels = st.multiselect("Select two groups", levels, default=levels[:2], key="group_levels")
                    if len(group_levels) == 2:
                        contrast = st.selectbox(
                            "Contrast direction",
                            [f"{group_levels[0]} minus {group_levels[1]}", f"{group_levels[1]} minus {group_levels[0]}"],
                            key="contrast_select",
                        )
                        contrast = contrast.replace(" minus ", "_minus_")

        elif actual_goal == Goal.COMPARE_PAIRED_MEANS:
            st.write("**Compare the same units measured twice**")
            variables["outcome"] = st.selectbox("Outcome (continuous)", continuous_cols, key="outcome_paired")
            variables["pair_id"] = st.selectbox("Pair identifier", id_cols + categorical_cols, key="pair_id")
            variables["occasion"] = st.selectbox("Occasion (time/condition)", date_cols + categorical_cols, key="occasion")

            if variables["occasion"] in df.columns:
                occasions = df[variables["occasion"]].unique().to_list()
                if len(occasions) >= 2:
                    selected = st.multiselect("Select two occasions", occasions, default=occasions[:2], key="occasions_select")
                    if len(selected) == 2:
                        contrast = st.selectbox(
                            "Contrast direction",
                            [f"{selected[0]} minus {selected[1]}", f"{selected[1]} minus {selected[0]}"],
                            key="contrast_paired",
                        )
                        contrast = contrast.replace(" minus ", "_minus_")

        elif actual_goal in (Goal.EXPLORE_LINEAR_RELATIONSHIP, Goal.EXPLORE_ORDERED_RELATIONSHIP):
            st.write(f"**Explore {'linear' if actual_goal == Goal.EXPLORE_LINEAR_RELATIONSHIP else 'monotonic'} relationship**")
            variables["outcome"] = st.selectbox("Variable X", continuous_cols + ordinal_cols, key="outcome_corr")
            variables["predictor"] = st.selectbox("Variable Y", [c for c in continuous_cols + ordinal_cols if c != variables["outcome"]], key="predictor_corr")

        elif actual_goal == Goal.DESCRIBE_DATA:
            st.write("**Generate descriptive statistics for all variables**")
            # No variables needed - we'll add a dummy for validation

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
            key="study_design_radio",
        )

        if study_design == StudyDesign.UNKNOWN:
            st.warning("⚠️ With unknown design, only descriptive results will be available.")

        # Advanced options
        with st.expander("Advanced Options"):
            col1, col2 = st.columns(2)
            with col1:
                confidence = st.slider("Confidence level", 0.80, 0.99, 0.95, 0.01, key="confidence_slider")
                alternative = st.selectbox("Alternative hypothesis", [a.value for a in Alternative], key="alternative_select")
            with col2:
                missing_policy = st.selectbox("Missing data policy", [m.value for m in MissingPolicy], key="missing_policy")
                nonfinite_policy = st.selectbox("Non-finite values", [n.value for n in NonFinitePolicy], key="nonfinite_policy")

            seed = st.number_input("Random seed", 0, 2**31 - 1, 42, key="seed_input")

        # Submit
        submitted = st.form_submit_button("Check Eligibility", type="primary", use_container_width=True)

        if submitted:
            # Validate group levels
            if actual_goal == Goal.COMPARE_TWO_MEANS and (not group_levels or len(group_levels) != 2):
                st.error("Please select exactly two groups")
                return

            # For paired means, get pair_id and occasion from variables
            _pair_id = variables.get("pair_id")
            _occasion = variables.get("occasion")
            if actual_goal == Goal.COMPARE_PAIRED_MEANS:
                if not _pair_id or not _occasion:
                    st.error("Please provide pair identifier and occasion")
                    return

            # Build request
            request = AnalysisRequest(
                goal=actual_goal,
                variables=variables if actual_goal != Goal.DESCRIBE_DATA else {"dummy": continuous_cols[0] if continuous_cols else (categorical_cols[0] if categorical_cols else "x")},
                group_levels=group_levels,
                contrast=contrast,
                study_design=study_design,
                design_confirmation_source="user",
                estimand=_get_estimand_description(actual_goal, variables),
                missing_policy=MissingPolicy(missing_policy),
                nonfinite_policy=NonFinitePolicy(nonfinite_policy),
                alternative=Alternative(alternative),
                confidence_level=confidence,
                seed=seed,
            )

            # Check if configuration changed and invalidate if needed
            _check_and_invalidate_config(
                actual_goal, variables, group_levels, contrast, 
                study_design, confidence, alternative, missing_policy, 
                nonfinite_policy, seed
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