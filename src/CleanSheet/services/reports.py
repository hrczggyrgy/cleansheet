"""Report generation and export service."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import polars as pl

from CleanSheet.config import get_settings
from CleanSheet.contracts import (
    AnalysisRequest,
    AnalysisResult,
    AssumptionReport,
    DatasetRef,
    RunManifest,
)
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.profile import generate_data_dictionary


def escape_csv_value(value: str) -> str:
    """Escape CSV values to prevent formula injection."""
    if not isinstance(value, str):
        value = str(value)

    # Check for formula prefixes
    if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        value = "'" + value

    # Escape quotes
    if '"' in value or "," in value or "\n" in value:
        value = '"' + value.replace('"', '""') + '"'

    return value


def generate_markdown_report(
    result: AnalysisResult,
    dataset_ref: DatasetRef,
    profile: Any,
    manifest: RunManifest,
    assumption_report: AssumptionReport | None = None,
) -> str:
    """Generate a Markdown report."""
    lines = []

    # Header
    lines.append("# CleanSheet Analysis Report")
    lines.append("")
    lines.append(f"**Run ID:** {result.run_id}")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}Z")
    lines.append(f"**Dataset:** {dataset_ref.dataset_id} ({dataset_ref.row_count:,} rows × {dataset_ref.column_count} cols)")
    lines.append(f"**Source Hash:** `{dataset_ref.source_sha256[:16]}`")
    lines.append("")

    # Question
    lines.append("## Question")
    lines.append("")
    lines.append(f"**Goal:** {result.request.goal.value.replace('_', ' ').title()}")
    lines.append(f"**Estimand:** {result.request.estimand}")
    lines.append(f"**Study Design:** {result.request.study_design.value}")
    lines.append("")

    # Variables
    lines.append("## Variables")
    lines.append("")
    for role, col in result.request.variables.items():
        lines.append(f"- **{role.title()}:** `{col}`")
    if result.request.group_levels:
        lines.append(f"- **Group Levels:** {', '.join(result.request.group_levels)}")
    lines.append("")

    # Data Preparation
    lines.append("## Data Preparation")
    lines.append("")
    lines.append(f"- **Import Format:** {dataset_ref.format.upper()}")
    lines.append(f"- **Missing Policy:** {result.request.missing_policy.value}")
    lines.append(f"- **Non-finite Policy:** {result.request.nonfinite_policy.value}")
    if result.request.confidence_level != 0.95:
        lines.append(f"- **Confidence Level:** {result.request.confidence_level:.0%}")
    lines.append("")

    # Assumption Diagnostics
    if assumption_report:
        lines.append("## Assumption Diagnostics")
        lines.append("")
        lines.append(f"**Routing Explanation:** {assumption_report.routing_explanation}")
        lines.append(f"**Auto-Routed:** {'Yes' if assumption_report.auto_routed else 'No'}")
        lines.append(f"**Recommended Method:** {assumption_report.recommended_method.value.replace('_', ' ').title()}")
        if assumption_report.fallback_method:
            lines.append(f"**Fallback Method:** {assumption_report.fallback_method.value.replace('_', ' ').title()}")
        lines.append("")

        for check in assumption_report.checks:
            status = "✅ PASS" if check.passed else ("❌ FAIL" if check.passed is False else "ℹ️ INFO")
            lines.append(f"- **{check.name}** ({check.severity.upper()}): {status}")
            lines.append(f"  - Message: {check.message}")
            if check.value is not None:
                lines.append(f"  - Value: {check.value}")
            if check.threshold is not None:
                lines.append(f"  - Threshold: {check.threshold}")
        lines.append("")

    # Results
    lines.append("## Results")
    lines.append("")
    for i, stat_result in enumerate(result.statistical_results):
        lines.append(f"### Analysis {i+1}: {stat_result.method.value.replace('_', ' ').title()}")
        lines.append("")

        # Group counts
        if stat_result.group_counts:
            lines.append("**Sample Sizes:**")
            for k, v in stat_result.group_counts.items():
                lines.append(f"- {k}: n = {v:,}")
            lines.append("")

        # Estimate
        if stat_result.estimate is not None:
            lines.append(f"**Estimate:** {stat_result.estimate:.4f}")
            if stat_result.effect_size is not None:
                lines.append(f"**Effect Size:** {stat_result.effect_size:.4f} ({stat_result.effect_size_interpretation})")
            lines.append("")

        # Confidence Interval
        if stat_result.interval and stat_result.interval_status == "computed":
            lines.append(f"**{result.request.confidence_level:.0%} CI:** [{stat_result.interval[0]:.4f}, {stat_result.interval[1]:.4f}]")
            lines.append(f"**Interval Method:** {stat_result.interval_method.value}")
            lines.append("")
        elif stat_result.interval_status != "not_applicable":
            lines.append(f"**Interval:** {stat_result.interval_status.replace('_', ' ').title()}")
            lines.append("")

        # Test Statistic
        if stat_result.statistic is not None:
            lines.append(f"**Test Statistic:** {stat_result.statistic:.4f}")
            if stat_result.degrees_of_freedom is not None:
                lines.append(f"**Degrees of Freedom:** {stat_result.degrees_of_freedom}")
            lines.append("")

        # P-value
        if stat_result.p_value is not None:
            lines.append(f"**P-value:** {stat_result.p_value:.6f}")
            if stat_result.adjusted_p_value is not None:
                lines.append(f"**Adjusted P-value:** {stat_result.adjusted_p_value:.6f}")
            lines.append("")

        # Exclusions
        if stat_result.exclusions:
            lines.append("**Exclusions:**")
            for k, v in stat_result.exclusions.items():
                lines.append(f"- {k}: {v}")
            lines.append("")

        # Assumption Checks (from statistical result)
        if stat_result.assumption_checks:
            lines.append("**Assumption Checks (from test):**")
            for k, v in stat_result.assumption_checks.items():
                if isinstance(v, dict):
                    lines.append(f"- {k}:")
                    for k2, v2 in v.items():
                        lines.append(f"  - {k2}: {v2}")
                else:
                    lines.append(f"- {k}: {v}")
            lines.append("")

    # Warnings
    if result.warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in result.warnings:
            lines.append(f"- ⚠️ {w}")
        lines.append("")

    # Limitations
    lines.append("## Limitations & Scope")
    lines.append("")
    lines.append(f"- This analysis is **{result.request.analysis_purpose}** in nature.")
    if result.request.study_design.value == "unknown":
        lines.append("- Study design was not confirmed; only descriptive results are valid.")
    lines.append("- Confidence intervals assume correct model specification and independence.")
    lines.append(f"- Missing data handled via {result.request.missing_policy.value}; results may be biased if missingness is not at random.")
    lines.append("- Effect size interpretations are conventional guidelines, not definitive thresholds.")
    lines.append("- Correlation does not imply causation.")
    lines.append("")

    # Reproducibility
    lines.append("## Reproducibility")
    lines.append("")
    lines.append("- **Run Manifest:** `run_manifest.json`")
    lines.append("- **Recipe:** `recipe.json`")
    lines.append("- **Data Dictionary:** `data_dictionary.csv`")
    lines.append("- **Quality Issues:** `quality_issues.csv`")
    lines.append("- **Software Versions:** See `run_manifest.json`")
    lines.append("")

    return "\n".join(lines)


def generate_html_report(markdown: str) -> str:
    """Convert Markdown to HTML with basic styling."""
    import markdown as md

    html = md.markdown(markdown, extensions=["tables", "fenced_code", "toc"])

    # Add CSS
    css = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 2rem; line-height: 1.6; }
        h1, h2, h3 { color: #1a1a2e; }
        code { background: #f4f4f4; padding: 0.2em 0.4em; border-radius: 3px; }
        pre { background: #f8f8f8; padding: 1rem; border-radius: 5px; overflow-x: auto; }
        table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
        th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; }
        th { background: #f0f0f0; }
        .warning { background: #fff3cd; border: 1px solid #ffc107; padding: 1rem; border-radius: 5px; margin: 1rem 0; }
        img { max-width: 100%; height: auto; }
    </style>
    """

    return f"<!DOCTYPE html><html><head><meta charset='utf-8'>{css}</head><body>{html}</body></html>"


def generate_results_csv(result: AnalysisResult) -> str:
    """Generate CSV with statistical results."""
    rows = []
    for i, stat in enumerate(result.statistical_results):
        row = {
            "analysis_id": i + 1,
            "method": stat.method.value,
            "estimate": stat.estimate,
            "ci_lower": stat.interval[0] if stat.interval else None,
            "ci_upper": stat.interval[1] if stat.interval else None,
            "interval_method": stat.interval_method.value,
            "interval_status": stat.interval_status,
            "statistic": stat.statistic,
            "df": stat.degrees_of_freedom,
            "p_value": stat.p_value,
            "adjusted_p_value": stat.adjusted_p_value,
            "q_value": stat.q_value,
            "effect_size": stat.effect_size,
            "effect_interpretation": stat.effect_size_interpretation,
            "effect_magnitude": stat.effect_magnitude_label,
            "unstandardized_effect": stat.unstandardized_effect,
            "unstandardized_ci_lower": stat.unstandardized_effect_ci[0] if stat.unstandardized_effect_ci else None,
            "unstandardized_ci_upper": stat.unstandardized_effect_ci[1] if stat.unstandardized_effect_ci else None,
        }
        # Add group counts
        for k, v in stat.group_counts.items():
            row[f"n_{k}"] = v
        rows.append(row)

    df = pl.DataFrame(rows)
    # Apply formula injection protection if enabled
    settings = get_settings()
    if settings.formula_injection_protection:
        for col in df.columns:
            if df[col].dtype == pl.String:
                df = df.with_columns(pl.col(col).map_elements(escape_csv_value, return_dtype=pl.String))

    return df.write_csv()


def generate_assumption_csv(assumption_report: AssumptionReport) -> str:
    """Generate CSV with assumption diagnostics."""
    rows = []
    for check in assumption_report.checks:
        rows.append({
            "check_name": check.name,
            "passed": check.passed,
            "value": check.value,
            "threshold": check.threshold,
            "message": check.message,
            "severity": check.severity,
        })

    if not rows:
        rows.append({"check_name": "none", "passed": True, "value": None, "threshold": None, "message": "No assumption checks", "severity": "info"})

    df = pl.DataFrame(rows)
    return df.write_csv()


def generate_quality_issues_csv(profile: Any) -> str:
    """Generate CSV with quality issues."""
    rows = []

    # Missingness
    for issue in profile.quality_issues.get("missingness", []):
        rows.append({
            "issue_type": "missingness",
            "column": issue["column"],
            "severity": issue["severity"],
            "details": f"{issue['null_count']} missing ({issue['null_pct']:.1f}%)",
        })

    # Constant columns
    for col in profile.quality_issues.get("constant_columns", []):
        rows.append({
            "issue_type": "constant_column",
            "column": col,
            "severity": "high",
            "details": "All values identical",
        })

    # High cardinality
    for issue in profile.quality_issues.get("high_cardinality", []):
        rows.append({
            "issue_type": "high_cardinality",
            "column": issue["column"],
            "severity": "medium",
            "details": f"{issue['unique_count']} unique values",
        })

    # Numeric issues
    for issue in profile.quality_issues.get("numeric_issues", []):
        rows.append({
            "issue_type": "numeric_issue",
            "column": issue["column"],
            "severity": "high",
            "details": f"{issue['issue']}: {issue['count']} occurrences",
        })

    # Duplicates
    for issue in profile.quality_issues.get("duplicates", []):
        rows.append({
            "issue_type": "duplicate_rows",
            "column": "",
            "severity": "medium",
            "details": f"{issue['count']} duplicate rows",
        })

    if not rows:
        rows.append({"issue_type": "none", "column": "", "severity": "info", "details": "No quality issues detected"})

    df = pl.DataFrame(rows)
    return df.write_csv()


def generate_reproduction_script(
    dataset_ref: DatasetRef,
    import_spec: Any,
    column_roles: list[Any],
    recipe: list[Any],
    analysis_request: AnalysisRequest,
    result: AnalysisResult,
) -> str:
    """Generate a standalone Python script to reproduce the analysis."""
    script_lines = [
        "#!/usr/bin/env python3",
        "\"\"\"",
        f"CleanSheet Reproduction Script",
        f"Run ID: {result.run_id}",
        f"Generated: {datetime.now(timezone.utc).isoformat()}Z",
        f"Source Data Hash: {dataset_ref.source_sha256}",
        "\"\"\"",
        "",
        "import json",
        "import hashlib",
        "from pathlib import Path",
        "",
        "import numpy as np",
        "import polars as pl",
        "from scipy import stats",
        "",
        "# ============================================================",
        "# CONFIGURATION (extracted from CleanSheet run manifest)",
        "# ============================================================",
        "",
        f"SOURCE_FILE = \"{{source_file}}\"  # Replace with path to your data file",
        f"SOURCE_SHA256 = \"{dataset_ref.source_sha256}\"",
        f"RECIPE = {json.dumps([r.model_dump() for r in recipe], indent=2, default=str)}",
        f"ANALYSIS_REQUEST = {analysis_request.model_dump_json(indent=2)}",
        f"COLUMN_ROLES = {json.dumps([r.model_dump() for r in column_roles], indent=2, default=str)}",
        "",
        "# ============================================================",
        "# STEP 1: LOAD AND VERIFY SOURCE DATA",
        "# ============================================================",
        "",
        "def load_and_verify_source(filepath: str) -> pl.DataFrame:",
        "    \"\"\"Load source file and verify SHA-256 hash.\"\"\"",
        "    data = Path(filepath).read_bytes()",
        "    actual_sha256 = hashlib.sha256(data).hexdigest()",
        f"    expected_sha256 = \"{dataset_ref.source_sha256}\"",
        "    if actual_sha256 != expected_sha256:",
        f"        raise ValueError(f\"Source file hash mismatch: expected {{expected_sha256}}, got {{actual_sha256}}\")",
        "    ",
        f"    if filepath.suffix.lower() in ['.parquet', '.pq']:",
        "        df = pl.read_parquet(filepath)",
        "    else:",
        "        df = pl.read_csv(filepath)",
        "    return df",
        "",
        "# ============================================================",
        "# STEP 2: APPLY CLEANING RECIPE",
        "# ============================================================",
        "",
        "def apply_recipe(df: pl.DataFrame, recipe: list) -> pl.DataFrame:",
        "    \"\"\"Apply cleaning recipe steps to DataFrame.\"\"\"",
        "    for step in recipe:",
        "        op = step.get('operation')",
        "        args = step.get('arguments', {})",
        "        ",
        "        if op == 'rename':",
        "            mapping = args.get('mapping', {})",
        "            df = df.rename(mapping)",
        "        elif op == 'filter':",
        "            expr_str = args.get('expression')",
        "            if expr_str:",
        "                df = df.filter(eval(expr_str, {\"pl\": pl}))",
        "        elif op == 'cast':",
        "            casts = args.get('casts', {})",
        "            for col, dtype_str in casts.items():",
        "                dtype = getattr(pl, dtype_str)",
        "                df = df.with_columns(pl.col(col).cast(dtype).alias(col))",
        "        elif op == 'deduplicate':",
        "            subset = args.get('subset')",
        "            keep = args.get('keep', 'first')",
        "            if subset:",
        "                df = df.unique(subset=subset, keep=keep, maintain_order=True)",
        "            else:",
        "                df = df.unique(keep=keep, maintain_order=True)",
        "        elif op == 'drop_columns':",
        "            columns = args.get('columns', [])",
        "            df = df.drop(columns)",
        "        elif op == 'recode_categorical':",
        "            mapping = args.get('mapping', {})",
        "            for col, recode in mapping.items():",
        "                df = df.with_columns(pl.col(col).replace(recode).alias(col))",
        "        elif op == 'flag_outliers':",
        "            col = args.get('column')",
        "            lower = args.get('lower')",
        "            upper = args.get('upper')",
        "            flag_col = args.get('flag_column', f'{col}_outlier')",
        "            df = df.with_columns(",
        "                ((pl.col(col) < lower) | (pl.col(col) > upper)).alias(flag_col)",
        "            )",
        "    return df",
        "",
        "# ============================================================",
        "# STEP 3: RUN STATISTICAL ANALYSIS",
        "# ============================================================",
        "",
        "def run_welch_t(df: pl.DataFrame, request: dict) -> dict:",
        "    \"\"\"Run Welch's t-test with Hedges' g and bootstrap CI.\"\"\"",
        "    vars_ = request['variables']",
        "    levels = request.get('group_levels', [])",
        "    contrast = request.get('contrast', '')",
        "    confidence = request.get('confidence_level', 0.95)",
        "    seed = request.get('seed', 42)",
        "    alternative = request.get('alternative', 'two-sided')",
        "    ",
        "    outcome_col = vars_['outcome']",
        "    group_col = vars_['group']",
        "    ",
        "    # Determine contrast order",
        "    if contrast and contrast.endswith(f\"_minus_{{levels[1]}}\") and contrast.startswith(f\"{{levels[0]}}_\"):",
        "        first, second = levels[0], levels[1]",
        "    elif contrast and contrast.endswith(f\"_minus_{{levels[0]}}\") and contrast.startswith(f\"{{levels[1]}}_\"):",
        "        first, second = levels[1], levels[0]",
        "    else:",
        "        first, second = levels[0], levels[1]",
        "    ",
        "    data = df.filter(",
        "        pl.col(group_col).is_in(levels) &",
        "        pl.col(outcome_col).is_not_null() &",
        "        ~pl.col(outcome_col).is_infinite() &",
        "        ~pl.col(outcome_col).is_nan()",
        "    )",
        "    ",
        "    group_first = data.filter(pl.col(group_col) == first)[outcome_col].to_numpy()",
        "    group_second = data.filter(pl.col(group_col) == second)[outcome_col].to_numpy()",
        "    ",
        "    # Welch's t-test",
        "    result = stats.ttest_ind(group_first, group_second, equal_var=False, alternative=alternative)",
        "    mean_diff = float(np.mean(group_first) - np.mean(group_second))",
        "    se = float(np.sqrt(np.var(group_first, ddof=1)/len(group_first) + np.var(group_second, ddof=1)/len(group_second)))",
        "    df_welch = float((np.var(group_first, ddof=1)/len(group_first) + np.var(group_second, ddof=1)/len(group_second))**2 / (",
        "        (np.var(group_first, ddof=1)/len(group_first))**2/(len(group_first)-1) +",
        "        (np.var(group_second, ddof=1)/len(group_second))**2/(len(group_second)-1)",
        "    ))",
        "    ",
        "    # CI for mean difference",
        "    from scipy.stats import t",
        "    alpha = 1 - confidence",
        "    t_crit = t.ppf(1 - alpha/2, df_welch)",
        "    ci_low = mean_diff - t_crit * se",
        "    ci_high = mean_diff + t_crit * se",
        "    ",
        "    # Hedges' g",
        "    pooled_sd = np.sqrt(((len(group_first)-1)*np.var(group_first, ddof=1) + (len(group_second)-1)*np.var(group_second, ddof=1)) / (len(group_first) + len(group_second) - 2))",
        "    cohen_d = mean_diff / pooled_sd if pooled_sd > 0 else 0",
        "    n_total = len(group_first) + len(group_second)",
        "    hedges_correction = 1 - 3 / (4 * n_total - 9) if n_total > 2 else 1",
        "    hedges_g = cohen_d * hedges_correction",
        "    ",
        "    # Bootstrap CI for Hedges' g",
        "    effect_size_ci = None",
        "    try:",
        "        from scipy.stats import bootstrap",
        "        def hedges_g_fn(x1, x2):",
        "            md = np.mean(x1) - np.mean(x2)",
        "            psd = np.sqrt(((len(x1)-1)*np.var(x1, ddof=1) + (len(x2)-1)*np.var(x2, ddof=1)) / (len(x1) + len(x2) - 2))",
        "            if psd == 0: return 0.0",
        "            cd = md / psd",
        "            n = len(x1) + len(x2)",
        "            hc = 1 - 3 / (4 * n - 9) if n > 2 else 1",
        "            return cd * hc",
        "        rng = np.random.default_rng(seed)",
        "        ci = bootstrap(",
        "            (group_first, group_second),",
        "            hedges_g_fn,",
        "            confidence_level=confidence,",
        "            n_resamples=2000,",
        "            method='percentile',",
        "            paired=False,",
        "            rng=rng,",
        "        )",
        "        effect_size_ci = (float(ci.confidence_interval.low), float(ci.confidence_interval.high))",
        "    except Exception:",
        "        pass",
        "    ",
        "    return {",
        "        'method': 'welch_t',",
        "        'estimate': mean_diff,",
        "        'ci': (ci_low, ci_high),",
        "        'statistic': float(result.statistic),",
        "        'df': df_welch,",
        "        'p_value': float(result.pvalue),",
        "        'effect_size': float(hedges_g),",
        "        'effect_size_ci': effect_size_ci,",
        "        'group_counts': {first: len(group_first), second: len(group_second)},",
        "    }",
        "",
        "# ============================================================",
        "# MAIN EXECUTION",
        "# ============================================================",
        "",
        "if __name__ == \"__main__\":",
        "    import sys",
        "    ",
        "    if len(sys.argv) < 2:",
        "        print(f\"Usage: {{sys.argv[0]}} <source_file>\")",
        "        sys.exit(1)",
        "    ",
        "    source_file = sys.argv[1]",
        "    ",
        "    print(f\"Loading data from {{source_file}}...\")",
        "    df = load_and_verify_source(source_file)",
        "    print(f\"Loaded {{df.height}} rows × {{df.width}} columns\")",
        "    ",
        "    print(\"Applying cleaning recipe...\")",
        "    df = apply_recipe(df, RECIPE)",
        "    print(f\"Prepared data: {{df.height}} rows × {{df.width}} columns\")",
        "    ",
        "    print(f\"Running analysis: {{ANALYSIS_REQUEST['goal']}}...\")",
        "    ",
        "    if ANALYSIS_REQUEST['goal'] == 'compare_two_means':",
        "        method = ANALYSIS_REQUEST.get('method', 'welch_t')",
        "        if method == 'welch_t':",
        "            res = run_welch_t(df, ANALYSIS_REQUEST)",
        "        elif method == 'mann_whitney_u':",
        "            print(\"Mann-Whitney U not yet implemented in reproduction script\")",
        "            sys.exit(1)",
        "        else:",
        "            print(f\"Unknown method: {{method}}\")",
        "            sys.exit(1)",
        "    else:",
        "        print(f\"Goal {{ANALYSIS_REQUEST['goal']}} not yet implemented in reproduction script\")",
        "        sys.exit(1)",
        "    ",
        "    print(f\"\\nResults:\")",
        "    print(f\"  Estimate: {{res['estimate']:.4f}}\")",
        "    print(f\"  95% CI: [{{res['ci'][0]:.4f}}, {{res['ci'][1]:.4f}}]\")",
        "    print(f\"  t({{res['df']:.1f}}) = {{res['statistic']:.4f}}, p = {{res['p_value']:.6f}}\")",
        "    print(f\"  Hedges' g = {{res['effect_size']:.4f}}\")",
        "    if res['effect_size_ci']:",
        "        print(f\"  Hedges' g 95% CI: [{{res['effect_size_ci'][0]:.4f}}, {{res['effect_size_ci'][1]:.4f}}]\")",
        "    print(f\"  Group counts: {{res['group_counts']}}\")",
        "",
        "# ============================================================",
        "# VERIFICATION",
        "# ============================================================",
        "",
        "    # Verify against original results",
        "    original = {",
        f"        'estimate': {result.statistical_results[0].estimate},",
        f"        'ci': {list(result.statistical_results[0].interval) if result.statistical_results[0].interval else None},",
        f"        'statistic': {result.statistical_results[0].statistic},",
        f"        'df': {result.statistical_results[0].degrees_of_freedom},",
        f"        'p_value': {result.statistical_results[0].p_value},",
        f"        'effect_size': {result.statistical_results[0].effect_size},",
        f"        'effect_size_ci': {list(result.statistical_results[0].effect_size_ci) if result.statistical_results[0].effect_size_ci else None},",
        "    }",
        "    ",
        "    tolerance = 1e-6",
        "    for key in ['estimate', 'statistic', 'p_value', 'effect_size']:",
        "        if key in original and original[key] is not None:",
        "            diff = abs(res[key] - original[key])",
        "            if diff > tolerance:",
        "                print(f\"⚠️  MISMATCH in {{key}}: reproduced={{res[key]}}, original={{original[key]}} (diff={{diff}})\")",
        "            else:",
        "                print(f\"✅ {{key}} matches (diff={{diff:.2e}})\")",
        "    ",
        "    print(\"\\nReproduction complete!\")",
        "",
    ]
    return "\n".join(script_lines)


def generate_run_manifest(
    dataset_ref: DatasetRef,
    import_spec: Any,
    column_roles: list[Any],
    recipe: list[Any],
    analysis_request: AnalysisRequest,
    result: AnalysisResult,
    settings: Any,
) -> RunManifest:
    """Generate reproducibility manifest."""
    # Compute hashes
    import_spec_hash = hashlib.sha256(import_spec.model_dump_json(sort_keys=True).encode()).hexdigest()[:16]
    schema_hash = dataset_ref.schema_hash
    roles_hash = hashlib.sha256(json.dumps([r.model_dump() for r in column_roles], sort_keys=True).encode()).hexdigest()[:16]
    recipe_hash = hashlib.sha256(json.dumps([r.model_dump() for r in recipe], sort_keys=True).encode()).hexdigest()[:16]
    analysis_spec_hash = hashlib.sha256(analysis_request.model_dump_json(sort_keys=True).encode()).hexdigest()[:16]

    return RunManifest(
        run_id=result.run_id,
        input_fingerprint=dataset_ref.source_sha256,
        import_spec_hash=import_spec_hash,
        schema_hash=schema_hash,
        roles_hash=roles_hash,
        recipe_hash=recipe_hash,
        analysis_spec_hash=analysis_spec_hash,
        rules_version="1.0",
        dependency_versions=settings.get_dependency_versions() if hasattr(settings, "get_dependency_versions") else {},
        seeds={"analysis": analysis_request.seed, "plotting": 42},
        timestamps={
            "started": datetime.now(timezone.utc).isoformat(),
            "completed": datetime.now(timezone.utc).isoformat(),
        },
        resource_limits=settings.get_resource_limits() if hasattr(settings, "get_resource_limits") else {},
        outcomes={
            "status": result.status,
            "n_analyses": len(result.statistical_results),
            "n_plots": len(result.plots),
            "warnings": result.warnings,
        },
    )


def generate_export_bundle(
    workspace: Workspace,
    result: AnalysisResult,
    dataset_ref: DatasetRef,
    import_spec: Any,
    column_roles: list[Any],
    recipe: list[Any],
    profile: Any,
    include_data: bool = False,
    plots: list[Any] | None = None,
    assumption_report: AssumptionReport | None = None,
) -> Path:
    """Generate a complete export bundle as a ZIP file."""
    settings = get_settings()

    # Generate components
    manifest = generate_run_manifest(
        dataset_ref, import_spec, column_roles, recipe,
        result.request, result, settings
    )

    markdown = generate_markdown_report(result, dataset_ref, profile, manifest, assumption_report)
    html = generate_html_report(markdown)
    results_csv = generate_results_csv(result)
    assumption_csv = generate_assumption_csv(assumption_report) if assumption_report else ""
    data_dict_csv = generate_data_dictionary(profile).write_csv()
    quality_csv = generate_quality_issues_csv(profile)
    recipe_json = generate_recipe_json(recipe)
    manifest_json = manifest.to_json()
    reproduction_script = generate_reproduction_script(
        dataset_ref, import_spec, column_roles, recipe,
        result.request, result
    )

    # Use provided plots or generate placeholder specs
    plot_data = plots if plots is not None else []

    # Create ZIP in memory
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Core files
        zf.writestr("report.md", markdown)
        zf.writestr("report.html", html)
        zf.writestr("results.csv", results_csv)
        if assumption_csv:
            zf.writestr("assumption_diagnostics.csv", assumption_csv)
        zf.writestr("data_dictionary.csv", data_dict_csv)
        zf.writestr("quality_issues.csv", quality_csv)
        zf.writestr("recipe.json", recipe_json)
        zf.writestr("run_manifest.json", manifest_json)
        zf.writestr("cleansheet_reproduce.py", reproduction_script)

        # Figures
        for i, plot in enumerate(plot_data):
            ext = "png"
            if hasattr(plot, "spec"):
                plot_type = plot.spec.plot_type.value
            else:
                plot_type = "plot"
            filename = f"figures/plot_{i+1}_{plot_type}.{ext}"
            if hasattr(plot, "png_bytes"):
                zf.writestr(filename, plot.png_bytes)

        # Prepared data (optional)
        if include_data and recipe:
            # Get latest prepared data
            pass  # Would need recipe hash to retrieve

    zip_buffer.seek(0)

    # Save to workspace
    export_name = f"cleansheet_export_{result.run_id}.zip"
    export_path = workspace.store_artifact(export_name, zip_buffer.read(), "exports")

    return export_path