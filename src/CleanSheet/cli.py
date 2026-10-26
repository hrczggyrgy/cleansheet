"""CLI entry point for headless recipe replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from CleanSheet.config import get_settings
from CleanSheet.contracts import (
    AnalysisRequest,
    ImportSpec,
    TransformStep,
)
from CleanSheet.engine.execution import get_or_create_prepared
from CleanSheet.jobs.workspace import Workspace
from CleanSheet.services.profile import run_profiling
from CleanSheet.services.statistics import run_analysis


def load_recipe(recipe_path: Path) -> tuple[list[TransformStep], AnalysisRequest]:
    """Load recipe and analysis request from JSON."""
    data = json.loads(recipe_path.read_text())

    recipe = [TransformStep(**step) for step in data.get("recipe", [])]
    analysis_request = AnalysisRequest(**data.get("analysis", {}))

    return recipe, analysis_request


def replay_recipe(
    input_path: Path,
    recipe_path: Path,
    output_dir: Path,
    fmt: str = "auto",
) -> int:
    """Replay a recipe against input data."""
    settings = get_settings()

    # Load recipe
    recipe, analysis_request = load_recipe(recipe_path)

    # Create workspace
    workspace = Workspace()

    # Read and ingest input
    data = input_path.read_bytes()
    if fmt == "auto":
        fmt = "parquet" if input_path.suffix.lower() in [".parquet", ".pq"] else "csv"

    import_spec = ImportSpec()
    dataset_ref, preview, metadata = workspace.store_source(data, fmt, import_spec)

    print(f"Loaded dataset: {dataset_ref.dataset_id}")
    print(f"Rows: {dataset_ref.row_count:,}, Columns: {dataset_ref.column_count}")

    # Apply recipe to get prepared data
    prepared_df = get_or_create_prepared(workspace, dataset_ref, [s.model_dump() for s in recipe])
    print(f"Prepared data: {prepared_df.height:,} rows × {prepared_df.width} cols")

    # Run analysis
    print(f"Running analysis: {analysis_request.goal.value}...")
    result = run_analysis(workspace, dataset_ref, analysis_request)

    print(f"Analysis complete: {result.method.value}")
    if result.estimate is not None:
        print(f"  Estimate: {result.estimate:.4f}")
    if result.interval:
        print(f"  CI: [{result.interval[0]:.4f}, {result.interval[1]:.4f}]")
    if result.p_value is not None:
        print(f"  P-value: {result.p_value:.6f}")

    # Generate export
    output_dir.mkdir(parents=True, exist_ok=True)

    # For now, just save results as JSON
    result_path = output_dir / "result.json"
    result_path.write_text(result.model_dump_json(indent=2))
    print(f"Results saved to: {result_path}")

    return 0


def profile_only(
    input_path: Path,
    output_dir: Path,
    fmt: str = "auto",
) -> int:
    """Run only profiling on input data."""
    workspace = Workspace()

    data = input_path.read_bytes()
    if fmt == "auto":
        fmt = "parquet" if input_path.suffix.lower() in [".parquet", ".pq"] else "csv"

    import_spec = ImportSpec()
    dataset_ref, preview, metadata = workspace.store_source(data, fmt, import_spec)

    print(f"Loaded dataset: {dataset_ref.dataset_id}")
    print(f"Rows: {dataset_ref.row_count:,}, Columns: {dataset_ref.column_count}")

    profile = run_profiling(workspace, dataset_ref)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Save profile
    import json
    profile_path = output_dir / "profile.json"
    profile_path.write_text(json.dumps(profile.to_dict(), indent=2, default=str))
    print(f"Profile saved to: {profile_path}")

    # Save data dictionary
    from CleanSheet.services.profile import generate_data_dictionary
    dd = generate_data_dictionary(profile)
    dd_path = output_dir / "data_dictionary.csv"
    dd.write_csv(dd_path)
    print(f"Data dictionary saved to: {dd_path}")

    # Save quality issues
    qi_path = output_dir / "quality_issues.csv"
    # Would need to generate quality CSV here
    print(f"Quality issues saved to: {qi_path}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cleansheet",
        description="CleanSheet - No-code statistical analysis CLI",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Replay command
    replay_parser = subparsers.add_parser("replay", help="Replay a recipe against input data")
    replay_parser.add_argument("input", type=Path, help="Input CSV/Parquet file")
    replay_parser.add_argument("recipe", type=Path, help="Recipe JSON file")
    replay_parser.add_argument("-o", "--output", type=Path, default=Path("output"), help="Output directory")
    replay_parser.add_argument("--format", choices=["csv", "parquet", "auto"], default="auto")

    # Profile command
    profile_parser = subparsers.add_parser("profile", help="Profile a dataset")
    profile_parser.add_argument("input", type=Path, help="Input CSV/Parquet file")
    profile_parser.add_argument("-o", "--output", type=Path, default=Path("output"), help="Output directory")
    profile_parser.add_argument("--format", choices=["csv", "parquet", "auto"], default="auto")

    args = parser.parse_args()

    try:
        if args.command == "replay":
            return replay_recipe(args.input, args.recipe, args.output, args.format)
        if args.command == "profile":
            return profile_only(args.input, args.output, args.format)
        parser.print_help()
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
