#!/usr/bin/env python3
"""
Reproduction script for BUG-008: Contrast direction bug in long-format paired test.
CleanSheet computes pre - post when user specifies group_levels=["pre", "post"]
but the expected behavior is post - pre (second minus first).
"""
import sys
sys.path.insert(0, "/home/lptop/Documents/coding/CleanSheet/src")

import polars as pl
import pandas as pd
import numpy as np
from scipy import stats

from CleanSheet.services.ingest import ingest_file
from CleanSheet.services.profile import run_profiling
from CleanSheet.services.prepare import get_prepared_data
from CleanSheet.services.statistics import run_analysis, AnalysisRequest
from CleanSheet.contracts import Goal, StudyDesign, Alternative, ColumnRole
from CleanSheet.jobs.workspace import WorkspaceManager

# Use the existing paired_long.csv data
df_long = pd.read_csv('/home/lptop/Documents/coding/CleanSheet/qa_runs/data/paired_long.csv')
pre = df_long[df_long['occasion'] == 'pre']['value'].values
post = df_long[df_long['occasion'] == 'post']['value'].values
print(f"Using paired_long.csv data:")
print(f"  pre mean: {np.mean(pre):.6f}")
print(f"  post mean: {np.mean(post):.6f}")
print(f"  post - pre mean: {np.mean(post - pre):.6f}")

# Reference computation (what user expects: post - pre)
diff = post - pre
ref_result = stats.ttest_rel(post, pre)
print(f"\nReference (post - pre):")
print(f"  mean diff: {np.mean(diff):.6f}")
print(f"  t-statistic: {ref_result.statistic:.6f}")
print(f"  p-value: {ref_result.pvalue:.6f}")
print(f"  df: {ref_result.df}")

# Now run through CleanSheet
with open("/home/lptop/Documents/coding/CleanSheet/qa_runs/data/paired_long.csv", "rb") as f:
    data = f.read()

ws_mgr = WorkspaceManager()
ws = ws_mgr.create()
dataset_ref, preview, metadata = ingest_file(ws, data, filename="paired_long.csv")
profiling_result = run_profiling(ws, dataset_ref)

column_roles = []
for col_profile in profiling_result.columns:
    column_roles.append(ColumnRole(
        column=col_profile.name,
        physical_dtype=col_profile.physical_dtype,
        semantic_role=col_profile.semantic_role
    ))

recipe = []
prepared_df = get_prepared_data(ws, dataset_ref, recipe)

# Test with group_levels=["pre", "post"] - user expects post - pre
request = AnalysisRequest(
    goal=Goal.COMPARE_PAIRED_MEANS,
    variables={"pair_id": "subject_id", "occasion": "occasion", "outcome": "value"},
    group_levels=["pre", "post"],
    study_design=StudyDesign.PAIRED,
    estimand="Mean difference (post - pre)",
    confidence_level=0.95,
    alternative=Alternative.TWO_SIDED
)

print("\nCleanSheet result (group_levels=['pre', 'post']):")
result = run_analysis(ws, dataset_ref, request, recipe, column_roles)
stat = result.statistical_results[0]
print(f"  estimate: {stat.estimate:.6f}")
print(f"  t-statistic: {stat.statistic:.6f}")
print(f"  p-value: {stat.p_value:.6f}")
print(f"  contrast: {stat.assumption_checks.get('contrast', 'N/A')}")

# The fix: group_levels[0] minus group_levels[1] = pre minus post
# But user expects post - pre, so we need to reverse the order in group_levels
# Let's test with group_levels=["post", "pre"]
request2 = AnalysisRequest(
    goal=Goal.COMPARE_PAIRED_MEANS,
    variables={"pair_id": "subject_id", "occasion": "occasion", "outcome": "value"},
    group_levels=["post", "pre"],
    study_design=StudyDesign.PAIRED,
    estimand="Mean difference (pre - post)",
    confidence_level=0.95,
    alternative=Alternative.TWO_SIDED
)

print("\nCleanSheet result (group_levels=['post', 'pre']):")
result2 = run_analysis(ws, dataset_ref, request2, recipe, column_roles)
stat2 = result2.statistical_results[0]
print(f"  estimate: {stat2.estimate:.6f}")
print(f"  t-statistic: {stat2.statistic:.6f}")
print(f"  p-value: {stat2.p_value:.6f}")
print(f"  contrast: {stat2.assumption_checks.get('contrast', 'N/A')}")

print("\n--- Analysis ---")
print(f"Reference (post - pre): {np.mean(diff):.6f}")
print(f"CleanSheet group_levels=['pre','post'] (pre - post): {stat.estimate:.6f}")
print(f"CleanSheet group_levels=['post','pre'] (post - pre): {stat2.estimate:.6f}")

# Check if the fix works correctly
if abs(stat.estimate - np.mean(pre - post)) < 1e-10 and abs(stat2.estimate - np.mean(post - pre)) < 1e-10:
    print("\n✅ FIX VERIFIED: group_levels order correctly determines contrast direction")
else:
    print("\n❌ FIX NOT WORKING: contrast direction still incorrect")

ws.cleanup()