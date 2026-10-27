"""Question screen - Select analysis goal and variables."""

from __future__ import annotations

import hashlib
import json
import streamlit as st

from CleanSheet.contracts import (
    Alternative,
    AnalysisMode,
    AnalysisRequest,
    DiscoveryCandidate,
    Goal,
    JobStatus,
    MissingPolicy,
    NonFinitePolicy,
    StudyDesign,
)
from CleanSheet.engine.assumptions import run_assumption_diagnostics, AssumptionReport
from CleanSheet.engine.discovery import run_autonomous_discovery
from CleanSheet.engine.execution import LazyExecutor, get_or_create_prepared
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.recommend import check_eligibility
from CleanSheet.ui.accessibility import (
    render_skip_link,
    set_page_main_content_id,
    announce_to_screen_reader,
    render_focus_visible_style,
)


def render_question(ws: Workspace) -> None:
    """Render analysis question selection screen."""
    dataset_ref = st.session_state.get("dataset_ref")
    column_roles = st.session_state.get("column_roles", [])
    recipe = st.session_state.get("recipe", [])
    study_context = st.session_state.get("study_context")

    # Accessibility
    render_skip_link()
    render_focus_visible_style()
    set_page_main_content_id()

    if dataset_ref is None:
        st.error("No dataset loaded.")
        return

    st.title("❓ Ask a Question")
    st.caption("Choose what you want to learn from your data.")
    announce_to_screen_reader("Question selection page loaded. Choose an analysis goal and configure variables.")

    # Get prepared data for recommendations
    executor = LazyExecutor(ws, dataset_ref)
    df = get_or_create_prepared(ws, dataset_ref, [s.model_dump() for s in recipe]) if recipe else executor.preview(1000)

    # Build role mapping
    role_map = {r.column: r.semantic_role.value for r in column_roles}
    continuous_cols = [c for c, r in role_map.items() if r == "continuous"]
    discrete_cols = [c for c, r in role_map.items() if r == "discrete"]
    ordinal_cols = [c for c, r in role_map.items() if r == "ordinal"]
    nominal_cols = [c for c, r in role_map.items() if r == "nominal"]
    binary_cols = [c for c, r in role_map.items() if r == "binary"]
    date_cols = [c for c, r in role_map.items() if r == "date"]
    datetime_cols = [c for c, r in role_map.items() if r == "datetime"]
    id_cols = [c for c, r in role_map.items() if r == "identifier"]

    # All categorical for grouping
    categorical_cols = nominal_cols + ordinal_cols + binary_cols
    # All numeric for outcomes
    numeric_cols = continuous_cols + discrete_cols + ordinal_cols

    # Mode selector tabs
    mode_tabs = st.tabs([
        "🎯 Guided Analysis",
        "🔍 Target Scan", 
        "✨ Autonomous Discovery"
    ])
    
    with mode_tabs[0]:
        st.session_state.analysis_mode = AnalysisMode.GUIDED
        _render_guided_mode(ws, dataset_ref, column_roles, recipe, study_context)
    
    with mode_tabs[1]:
        st.session_state.analysis_mode = AnalysisMode.TARGET_SCAN
        _render_target_scan_mode(ws, dataset_ref, column_roles, recipe, study_context)
    
    with mode_tabs[2]:
        st.session_state.analysis_mode = AnalysisMode.AUTONOMOUS_DISCOVERY
        _render_discovery_mode(ws, dataset_ref, column_roles, recipe, study_context)


def _render_guided_mode(ws: Workspace, dataset_ref, column_roles, recipe, study_context) -> None:
    """Render the guided analysis mode (original question cards)."""
    executor = LazyExecutor(ws, dataset_ref)
    df = get_or_create_prepared(ws, dataset_ref, [s.model_dump() for s in recipe]) if recipe else executor.preview(1000)

    # Build role mapping
    role_map = {r.column: r.semantic_role.value for r in column_roles}
    continuous_cols = [c for c, r in role_map.items() if r == "continuous"]
    discrete_cols = [c for c, r in role_map.items() if r == "discrete"]
    ordinal_cols = [c for c, r in role_map.items() if r == "ordinal"]
    nominal_cols = [c for c, r in role_map.items() if r == "nominal"]
    binary_cols = [c for c, r in role_map.items() if r == "binary"]
    date_cols = [c for c, r in role_map.items() if r == "date"]
    datetime_cols = [c for c, r in role_map.items() if r == "datetime"]
    id_cols = [c for c, r in role_map.items() if r == "identifier"]

    # All categorical for grouping
    categorical_cols = nominal_cols + ordinal_cols + binary_cols
    # All numeric for outcomes
    numeric_cols = continuous_cols + discrete_cols + ordinal_cols

    # Question cards - 5 main goals
    st.markdown("### What would you like to know?")

    question_cards = [
        {
            "goal": Goal.COMPARE_TWO_MEANS,
            "label": "Compare two groups",
            "icon": "📊",
            "description": "Compare a numeric outcome between two groups",
            "requires": ["numeric outcome", "categorical group (2 levels)"],
        },
        {
            "goal": Goal.COMPARE_K_MEANS,
            "label": "Compare 3+ groups",
            "icon": "📊",
            "description": "Compare a numeric outcome across three or more groups",
            "requires": ["numeric outcome", "categorical group (3+ levels)"],
        },
        {
            "goal": Goal.COMPARE_PAIRED_MEANS,
            "label": "Compare before/after",
            "icon": "🔄",
            "description": "Compare the same units measured twice",
            "requires": ["numeric outcome", "pair identifier", "occasion variable"],
        },
        {
            "goal": Goal.EXPLORE_LINEAR_RELATIONSHIP,
            "label": "Explore linear relationship",
            "icon": "📈",
            "description": "Measure linear correlation between two numeric variables",
            "requires": ["two continuous variables"],
        },
        {
            "goal": Goal.EXPLORE_ORDERED_RELATIONSHIP,
            "label": "Explore monotonic relationship",
            "icon": "📈",
            "description": "Measure rank correlation (Spearman) for numeric or ordinal variables",
            "requires": ["two numeric or ordinal variables"],
        },
        {
            "goal": Goal.CATEGORICAL_ASSOCIATION,
            "label": "Test category association",
            "icon": "🔗",
            "description": "Test if two categorical variables are associated",
            "requires": ["two categorical variables"],
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
    cols = st.columns(3)
    for i, q in enumerate(question_cards):
        with cols[i % 3], st.container(border=True):
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
        _render_goal_config(ws, goal, df, role_map, numeric_cols, categorical_cols, ordinal_cols, date_cols, datetime_cols, id_cols, dataset_ref, study_context)

    # Back button
    if st.button("← Back to Preparation"):
        st.session_state.current_stage = JobStatus.DATA_READY
        if "selected_goal" in st.session_state:
            del st.session_state.selected_goal
        st.rerun()


def _invalidate_pending_analysis() -> None:
    """Invalidate any pending analysis when configuration changes."""
    for key in ["pending_analysis_request", "analysis_plan", "results", "plots", "assumption_report"]:
        if key in st.session_state:
            del st.session_state[key]


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
    numeric_cols: list,
    categorical_cols: list,
    ordinal_cols: list,
    date_cols: list,
    datetime_cols: list,
    id_cols: list,
    dataset_ref,
    study_context,
) -> None:
    """Render configuration for selected goal."""

    st.markdown(f"### Configure: {goal.value.replace('_', ' ').title()}")

    # Configuration form
    with st.form("analysis_config"):
        variables = {}
        group_levels = None
        contrast = None

        if goal == Goal.COMPARE_TWO_MEANS:
            st.write("**Compare a numeric outcome between two groups**")
            variables["outcome"] = st.selectbox("Outcome (numeric)", numeric_cols, key="outcome_select")
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

        elif goal == Goal.COMPARE_K_MEANS:
            st.write("**Compare a numeric outcome across 3+ groups**")
            variables["outcome"] = st.selectbox("Outcome (numeric)", numeric_cols, key="outcome_k_select")
            variables["group"] = st.selectbox("Group (categorical)", categorical_cols, key="group_k_select")

            if variables["group"] in df.columns:
                levels = df[variables["group"]].unique().to_list()
                if len(levels) >= 3:
                    group_levels = st.multiselect("Select groups", levels, default=levels[:3], key="group_levels_k")
                    st.caption("Post-hoc pairwise comparisons will be run automatically if significant.")

        elif goal == Goal.COMPARE_PAIRED_MEANS:
            st.write("**Compare the same units measured twice**")
            
            # Data format selector
            paired_format = st.radio(
                "Data format:",
                ["long", "wide"],
                format_func=lambda x: {
                    "long": "📋 Long format (one row per measurement) — columns: Subject ID, Occasion, Outcome",
                    "wide": "📊 Wide format (one row per subject) — columns: Subject ID, Pre-Score, Post-Score"
                }[x],
                horizontal=True,
                key="paired_format",
                help="Long: Subject_ID | Timepoint | Value. Wide: Subject_ID | Pre_Value | Post_Value"
            )
            
            variables["outcome"] = st.selectbox("Outcome (numeric)", numeric_cols, key="outcome_paired")
            
            if paired_format == "long":
                variables["pair_id"] = st.selectbox("Subject ID column", id_cols + categorical_cols, key="pair_id")
                variables["occasion"] = st.selectbox("Occasion column", date_cols + datetime_cols + categorical_cols, key="occasion")
                
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
            else:
                # Wide format: need pre and post columns
                pre_col = st.selectbox("Pre/Before measurement", numeric_cols, key="pre_col")
                post_col = st.selectbox("Post/After measurement", [c for c in numeric_cols if c != pre_col], key="post_col")
                variables["pre_col"] = pre_col
                variables["post_col"] = post_col
                variables["pair_id"] = st.selectbox("Subject ID column", id_cols + categorical_cols, key="pair_id_wide")
                contrast = f"{post_col}_minus_{pre_col}"

        elif goal in (Goal.EXPLORE_LINEAR_RELATIONSHIP, Goal.EXPLORE_ORDERED_RELATIONSHIP):
            st.write(f"**Explore {'linear' if goal == Goal.EXPLORE_LINEAR_RELATIONSHIP else 'monotonic'} relationship**")
            variables["outcome"] = st.selectbox("Variable X", numeric_cols + ordinal_cols, key="outcome_corr")
            variables["predictor"] = st.selectbox("Variable Y", [c for c in numeric_cols + ordinal_cols if c != variables["outcome"]], key="predictor_corr")

        elif goal == Goal.CATEGORICAL_ASSOCIATION:
            st.write("**Test association between two categorical variables**")
            variables["outcome"] = st.selectbox("Row variable", categorical_cols, key="outcome_cat")
            variables["group"] = st.selectbox("Column variable", [c for c in categorical_cols if c != variables["outcome"]], key="group_cat")

        elif goal == Goal.DESCRIBE_DATA:
            st.write("**Generate descriptive statistics for all variables**")
            # No variables needed

        # Study design - pre-filled from study context
        st.markdown("### Study Design")
        default_design = StudyDesign.INDEPENDENT
        if study_context:
            if study_context.row_independence == "paired":
                default_design = StudyDesign.PAIRED

        study_design = st.radio(
            "How were observations collected?",
            [StudyDesign.INDEPENDENT, StudyDesign.PAIRED, StudyDesign.UNKNOWN],
            format_func=lambda x: {
                StudyDesign.INDEPENDENT: "Independent observations (different units in each group)",
                StudyDesign.PAIRED: "Paired observations (same units measured twice)",
                StudyDesign.UNKNOWN: "Unknown / Not sure",
            }[x],
            horizontal=False,
            index=[StudyDesign.INDEPENDENT, StudyDesign.PAIRED, StudyDesign.UNKNOWN].index(default_design),
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
        submitted = st.form_submit_button("Check Eligibility & Assumptions", type="primary", use_container_width=True)

        if submitted:
            # Validate group levels
            if goal in (Goal.COMPARE_TWO_MEANS,) and (not group_levels or len(group_levels) != 2):
                st.error("Please select exactly two groups")
                return

            if goal == Goal.COMPARE_K_MEANS and (not group_levels or len(group_levels) < 3):
                st.error("Please select at least three groups")
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
                variables=variables if goal != Goal.DESCRIBE_DATA else {"dummy": numeric_cols[0] if numeric_cols else (categorical_cols[0] if categorical_cols else "x")},
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

            # Check if configuration changed and invalidate if needed
            _check_and_invalidate_config(
                goal, variables, group_levels, contrast,
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

            # Run assumption diagnostics
            with st.spinner("Running assumption diagnostics..."):
                executor = LazyExecutor(ws, dataset_ref)
                if recipe:
                    recipe_steps = [s.model_dump() for s in recipe]
                    lf = executor.source_lf
                    from CleanSheet.engine.execution import build_preparation_pipeline
                    lf = build_preparation_pipeline(lf, recipe_steps)
                    required_cols = list(set(request.variables.values()))
                    df_prepared = lf.select(required_cols).collect(engine="streaming")
                else:
                    df_prepared = executor.materialize_for_analysis(list(set(request.variables.values())))

                # Build column roles dict
                roles_dict = {}
                for cr in column_roles:
                    roles_dict[cr.column] = cr.semantic_role

                assumption_report = run_assumption_diagnostics(df_prepared, request, roles_dict)

            # Show eligibility result
            st.success("✅ Analysis is eligible!")
            if eligibility.warnings:
                for w in eligibility.warnings:
                    st.warning(w)

            # Show assumption report
            _render_assumption_report(assumption_report)

            # Store request and assumption report for confirmation
            st.session_state.pending_analysis_request = request
            st.session_state.assumption_report = assumption_report

    # Confirmation button OUTSIDE the form
    if "pending_analysis_request" in st.session_state:
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Change Configuration", use_container_width=True):
                if "pending_analysis_request" in st.session_state:
                    del st.session_state.pending_analysis_request
                if "assumption_report" in st.session_state:
                    del st.session_state.assumption_report
                st.rerun()
        with col2:
            if st.button("Run Analysis", type="primary", use_container_width=True):
                st.session_state.analysis_plan = st.session_state.pending_analysis_request
                del st.session_state.pending_analysis_request
                st.session_state.current_stage = JobStatus.RUNNING
                st.rerun()


def _render_assumption_report(report: AssumptionReport) -> None:
    """Render the assumption diagnostics report."""
    st.markdown("### 🔬 Assumption Diagnostics")

    # Overall routing explanation
    if report.auto_routed:
        st.warning(f"⚠️ **Method Auto-Adjusted**: {report.routing_explanation}")
        st.caption(f"Switched from {report.fallback_method.value.replace('_', ' ').title()} to {report.recommended_method.value.replace('_', ' ').title()}")
    else:
        st.success(f"✅ **Assumptions Met**: {report.routing_explanation}")
        st.caption(f"Recommended: {report.recommended_method.value.replace('_', ' ').title()}")

    # Individual checks
    for check in report.checks:
        if check.severity == "error":
            if check.passed is False:
                st.error(f"🛑 **{check.name}**: {check.message}")
            elif check.passed is True:
                st.success(f"✅ **{check.name}**: {check.message}")
            else:
                st.info(f"ℹ️ **{check.name}**: {check.message}")
        elif check.severity == "warning":
            if check.passed is False:
                st.warning(f"⚠️ **{check.name}**: {check.message}")
            else:
                st.success(f"✅ **{check.name}**: {check.message}")
        else:  # info
            st.info(f"ℹ️ **{check.name}**: {check.message}")


def _get_estimand_description(goal: Goal, variables: dict) -> str:
    """Generate human-readable estimand description."""
    descriptions = {
        Goal.COMPARE_TWO_MEANS: f"Difference in mean {variables.get('outcome', 'outcome')} between {variables.get('group', 'groups')}",
        Goal.COMPARE_K_MEANS: f"Differences in mean {variables.get('outcome', 'outcome')} across {variables.get('group', 'groups')}",
        Goal.COMPARE_PAIRED_MEANS: f"Mean paired difference in {variables.get('outcome', 'outcome')}",
        Goal.EXPLORE_LINEAR_RELATIONSHIP: f"Pearson correlation between {variables.get('outcome', 'X')} and {variables.get('predictor', 'Y')}",
        Goal.EXPLORE_ORDERED_RELATIONSHIP: f"Spearman correlation between {variables.get('outcome', 'X')} and {variables.get('predictor', 'Y')}",
        Goal.CATEGORICAL_ASSOCIATION: f"Association between {variables.get('outcome', 'row')} and {variables.get('group', 'column')}",
        Goal.SPARSE_2X2_TABLE: f"Odds ratio for {variables.get('outcome', 'row')} by {variables.get('group', 'column')}",
        Goal.DESCRIBE_DATA: "Descriptive statistics for all variables",
    }
    return descriptions.get(goal, "Analysis")


def _render_target_scan_mode(ws: Workspace, dataset_ref, column_roles, recipe, study_context) -> None:
    """Render the target outcome scan mode."""
    st.markdown("### 🔍 Find Drivers of a Target Variable")
    st.caption("Select a target outcome and CleanSheet will find the strongest predictors.")
    
    role_map = {r.column: r.semantic_role.value for r in column_roles}
    continuous_cols = [c for c, r in role_map.items() if r in ("continuous", "discrete", "ordinal")]
    categorical_cols = [c for c, r in role_map.items() if r in ("nominal", "ordinal", "binary")]
    
    target = st.selectbox(
        "Target variable (outcome)",
        continuous_cols + categorical_cols,
        key="target_scan_target",
        help="The variable you want to predict or explain"
    )
    
    if target and st.button("Scan for Drivers", type="primary", use_container_width=True):
        with st.spinner("Scanning for validated drivers..."):
            candidates = run_autonomous_discovery(
                workspace=ws,
                dataset_ref=dataset_ref,
                column_roles=column_roles,
                recipe_steps=[s.model_dump() for s in recipe],
                target_column=target,
            )
        
        st.session_state.discovery_candidates = candidates
        st.session_state.target_scan_target = target
        st.rerun()
    
    # Show results if available
    if "discovery_candidates" in st.session_state and st.session_state.get("target_scan_target") == target:
        candidates = st.session_state.discovery_candidates
        if candidates:
            st.success(f"✅ Found {len(candidates)} validated driver(s) for **{target}**")
            st.caption("Ranked by effect size, data quality, and FDR-adjusted significance — not raw p-values.")
            
            for i, cand in enumerate(candidates):
                _render_discovery_candidate_card(cand, i, target)
        else:
            st.info("""
            **No reliable drivers detected above noise.**
            
            We checked all eligible variable pairs and applied False Discovery Rate correction.
            After adjusting for multiple comparisons and filtering for practical effect sizes,
            no relationships were strong enough to distinguish from chance.
            
            This is a good sign — it means CleanSheet isn't showing you false positives.
            """)


def _render_discovery_mode(ws: Workspace, dataset_ref, column_roles, recipe, study_context) -> None:
    """Render the autonomous discovery mode."""
    st.markdown("### ✨ Autonomous Discovery")
    st.caption("CleanSheet scans all validated variable pairs and surfaces the strongest patterns.")
    st.info("""
    **How discovery works:**
    - Checks all eligible variable pairs (numeric×numeric, numeric×categorical, categorical×categorical)
    - Runs assumption diagnostics and auto-selects appropriate tests
    - Applies **Benjamini-Hochberg FDR correction** across all tests
    - Ranks by **effect size + data quality + interpretability** (not raw p-values)
    - Prunes redundant findings (e.g., correlated predictors)
    - Only shows findings with **q < 0.05** and **practical effect sizes**
    """)
    
    if st.button("🔍 Run Full Discovery Scan", type="primary", use_container_width=True):
        with st.spinner("Running autonomous discovery scan..."):
            candidates = run_autonomous_discovery(
                workspace=ws,
                dataset_ref=dataset_ref,
                column_roles=column_roles,
                recipe_steps=[s.model_dump() for s in recipe],
            )
        
        st.session_state.discovery_candidates = candidates
        st.rerun()
    
    # Show results if available
    if "discovery_candidates" in st.session_state:
        candidates = st.session_state.discovery_candidates
        if candidates:
            st.success(f"✅ Discovery complete — {len(candidates)} validated pattern(s) found")
            st.caption("All findings are FDR-adjusted (q < 0.05) and have practical effect sizes.")
            
            for i, cand in enumerate(candidates):
                _render_discovery_candidate_card(cand, i)
        else:
            st.info("""
            **No reliable patterns detected above noise.**
            
            CleanSheet checked all eligible variable pairs, adjusted for multiple comparisons
            using Benjamini-Hochberg FDR, and filtered for practical effect sizes.
            
            **This is by design** — CleanSheet would rather show you nothing than false leads.
            """)


def _render_discovery_candidate_card(cand: DiscoveryCandidate, index: int, target: str | None = None) -> None:
    """Render a single discovery candidate card."""
    with st.container(border=True):
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            st.markdown(f"**{cand.question}**")
            if cand.raw_p_value is not None:
                st.caption(f"Raw p = {cand.raw_p_value:.4f} → FDR q = {cand.q_value:.4f}")
            if cand.effect_size is not None:
                st.caption(f"Effect: {cand.effect_size:.3f} ({cand.eligibility.suggested_method.value.replace('_', ' ').title() if cand.eligibility and cand.eligibility.suggested_method else 'N/A'})")
        
        with col2:
            if cand.composite_score is not None:
                st.metric("Score", f"{cand.composite_score:.0f}")
        
        with col3:
            if st.button("Run Full Analysis", key=f"discovery_run_{index}", type="primary", use_container_width=True):
                # Build analysis request from candidate
                from CleanSheet.contracts import AnalysisRequest, Alternative, MissingPolicy, NonFinitePolicy, StudyDesign
                request = AnalysisRequest(
                    goal=cand.goal,
                    variables=cand.variables,
                    group_levels=None,
                    study_design=StudyDesign.INDEPENDENT,
                    design_confirmation_source="inferred",
                    estimand=cand.question,
                    missing_policy=MissingPolicy.REQUIRED_COLUMNS_COMPLETE_CASES,
                    nonfinite_policy=NonFinitePolicy.EXCLUDE_AND_REPORT,
                    method=cand.eligibility.suggested_method if cand.eligibility else None,
                    alternative=Alternative.TWO_SIDED,
                    confidence_level=0.95,
                    seed=42,
                )
                st.session_state.analysis_plan = request
                st.session_state.analysis_mode = "discovery"
                st.session_state.current_stage = JobStatus.RUNNING
                st.rerun()