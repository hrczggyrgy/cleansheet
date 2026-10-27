#!/usr/bin/env python3
"""
Reproduction script for BUG-007: Missing import of Goal in nonparametric.py
"""
import sys
sys.path.insert(0, "/home/lptop/Documents/coding/CleanSheet/src")

import pandas as pd
import numpy as np
from scipy import stats

# Test the Kruskal-Wallis post-hoc code directly
# This simulates what happens in run_posthoc_if_needed

# First, let's check if the import is missing
try:
    from CleanSheet.engine.nonparametric import run_posthoc_if_needed
    from CleanSheet.contracts import Goal
    print("Goal imported successfully")
except ImportError as e:
    print(f"Import error: {e}")

# The bug is in engine/nonparametric.py line 746:
# if goal == Goal.COMPARE_K_MEANS:
# But Goal is not imported in that module

# Let's verify by checking the source
with open("/home/lptop/Documents/coding/CleanSheet/src/CleanSheet/engine/nonparametric.py", "r") as f:
    source = f.read()
if "Goal.COMPARE_K_MEANS" in source:
    # Check if Goal is in the imports - look for "Goal" in the import block
    import_block_start = source.find("from CleanSheet.contracts import")
    import_block_end = source.find(")", import_block_start)
    import_block = source[import_block_start:import_block_end]
    print(f"Import block: {import_block}")
    if 'Goal' not in import_block:
        print("BUG CONFIRMED: Goal is used but not imported in nonparametric.py")
    else:
        print("✅ FIX VERIFIED: Goal is now imported in nonparametric.py")
else:
    print("Could not verify")

# Now let's test the actual function call that would fail
# Create minimal test data
np.random.seed(42)
groups = [
    np.random.normal(10, 2, 25),
    np.random.normal(14, 3, 25),
    np.random.normal(18, 4, 25)
]

# Run Kruskal-Wallis
h_stat, p_val = stats.kruskal(*groups)
print(f"Kruskal-Wallis: H={h_stat:.4f}, p={p_val:.4f}")

# The post-hoc would be called if p < 0.05
# This would fail with NameError: name 'Goal' is not defined
print("If p < 0.05, run_posthoc_if_needed would be called and fail with NameError")