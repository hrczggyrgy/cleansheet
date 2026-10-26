"""Report generation and export service."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import polars as pl

from CleanSheet.config import get_settings
from CleanSheet.contracts import (
    AnalysisRequest,
    AnalysisResult,
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
) -> str:
    """Generate a Markdown report."""
    lines = []

    # Header
    lines.append("# CleanSheet Analysis Report")
    lines.append("")
    lines.append(f"**Run ID:** {result.run_id}")
    lines.append(f"**Generated:** {datetime.utcnow().isoformat()}Z")
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

        # Assumption Checks
        if stat_result.assumption_checks:
            lines.append("**Assumption Checks:**")
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
    lines.append("## Limitations")
    lines.append("")
    lines.append(f"- This analysis is **{result.request.analysis_purpose}** in nature.")
    if result.request.study_design.value == "unknown":
        lines.append("- Study design was not confirmed; only descriptive results are valid.")
    lines.append("- Confidence intervals assume correct model specification and independence.")
    lines.append(f"- Missing data handled via {result.request.missing_policy.value}; results may be biased if missingness is not at random.")
    lines.append("- Effect size interpretations are conventional guidelines, not definitive thresholds.")
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
            "effect_size": stat.effect_size,
            "effect_interpretation": stat.effect_size_interpretation,
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


def generate_recipe_json(result: AnalysisResult) -> str:
    """Generate recipe JSON."""
    return result.request.model_dump_json(indent=2)


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
            "started": datetime.utcnow().isoformat(),
            "completed": datetime.utcnow().isoformat(),
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
) -> Path:
    """Generate a complete export bundle as a ZIP file."""
    settings = get_settings()

    # Generate components
    manifest = generate_run_manifest(
        dataset_ref, import_spec, column_roles, recipe,
        result.request, result, settings
    )

    markdown = generate_markdown_report(result, dataset_ref, profile, manifest)
    html = generate_html_report(markdown)
    results_csv = generate_results_csv(result)
    data_dict_csv = generate_data_dictionary(profile).write_csv()
    quality_csv = generate_quality_issues_csv(profile)
    recipe_json = generate_recipe_json(result)
    manifest_json = manifest.to_json()

    # Create ZIP in memory
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Core files
        zf.writestr("report.md", markdown)
        zf.writestr("report.html", html)
        zf.writestr("results.csv", results_csv)
        zf.writestr("data_dictionary.csv", data_dict_csv)
        zf.writestr("quality_issues.csv", quality_csv)
        zf.writestr("recipe.json", recipe_json)
        zf.writestr("run_manifest.json", manifest_json)

        # Figures
        for i, plot in enumerate(result.plots):
            ext = "png"
            filename = f"figures/plot_{i+1}_{plot.spec.plot_type.value}.{ext}"
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
