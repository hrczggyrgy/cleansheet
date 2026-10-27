#!/usr/bin/env python3
"""
Reproduction script for BUG-004: Pearson correlation CI division by zero at n=3.
When n=3, Fisher-z transformation uses se = 1/sqrt(n-3) = 1/sqrt(0) -> division by zero.
"""
import sys
sys.path.insert(0, "/home/lptop/Documents/coding/CleanSheet/src")

import numpy as np
from scipy import stats

# Create n=3 data
np.random.seed(42)
x = np.array([1.0, 2.0, 3.0])
y = np.array([1.1, 2.2, 2.9])  # Strong correlation

# Reference computation using scipy
r, p = stats.pearsonr(x, y)
print(f"Pearson r: {r:.6f}, p: {p:.6f}")

# Fisher-z CI computation (what CleanSheet does)
n = len(x)
z = np.arctanh(r)
se = 1 / np.sqrt(n - 3)  # Division by zero when n=3!
print(f"z: {z:.6f}")
print(f"se: {se}")  # This will be inf

z_crit = stats.norm.ppf(0.975)
z_low = z - z_crit * se
z_high = z + z_crit * se
ci_low = np.tanh(z_low)
ci_high = np.tanh(z_high)
print(f"CI: [{ci_low:.6f}, {ci_high:.6f}]")
print(f"  ci_low = tanh(-inf) = -1.0")
print(f"  ci_high = tanh(+inf) = +1.0")
print(f"  interval_status would be 'computed' but CI is meaningless [-1, 1]")

# Now test through CleanSheet
import pandas as pd
import polars as pl
from CleanSheet.services.ingest import ingest_file
from CleanSheet.services.profile import run_profiling
from CleanSheet.services.prepare import get_prepared_data
from CleanSheet.services.statistics import run_analysis, AnalysisRequest
from CleanSheet.contracts import Goal, StudyDesign, Alternative, ColumnRole
from CleanSheet.jobs.workspace import WorkspaceManager

# Create n=3 dataset
df = pd.DataFrame({"x": x, "y": y})
df.to_csv("/tmp/pearson_n3_test.csv", index=False)

with open("/tmp/pearson_n3_test.csv", "rb") as f:
    data = f.read()

ws_mgr = WorkspaceManager()
ws = ws_mgr.create()
dataset_ref, preview, metadata = ingest_file(ws, data, filename="pearson_n3_test.csv")
profiling_result = run_profiling(ws, dataset_ref)

column_roles = []
for col_profile in profiling_result.columns:
    column_roles.append(ColumnRole(
        column=col_profile.name,
        physical_dtype=col_profile.physical_dtype,
        semantic_role=col_profile.semantic_role
    ))

recipe = []

request = AnalysisRequest(
    goal=Goal.EXPLORE_LINEAR_RELATIONSHIP,
    variables={"x": "x", "y": "y"},
    study_design=StudyDesign.INDEPENDENT,
    estimand="Pearson correlation between x and y (n=3)",
    confidence_level=0.95,
    alternative=Alternative.TWO_SIDED
)

print("\nCleanSheet result for n=3:")
try:
    result = run_analysis(ws, dataset_ref, request, recipe, column_roles)
    stat = result.statistical_results[0]
    print(f"  r: {stat.estimate:.6f}")
    print(f"  CI: {stat.interval}")
    print(f"  interval_status: {stat.interval_status}")
    print(f"  interval_method: {stat.interval_method}")
    
    # Check if CI is [-1, 1] with status "computed" (the bug)
    if stat.interval == [-1.0, 1.0] and stat.interval_status == "computed":
        print("BUG CONFIRMED: CI is [-1, 1] with status 'computed' (meaningless)")
    elif stat.interval_status == "not_computed":
        print("FIXED: CI status is 'not_computed'")
    else:
        print(f"UNEXPECTED: CI={stat.interval}, status={stat.interval_status}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

ws.cleanup()