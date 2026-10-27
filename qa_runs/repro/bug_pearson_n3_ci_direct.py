#!/usr/bin/env python3
"""
Test Pearson n=3 CI directly using the adapter (bypassing assumption checking bug).
"""
import sys
sys.path.insert(0, "/home/lptop/Documents/coding/CleanSheet/src")

import polars as pl
import numpy as np
from scipy import stats

from CleanSheet.services.statistics import PearsonCorrelationAdapter
from CleanSheet.contracts import Goal, StudyDesign, Alternative, Method, AnalysisRequest

# Create n=3 data
np.random.seed(42)
x = np.array([1.0, 2.0, 3.0])
y = np.array([1.1, 2.2, 2.9])
df = pl.DataFrame({"x": x, "y": y})

# Use "outcome" and "predictor" to bypass BUG-006
request = AnalysisRequest(
    goal=Goal.EXPLORE_LINEAR_RELATIONSHIP,
    variables={"outcome": "x", "predictor": "y"},  # Workaround for BUG-006
    study_design=StudyDesign.INDEPENDENT,
    estimand="Test Pearson n=3",
    alternative=Alternative.TWO_SIDED,
    confidence_level=0.95,
    seed=42,
)

adapter = PearsonCorrelationAdapter()
result = adapter.run(df, request)

print(f"Pearson r: {result.estimate:.6f}")
print(f"CI: {result.interval}")
print(f"interval_status: {result.interval_status}")
print(f"interval_method: {result.interval_method}")
print(f"df: {result.degrees_of_freedom}")

# Check if CI is [-1, 1] with status "computed" (the bug)
if result.interval == [-1.0, 1.0] and result.interval_status == "computed":
    print("\nBUG CONFIRMED: CI is [-1, 1] with status 'computed' (meaningless)")
elif result.interval_status == "not_computed":
    print("\nFIXED: CI status is 'not_computed'")
else:
    print(f"\nUNEXPECTED: CI={result.interval}, status={result.interval_status}")

# Also test with n=4 (should work)
print("\n--- Testing n=4 ---")
x4 = np.array([1.0, 2.0, 3.0, 4.0])
y4 = np.array([1.1, 2.2, 2.9, 4.1])
df4 = pl.DataFrame({"x": x4, "y": y4})

request4 = AnalysisRequest(
    goal=Goal.EXPLORE_LINEAR_RELATIONSHIP,
    variables={"outcome": "x", "predictor": "y"},
    study_design=StudyDesign.INDEPENDENT,
    estimand="Test Pearson n=4",
    alternative=Alternative.TWO_SIDED,
    confidence_level=0.95,
    seed=42,
)

result4 = adapter.run(df4, request4)
print(f"Pearson r: {result4.estimate:.6f}")
print(f"CI: {result4.interval}")
print(f"interval_status: {result4.interval_status}")
print(f"interval_method: {result4.interval_method}")

# Reference from scipy
r_scipy, p_scipy = stats.pearsonr(x4, y4)
print(f"Scipy r: {r_scipy:.6f}, p: {p_scipy:.6f}")