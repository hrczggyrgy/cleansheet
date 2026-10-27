#!/usr/bin/env python3
"""
Compare CleanSheet results with reference computations.
"""
import json
import os

RESULTS_DIR = "/home/lptop/Documents/coding/CleanSheet/qa_runs/cleansheet_results"
REF_DIR = "/home/lptop/Documents/coding/CleanSheet/qa_runs/reference"

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def compare_values(ref, app, name, tol_rel=1e-8, tol_abs=1e-6):
    """Compare two numeric values with relative and absolute tolerance."""
    if ref is None and app is None:
        return True, "Both None"
    if ref is None or app is None:
        return False, f"One is None: ref={ref}, app={app}"
    
    abs_diff = abs(ref - app)
    rel_diff = abs_diff / max(abs(ref), 1e-10)
    
    passed = abs_diff <= tol_abs or rel_diff <= tol_rel
    status = "PASS" if passed else "FAIL"
    return passed, f"{status}: ref={ref:.10f}, app={app:.10f}, abs_diff={abs_diff:.2e}, rel_diff={rel_diff:.2e}"

def compare_dict(ref_dict, app_dict, prefix=""):
    """Recursively compare dictionaries."""
    results = []
    
    all_keys = set(ref_dict.keys()) | set(app_dict.keys())
    for key in sorted(all_keys):
        full_key = f"{prefix}.{key}" if prefix else key
        
        if key not in ref_dict:
            results.append((full_key, False, f"Missing in reference: {app_dict[key]}"))
        elif key not in app_dict:
            results.append((full_key, False, f"Missing in app: {ref_dict[key]}"))
        else:
            ref_val = ref_dict[key]
            app_val = app_dict[key]
            
            if isinstance(ref_val, dict) and isinstance(app_val, dict):
                results.extend(compare_dict(ref_val, app_val, full_key))
            elif isinstance(ref_val, (int, float)) and isinstance(app_val, (int, float)):
                passed, msg = compare_values(ref_val, app_val, full_key)
                results.append((full_key, passed, msg))
            elif isinstance(ref_val, list) and isinstance(app_val, list):
                # Compare lists element-wise if numeric
                if all(isinstance(x, (int, float)) for x in ref_val + app_val):
                    for i, (rv, av) in enumerate(zip(ref_val, app_val)):
                        passed, msg = compare_values(rv, av, f"{full_key}[{i}]")
                        results.append((f"{full_key}[{i}]", passed, msg))
                else:
                    results.append((full_key, ref_val == app_val, f"List equal: {ref_val == app_val}"))
            else:
                results.append((full_key, ref_val == app_val, f"Equal: {ref_val == app_val} (ref={ref_val}, app={app_val})"))
    
    return results

def main():
    # Load results
    cleansheet_results = load_json(os.path.join(RESULTS_DIR, "cleansheet_results.json"))
    reference_results = load_json(os.path.join(REF_DIR, "reference_results.json"))
    
    # Extract statistical results from CleanSheet
    app_stats = {}
    for dataset_key, result in cleansheet_results.items():
        if isinstance(result, dict) and "error" not in result:
            for test_key, test_result in result.items():
                if isinstance(test_result, dict) and "statistical_results" in test_result:
                    for stat in test_result["statistical_results"]:
                        key = f"{dataset_key}.{test_key}"
                        app_stats[key] = stat
    
    print("=" * 80)
    print("COMPARISON: CleanSheet vs Reference")
    print("=" * 80)
    
    all_passed = True
    
    # Compare two_groups Welch
    print("\n--- two_groups Welch t-test ---")
    ref = reference_results.get("two_groups_welch", {})
    app = app_stats.get("two_groups_csv.welch_t", {})
    
    comparisons = [
        ("statistic", ref.get("statistic"), app.get("statistic")),
        ("pvalue", ref.get("pvalue"), app.get("p_value")),
        ("df", ref.get("df"), app.get("degrees_of_freedom")),
        ("mean_diff", ref.get("mean_diff"), app.get("estimate")),
        ("ci_low", ref.get("ci_low"), app.get("interval", [None, None])[0]),
        ("ci_high", ref.get("ci_high"), app.get("interval", [None, None])[1]),
        ("hedges_g", ref.get("hedges_g"), app.get("effect_size")),
    ]
    
    for name, ref_val, app_val in comparisons:
        passed, msg = compare_values(ref_val, app_val, name)
        print(f"  {name}: {msg}")
        if not passed:
            all_passed = False
    
    # Compare Hedges' g CI (different methods - bootstrap vs parametric)
    ref_g_ci = [ref.get("hedges_g_ci_low"), ref.get("hedges_g_ci_high")]
    app_g_ci = app.get("effect_size_ci", [None, None])
    print(f"  hedges_g_ci: ref={ref_g_ci}, app={app_g_ci} (different methods expected)")
    
    # Compare two_groups Mann-Whitney
    print("\n--- two_groups Mann-Whitney U ---")
    ref = reference_results.get("two_groups_mannwhitney", {})
    app = app_stats.get("two_groups_csv.mann_whitney", {})
    
    comparisons = [
        ("statistic", ref.get("statistic"), app.get("statistic")),
        ("pvalue", ref.get("pvalue"), app.get("p_value")),
        ("rank_biserial_r", ref.get("rank_biserial_r"), app.get("effect_size")),
    ]
    
    for name, ref_val, app_val in comparisons:
        passed, msg = compare_values(ref_val, app_val, name)
        print(f"  {name}: {msg}")
        if not passed:
            all_passed = False
    
    # Compare paired_wide t-test
    print("\n--- paired_wide paired t-test ---")
    ref = reference_results.get("paired_wide_ttest", {})
    app = app_stats.get("paired_wide_csv.paired_ttest_wide", {})
    
    comparisons = [
        ("statistic", ref.get("statistic"), app.get("statistic")),
        ("pvalue", ref.get("pvalue"), app.get("p_value")),
        ("df", ref.get("df"), app.get("degrees_of_freedom")),
        ("mean_diff", ref.get("mean_diff"), app.get("estimate")),
        ("ci_low", ref.get("ci_low"), app.get("interval", [None, None])[0]),
        ("ci_high", ref.get("ci_high"), app.get("interval", [None, None])[1]),
        ("hedges_g", ref.get("hedges_g"), app.get("effect_size")),
    ]
    
    for name, ref_val, app_val in comparisons:
        passed, msg = compare_values(ref_val, app_val, name)
        print(f"  {name}: {msg}")
        if not passed:
            all_passed = False
    
    # Compare paired_long t-test
    print("\n--- paired_long paired t-test ---")
    ref = reference_results.get("paired_long_ttest", {})
    app = app_stats.get("paired_long_csv.paired_ttest_long", {})
    
    comparisons = [
        ("statistic", ref.get("statistic"), app.get("statistic")),
        ("pvalue", ref.get("pvalue"), app.get("p_value")),
        ("df", ref.get("df"), app.get("degrees_of_freedom")),
        ("mean_diff", ref.get("mean_diff"), app.get("estimate")),
        ("ci_low", ref.get("ci_low"), app.get("interval", [None, None])[0]),
        ("ci_high", ref.get("ci_high"), app.get("interval", [None, None])[1]),
    ]
    
    for name, ref_val, app_val in comparisons:
        passed, msg = compare_values(ref_val, app_val, name)
        print(f"  {name}: {msg}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 80)
    if all_passed:
        print("ALL COMPARISONS PASSED!")
    else:
        print("SOME COMPARISONS FAILED!")
    print("=" * 80)

if __name__ == "__main__":
    main()