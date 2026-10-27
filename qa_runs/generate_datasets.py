#!/usr/bin/env python3
"""
Generate all QA test datasets for CleanSheet.
Saves to ./qa_runs/data/ as both CSV and Parquet.
"""
import numpy as np
import pandas as pd
import os

np.random.seed(42)

DATA_DIR = "/home/lptop/Documents/coding/CleanSheet/qa_runs/data"
os.makedirs(DATA_DIR, exist_ok=True)

def save_both(df, name):
    """Save as both CSV and Parquet."""
    csv_path = os.path.join(DATA_DIR, f"{name}.csv")
    parquet_path = os.path.join(DATA_DIR, f"{name}.parquet")
    df.to_csv(csv_path, index=False)
    df.to_parquet(parquet_path, index=False)
    print(f"Saved {name}: {df.shape} -> {csv_path}, {parquet_path}")

# ============================================================
# 1. Built-in examples from seaborn (if available)
# ============================================================
try:
    import seaborn as sns
    for name in ["penguins", "iris", "tips", "titanic"]:
        try:
            df = sns.load_dataset(name)
            save_both(df, name)
        except Exception as e:
            print(f"Could not load {name}: {e}")
except ImportError:
    print("seaborn not available for built-in datasets")

# ============================================================
# 2. Synthetic files with KNOWN ground truth
# ============================================================

# a) two_groups.csv: group A ~ N(10,2), n=40; group B ~ N(12,3), n=35
n_a, n_b = 40, 35
group_a = np.random.normal(10, 2, n_a)
group_b = np.random.normal(12, 3, n_b)
df_two_groups = pd.DataFrame({
    "value": np.concatenate([group_a, group_b]),
    "group": ["A"] * n_a + ["B"] * n_b
})
save_both(df_two_groups, "two_groups")

# b) paired_wide.csv: subject_id, pre, post (n=30, post = pre + 1.5 + noise)
n_subjects = 30
pre = np.random.normal(50, 10, n_subjects)
post = pre + 1.5 + np.random.normal(0, 2, n_subjects)
df_paired_wide = pd.DataFrame({
    "subject_id": range(1, n_subjects + 1),
    "pre": pre,
    "post": post
})
save_both(df_paired_wide, "paired_wide")

# c) paired_long.csv: subject_id, occasion (pre/post), value (same data, long format)
df_paired_long = pd.DataFrame({
    "subject_id": np.repeat(range(1, n_subjects + 1), 2),
    "occasion": np.tile(["pre", "post"], n_subjects),
    "value": np.concatenate([pre, post])
})
save_both(df_paired_long, "paired_long")

# d) three_groups.csv: 3 groups with different means and unequal variances, n=25 each
n_per_group = 25
group1 = np.random.normal(10, 2, n_per_group)
group2 = np.random.normal(14, 3, n_per_group)
group3 = np.random.normal(18, 4, n_per_group)
df_three_groups = pd.DataFrame({
    "value": np.concatenate([group1, group2, group3]),
    "group": ["G1"] * n_per_group + ["G2"] * n_per_group + ["G3"] * n_per_group
})
save_both(df_three_groups, "three_groups")

# e) corr.csv: x, y with true Pearson r about 0.7 (n=100) plus a monotone non-linear pair (n=25)
n_corr = 100
x = np.random.normal(0, 1, n_corr)
y = 0.7 * x + np.random.normal(0, np.sqrt(1 - 0.7**2), n_corr)  # r ≈ 0.7
# Add monotone non-linear pair (n=25)
x_nl = np.linspace(0, 10, 25)
y_nl = np.log1p(x_nl) + np.random.normal(0, 0.2, 25)
df_corr = pd.DataFrame({
    "x_linear": np.concatenate([x, x_nl]),
    "y_linear": np.concatenate([y, y_nl]),
    "type": ["linear"] * n_corr + ["nonlinear"] * 25
})
save_both(df_corr, "corr")

# f) table_2x2.csv: sparse 2x2 table and 3x4 table
# Sparse 2x2: some expected counts < 5
df_2x2 = pd.DataFrame({
    "outcome": [0, 0, 1, 1, 0, 1, 1, 0, 1, 0],  # 10 rows, sparse
    "group": [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]
})
save_both(df_2x2, "table_2x2")

# 3x4 table for chi-square
df_3x4 = pd.DataFrame({
    "row": np.repeat(["R1", "R2", "R3"], 4),
    "col": np.tile(["C1", "C2", "C3", "C4"], 3),
    "count": [10, 5, 2, 1, 3, 8, 12, 4, 6, 2, 9, 7]  # some small expected counts
})
save_both(df_3x4, "table_3x4")

# ============================================================
# 3. Edge-case files
# ============================================================

# g) semicolon-delimited with decimal commas (e.g. 1,5)
df_semicolon = pd.DataFrame({
    "A": ["1,5", "2,3", "3,7", "4,1"],
    "B": ["10,2", "20,8", "30,5", "40,9"],
    "C": ["x", "y", "z", "w"]
})
csv_path = os.path.join(DATA_DIR, "semicolon_decimal_comma.csv")
df_semicolon.to_csv(csv_path, index=False, sep=";", decimal=",")
# Also save as parquet (standard format)
df_semicolon_parquet = pd.DataFrame({
    "A": [1.5, 2.3, 3.7, 4.1],
    "B": [10.2, 20.8, 30.5, 40.9],
    "C": ["x", "y", "z", "w"]
})
df_semicolon_parquet.to_parquet(os.path.join(DATA_DIR, "semicolon_decimal_comma.parquet"))
print(f"Saved semicolon_decimal_comma: {df_semicolon.shape}")

# h) latin-1 or cp1250 encoded file with accented text
df_latin = pd.DataFrame({
    "city": ["Székesfehérvár", "São Paulo", "München", "Zürich", "Île-de-France"],
    "value": [1, 2, 3, 4, 5]
})
csv_path = os.path.join(DATA_DIR, "latin1_accented.csv")
df_latin.to_csv(csv_path, index=False, encoding="latin-1")
df_latin.to_parquet(os.path.join(DATA_DIR, "latin1_accented.parquet"))
print(f"Saved latin1_accented: {df_latin.shape}")

# i) header-only CSV, single-row CSV, constant column, all-null column
df_header_only = pd.DataFrame(columns=["A", "B", "C"])
df_header_only.to_csv(os.path.join(DATA_DIR, "header_only.csv"), index=False)
df_header_only.to_parquet(os.path.join(DATA_DIR, "header_only.parquet"))
print(f"Saved header_only: {df_header_only.shape}")

df_single_row = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
df_single_row.to_csv(os.path.join(DATA_DIR, "single_row.csv"), index=False)
df_single_row.to_parquet(os.path.join(DATA_DIR, "single_row.parquet"))
print(f"Saved single_row: {df_single_row.shape}")

df_constant = pd.DataFrame({
    "constant": [5] * 10,
    "varying": range(10)
})
df_constant.to_csv(os.path.join(DATA_DIR, "constant_column.csv"), index=False)
df_constant.to_parquet(os.path.join(DATA_DIR, "constant_column.parquet"))
print(f"Saved constant_column: {df_constant.shape}")

df_all_null = pd.DataFrame({
    "all_null": [None] * 10,
    "some_data": range(10)
})
df_all_null.to_csv(os.path.join(DATA_DIR, "all_null_column.csv"), index=False)
df_all_null.to_parquet(os.path.join(DATA_DIR, "all_null_column.parquet"))
print(f"Saved all_null_column: {df_all_null.shape}")

# j) a column containing NA, N/A, -999, "." and literal text values (e.g. country code "NA")
df_null_tokens = pd.DataFrame({
    "mixed": ["NA", "N/A", "-999", ".", "NA", "US", "CA", "UK", "DE", "FR"],
    "numeric": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
})
df_null_tokens.to_csv(os.path.join(DATA_DIR, "null_tokens.csv"), index=False)
df_null_tokens.to_parquet(os.path.join(DATA_DIR, "null_tokens.parquet"))
print(f"Saved null_tokens: {df_null_tokens.shape}")

# k) NaN/inf strings in a numeric column, duplicate rows, leading/trailing whitespace in categories
df_edge = pd.DataFrame({
    "numeric": [1.0, 2.0, np.nan, np.inf, -np.inf, 5.0, 5.0, 6.0],  # NaN, inf, duplicate
    "category": [" A ", "B ", " C", "D", "E", " A ", "F", "G"]  # whitespace, duplicate
})
df_edge.to_csv(os.path.join(DATA_DIR, "edge_cases.csv"), index=False)
df_edge.to_parquet(os.path.join(DATA_DIR, "edge_cases.parquet"))
print(f"Saved edge_cases: {df_edge.shape}")

# l) mixed types appearing after row 1000 in a numeric column
np.random.seed(42)
df_mixed = pd.DataFrame({
    "col": list(np.random.normal(0, 1, 1000)) + ["text"] * 10 + [1.5, 2.5]  # 1012 rows
})
df_mixed.to_csv(os.path.join(DATA_DIR, "mixed_types_late.csv"), index=False)
# Can't save as parquet with mixed types - save CSV only
print(f"Saved mixed_types_late: {df_mixed.shape} (CSV only)")

# m) a file with 50 MB+ rows (actually let's do ~1M rows for speed) and a file slightly over the upload limit
# 50 MB limit - let's create a file ~55 MB (over limit)
# Estimate: ~10 bytes per row * 5.5M rows = 55 MB
# For speed, let's do ~100k rows (smaller) and note the 50MB limit
df_large = pd.DataFrame({
    "x": np.random.normal(0, 1, 100000),
    "y": np.random.normal(0, 1, 100000),
    "group": np.random.choice(["A", "B", "C"], 100000)
})
df_large.to_csv(os.path.join(DATA_DIR, "large_100k.csv"), index=False)
df_large.to_parquet(os.path.join(DATA_DIR, "large_100k.parquet"))
print(f"Saved large_100k: {df_large.shape}")

# n) a file whose cell contains `<img src=x onerror=alert(1)>` in a numeric column
df_xss = pd.DataFrame({
    "value": ["1.0", "2.0", "<img src=x onerror=alert(1)>", "4.0", "5.0"],
    "other": ["a", "b", "c", "d", "e"]
})
df_xss.to_csv(os.path.join(DATA_DIR, "xss_injection.csv"), index=False)
df_xss.to_parquet(os.path.join(DATA_DIR, "xss_injection.parquet"))
print(f"Saved xss_injection: {df_xss.shape}")

print("\nAll datasets generated!")