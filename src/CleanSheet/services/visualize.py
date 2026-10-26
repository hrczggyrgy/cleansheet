"""Visualization service with bounded plotting and Matplotlib worker isolation."""

from __future__ import annotations

import base64
import io
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns

from CleanSheet.contracts import PlotSpec, PlotType
from CleanSheet.engine.sampling import SamplingPlan, stable_sample
from CleanSheet.jobs.workspace import Workspace


@dataclass
class PlotResult:
    """Result of plot generation."""

    spec: PlotSpec
    png_bytes: bytes
    base64: str
    sampling_plan: SamplingPlan | None = None


def _render_plot_worker(spec_dict: dict[str, Any], df_dict: dict[str, Any]) -> bytes:
    """Worker function to render a plot in isolated process."""
    # Reconstruct spec and dataframe
    spec = PlotSpec(**spec_dict)
    df = pl.DataFrame(df_dict)

    # Apply sampling if needed
    if len(df) > spec.max_points:
        df = stable_sample(df, spec.max_points, spec.seed)

    # Create figure
    fig, ax = plt.subplots(figsize=(8, 5), dpi=100)

    try:
        _render_plot_on_axes(fig, ax, df, spec)
        plt.tight_layout()

        # Save to bytes
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        buf.seek(0)
        return buf.read()
    finally:
        plt.close(fig)


def _render_plot_on_axes(fig: plt.Figure, ax: plt.Axes, df: pl.DataFrame, spec: PlotSpec) -> None:
    """Render a plot on the given axes."""
    vars_map = spec.variables
    x = vars_map.get("x")
    y = vars_map.get("y")
    hue = vars_map.get("hue")
    col = vars_map.get("col")

    # Prepare data for seaborn (convert to pandas for compatibility)
    pdf = df.to_pandas()

    # Set style
    sns.set_theme(style="whitegrid", context="notebook")

    if spec.plot_type == PlotType.HISTOGRAM:
        if x:
            sns.histplot(data=pdf, x=x, hue=hue, ax=ax, bins=spec.transform.get("bins", 20))

    elif spec.plot_type == PlotType.ECDF:
        if x:
            sns.ecdfplot(data=pdf, x=x, hue=hue, ax=ax)

    elif spec.plot_type == PlotType.BOXPLOT:
        if x and y:
            sns.boxplot(data=pdf, x=x, y=y, hue=hue, ax=ax,
                       order=spec.category_order.get(x) if x in spec.category_order else None)

    elif spec.plot_type == PlotType.SCATTERPLOT:
        if x and y:
            sns.scatterplot(data=pdf, x=x, y=y, hue=hue, ax=ax, alpha=0.6, s=30)

    elif spec.plot_type == PlotType.COUNT_CHART:
        if x:
            sns.countplot(data=pdf, x=x, hue=hue, ax=ax,
                         order=spec.category_order.get(x) if x in spec.category_order else None)

    elif spec.plot_type == PlotType.CORRELATION_HEATMAP:
        # Compute correlation matrix
        numeric_cols = pdf.select_dtypes(include=[np.number]).columns.tolist()
        if numeric_cols:
            corr = pdf[numeric_cols].corr()
            mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
            sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="vlag",
                       center=0, vmin=-1, vmax=1, ax=ax, cbar_kws={"label": "Correlation"})

    elif spec.plot_type == PlotType.MISSINGNESS_MATRIX:
        # Missingness heatmap
        missing = pdf.isnull().astype(int)
        sns.heatmap(missing, cbar=False, cmap=["white", "red"], ax=ax)
        ax.set_title("Missingness Matrix (red = missing)")

    elif spec.plot_type == PlotType.ESTIMATE_INTERVAL:
        # Point estimate with CI - expects precomputed values in transform
        estimates = spec.transform.get("estimates", [])
        if estimates:
            positions = range(len(estimates))
            labels = [e.get("label", "") for e in estimates]
            points = [e.get("estimate", 0) for e in estimates]
            lowers = [e.get("lower", 0) for e in estimates]
            uppers = [e.get("upper", 0) for e in estimates]

            ax.errorbar(positions, points,
                       yerr=[np.array(points) - np.array(lowers), np.array(uppers) - np.array(points)],
                       fmt="o", capsize=5)
            ax.set_xticks(positions)
            ax.set_xticklabels(labels, rotation=45, ha="right")
            ax.axhline(0, color="gray", linestyle="--", alpha=0.5)

    # Apply labels
    if spec.labels.get("title"):
        ax.set_title(spec.labels["title"])
    if spec.labels.get("xlabel"):
        ax.set_xlabel(spec.labels["xlabel"])
    if spec.labels.get("ylabel"):
        ax.set_ylabel(spec.labels["ylabel"])

    # Apply category limits
    if hue and hue in pdf.columns:
        unique_hue = pdf[hue].nunique()
        if unique_hue > spec.max_categories:
            # Show top categories + "Other"
            top = pdf[hue].value_counts().head(spec.max_categories - 1).index.tolist()
            pdf[hue] = pdf[hue].where(pdf[hue].isin(top), "Other")


def generate_plots(
    workspace: Workspace,
    dataset_ref: Any,
    plot_specs: list[PlotSpec],
) -> list[PlotResult]:
    """Generate multiple plots with worker isolation."""
    from CleanSheet.engine.execution import LazyExecutor

    executor = LazyExecutor(workspace, dataset_ref)
    results = []

    for spec in plot_specs:
        # Get required columns
        cols = list(set(v for v in spec.variables.values() if v))

        # Materialize data for plotting
        df = executor.materialize_for_plotting(cols, spec.max_points, spec.seed)

        # Convert to dict for pickling
        df_dict = {col: df[col].to_list() for col in df.columns}
        spec_dict = spec.model_dump()

        # Render in worker
        try:
            with ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn")) as executor_pool:
                future = executor_pool.submit(_render_plot_worker, spec_dict, df_dict)
                png_bytes = future.result(timeout=30)
        except FuturesTimeoutError:
            raise TimeoutError("Plot rendering timed out")
        except Exception as e:
            raise RuntimeError(f"Plot rendering failed: {e}")

        # Store artifact
        filename = f"plot_{spec.plot_type.value}_{hash(str(spec_dict)) % 10000}.png"
        workspace.store_plot(filename, png_bytes)

        # Create result
        base64_str = base64.b64encode(png_bytes).decode("ascii")
        results.append(PlotResult(
            spec=spec,
            png_bytes=png_bytes,
            base64=base64_str,
        ))

    return results


def create_plot_spec(
    plot_type: PlotType,
    variables: dict[str, str],
    data: pl.DataFrame,
    **kwargs: Any,
) -> PlotSpec:
    """Create a plot spec with smart defaults."""
    # Auto-generate labels
    labels = {}
    if "x" in variables:
        labels["xlabel"] = variables["x"].replace("_", " ").title()
    if "y" in variables:
        labels["ylabel"] = variables["y"].replace("_", " ").title()
    labels["title"] = plot_type.value.replace("_", " ").title()

    # Category ordering for categorical variables
    category_order = {}
    for role, col in variables.items():
        if col in data.columns and data[col].dtype in (pl.String, pl.Categorical):
            cats = data[col].unique().to_list()
            if len(cats) <= 20:
                category_order[col] = cats

    return PlotSpec(
        plot_type=plot_type,
        variables=variables,
        category_order=category_order,
        labels=labels,
        **kwargs,
    )


def recommend_plots(profile_result: Any, column_roles: dict[str, str]) -> list[PlotSpec]:
    """Recommend plots based on data profile."""
    specs = []

    continuous = [c for c, r in column_roles.items() if r == "continuous"]
    categorical = [c for c, r in column_roles.items() if r == "categorical"]
    ordinal = [c for c, r in column_roles.items() if r == "ordinal"]

    # Univariate continuous
    for col in continuous[:5]:
        specs.append(create_plot_spec(
            PlotType.HISTOGRAM, {"x": col}, profile_result,
            max_points=5000,
        ))
        specs.append(create_plot_spec(
            PlotType.ECDF, {"x": col}, profile_result,
            max_points=5000,
        ))

    # Continuous by categorical
    for cat in categorical[:3]:
        for cont in continuous[:3]:
            specs.append(create_plot_spec(
                PlotType.BOXPLOT, {"x": cat, "y": cont}, profile_result,
            ))

    # Scatterplots
    for i, x in enumerate(continuous[:4]):
        for y in continuous[i+1:4]:
            specs.append(create_plot_spec(
                PlotType.SCATTERPLOT, {"x": x, "y": y}, profile_result,
            ))

    # Categorical counts
    for cat in categorical[:5]:
        specs.append(create_plot_spec(
            PlotType.COUNT_CHART, {"x": cat}, profile_result,
        ))

    # Correlation heatmap
    if len(continuous) >= 2:
        specs.append(create_plot_spec(
            PlotType.CORRELATION_HEATMAP, {}, profile_result,
            max_points=10000,
        ))

    # Missingness
    specs.append(create_plot_spec(
        PlotType.MISSINGNESS_MATRIX, {}, profile_result,
        max_points=5000,
    ))

    return specs
