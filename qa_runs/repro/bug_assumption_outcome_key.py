#!/usr/bin/env python3
"""
Reproduction script for BUG-006: Assumption checking hardcodes "outcome" variable.
This bug affects all non-Welch analyses (correlation, chi-square, paired, Kruskal-Wallis).
"""
import sys
sys.path.insert(0, "/home/lptop/Documents/coding/CleanSheet/src")

import polars as pl
from CleanSheet.services.ingest import ingest_file
from CleanSheet.services.profile import run_profiling
from CleanSheet.services.prepare import get_prepared_data
from CleanSheet.services.statistics import run_analysis, AnalysisRequest
from CleanSheet.contracts import Goal, StudyDesign, Method, Alternative
from CleanSheet.jobs.workspace import WorkspaceManager

# Create test data for correlation
import pandas as pd
import numpy as np
np.random.seed(42)
x = np.random.normal(0, 1, 100)
y = 0.7 * x + np.random.normal(0, np.sqrt(1 - 0.7**2), 100)
df = pd.DataFrame({"x": x, "y": y})
df.to_csv("/tmp/corr_test.csv", index=False)

# Read as bytes
with open("/tmp/corr_test.csv", "rb") as f:
    data = f.read()

# Setup
ws_mgr = WorkspaceManager()
ws = ws_mgr.create()
dataset_ref, preview, metadata = ingest_file(ws, data, filename="corr_test.csv")
profiling_result = run_profiling(ws, dataset_ref)

# Get column roles
from CleanSheet.contracts import ColumnRole, SemanticRole
column_roles = []
for col_profile in profiling_result.columns:
    column_roles.append(ColumnRole(
        column=col_profile.name,
        physical_dtype=col_profile.physical_dtype,
        semantic_role=col_profile.semantic_role
    ))

recipe = []
prepared_df = get_prepared_data(ws, dataset_ref, recipe)

# Try to run Pearson correlation - this should trigger the bug
request = AnalysisRequest(
    goal=Goal.EXPLORE_LINEAR_RELATIONSHIP,
    variables={"x": "x", "y": "y"},
    study_design=StudyDesign.INDEPENDENT,
    estimand="Pearson correlation between x and y",
    confidence_level=0.95,
    alternative=Alternative.TWO_SIDED
)

print("Running Pearson correlation...")
try:
    result = run_analysis(ws, dataset_ref, request, recipe, column_roles)
    print("SUCCESS:", result.status)
except KeyError as e:
    print(f"BUG CONFIRMED: KeyError {e}")
    print("The assumption checking code hardcodes variables['outcome']")
    print("but correlation uses variables['x'] and variables['y']")
except Exception as e:
    print(f"OTHER ERROR: {type(e).__name__}: {e}")

# Cleanup
ws.cleanup()