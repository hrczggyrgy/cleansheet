"""Data preparation service with reversible transformations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from CleanSheet.config import get_settings
from CleanSheet.contracts import CleaningStep, DatasetRef, TransformOp
from CleanSheet.engine.execution import (
    LazyExecutor,
    build_preparation_pipeline,
    compute_recipe_hash,
    get_or_create_prepared,
)
from CleanSheet.jobs.workspace import Workspace


@dataclass
class PreparationResult:
    """Result of a preparation operation."""

    data: pl.DataFrame
    recipe: list[CleaningStep]
    recipe_hash: str
    preview_before: pl.DataFrame
    preview_after: pl.DataFrame
    operation_summary: str


def apply_transform(
    executor: LazyExecutor,
    current_recipe: list[CleaningStep],
    new_step: CleaningStep,
) -> PreparationResult:
    """Apply a new transformation step to the recipe."""
    # Build new recipe
    new_recipe = current_recipe + [new_step]

    # Get preview before
    preview_before = executor.preview(10)

    # Build pipeline with new recipe
    recipe_dicts = [step.model_dump() for step in new_recipe]
    lf = build_preparation_pipeline(executor.source_lf, recipe_dicts)

    # Materialize
    df = lf.collect(engine="streaming" if get_settings().polars_streaming else "in-memory")

    # Get preview after
    preview_after = df.head(10)

    # Generate summary
    summary = _summarize_step(new_step, preview_before, preview_after)

    return PreparationResult(
        data=df,
        recipe=new_recipe,
        recipe_hash=compute_recipe_hash(recipe_dicts),
        preview_before=preview_before,
        preview_after=preview_after,
        operation_summary=summary,
    )


def _summarize_step(step: CleaningStep, before: pl.DataFrame, after: pl.DataFrame) -> str:
    """Generate human-readable summary of a transformation."""
    op = step.operation
    args = step.arguments

    if op == TransformOp.RENAME:
        mapping = args.get("mapping", {})
        return f"Renamed {len(mapping)} column(s): {', '.join(f'{k}→{v}' for k, v in list(mapping.items())[:3])}"

    if op == TransformOp.FILTER:
        expr = args.get("expression", "")
        rows_before = before.height
        rows_after = after.height
        return f"Filtered rows: {rows_before:,} → {rows_after:,} ({rows_before - rows_after:,} removed)"

    if op == TransformOp.CAST:
        casts = args.get("casts", {})
        return f"Cast {len(casts)} column(s): {', '.join(f'{k}→{v}' for k, v in list(casts.items())[:3])}"

    if op == TransformOp.DEDUPLICATE:
        subset = args.get("subset")
        rows_before = before.height
        rows_after = after.height
        key = f" on {subset}" if subset else ""
        return f"Deduplicated{key}: {rows_before:,} → {rows_after:,} ({rows_before - rows_after:,} removed)"

    if op == TransformOp.DROP_COLUMNS:
        cols = args.get("columns", [])
        return f"Dropped {len(cols)} column(s): {', '.join(cols[:5])}"

    if op == TransformOp.RECODE_CATEGORICAL:
        mapping = args.get("mapping", {})
        return f"Recoded categorical values in {len(mapping)} column(s)"

    if op == TransformOp.IMPUTE:
        return "Applied imputation"

    return f"Applied {op.value}"


def create_transform_step(
    operation: TransformOp,
    arguments: dict[str, Any],
    input_schema: dict[str, str],
    output_schema: dict[str, str],
    affected_rows: int,
    affected_cols: int,
) -> CleaningStep:
    """Create a new transform step with metadata."""
    step_id = len(arguments)  # Will be overridden by caller
    return CleaningStep(
        step_id=step_id,
        operation=operation,
        arguments=arguments,
        input_schema={k: v for k, v in input_schema.items()},
        output_schema={k: v for k, v in output_schema.items()},
        affected_row_count=affected_rows,
        affected_column_count=affected_cols,
    )


def suggest_transformations(profile_result: Any) -> list[dict[str, Any]]:
    """Suggest transformations based on profiling results."""
    suggestions = []

    for col in profile_result.columns:
        # Constant columns
        if col.is_constant:
            suggestions.append({
                "operation": TransformOp.DROP_COLUMNS,
                "arguments": {"columns": [col.name]},
                "reason": f"Column '{col.name}' is constant (all values identical)",
                "priority": "high",
            })

        # High missingness
        if col.null_pct > 80:
            suggestions.append({
                "operation": TransformOp.DROP_COLUMNS,
                "arguments": {"columns": [col.name]},
                "reason": f"Column '{col.name}' has {col.null_pct:.1f}% missing values",
                "priority": "high",
            })
        elif col.null_pct > 20:
            suggestions.append({
                "operation": TransformOp.IMPUTE,
                "arguments": {
                    "column": col.name,
                    "strategy": "median" if col.semantic_role == "continuous" else "mode",
                },
                "reason": f"Column '{col.name}' has {col.null_pct:.1f}% missing values",
                "priority": "medium",
            })

        # High cardinality categorical
        if col.semantic_role == "categorical" and col.n_categories > 50:
            suggestions.append({
                "operation": TransformOp.RECODE_CATEGORICAL,
                "arguments": {
                    "column": col.name,
                    "strategy": "top_k",
                    "k": 20,
                },
                "reason": f"Column '{col.name}' has {col.n_categories} categories (consider grouping)",
                "priority": "low",
            })

        # Numeric identifiers
        if col.semantic_role == "continuous" and "id" in col.name.lower() and col.n_unique == col.n_rows:
            suggestions.append({
                "operation": TransformOp.CAST,
                "arguments": {"casts": {col.name: "String"}},
                "reason": f"Column '{col.name}' appears to be an identifier stored as numeric",
                "priority": "medium",
            })

    return suggestions


def get_prepared_data(
    workspace: Workspace,
    dataset_ref: DatasetRef,
    recipe: list[CleaningStep],
) -> pl.DataFrame:
    """Get prepared data, using cache if available."""
    recipe_dicts = [step.model_dump() for step in recipe]
    return get_or_create_prepared(workspace, dataset_ref, recipe_dicts)


def undo_last_step(recipe: list[CleaningStep]) -> list[CleaningStep]:
    """Remove the last transformation step."""
    if not recipe:
        return []
    return recipe[:-1]


def redo_step(
    executor: LazyExecutor,
    recipe: list[CleaningStep],
    step_index: int,
) -> PreparationResult:
    """Redo a step that was undone (re-apply from that point)."""
    if step_index >= len(recipe):
        raise ValueError("Step index out of range")

    # Rebuild from step_index onwards
    new_recipe = recipe[:step_index + 1]
    recipe_dicts = [step.model_dump() for step in new_recipe]

    lf = build_preparation_pipeline(executor.source_lf, recipe_dicts)
    df = lf.collect(engine="streaming" if get_settings().polars_streaming else "in-memory")

    return PreparationResult(
        data=df,
        recipe=new_recipe,
        recipe_hash=compute_recipe_hash(recipe_dicts),
        preview_before=executor.preview(10),
        preview_after=df.head(10),
        operation_summary=f"Redid step {step_index}: {recipe[step_index].operation.value}",
    )
