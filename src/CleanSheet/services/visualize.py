"""Visualization service with bounded plotting and Matplotlib worker isolation."""

from __future__ import annotations

import base64
import io
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any

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


# Okabe-Ito colorblind-safe palette
OKABE_ITO_PALETTE = [
    "#0072B2",  # Blue
    "#E69F00",  # Orange
    "#009E73",  # Bluish Green
    "#CC79A7",  # Reddish Purple
    "#56B4E9",  # Sky Blue
    "#D55E00",  # Vermilion
    "#F0E442",  # Yellow
    "#000000",  # Black
]

NEUTRAL_GRAY = "#6B7280"


def _render_plot_worker(spec_dict: dict[str, Any], df_dict: dict[str, Any]) -> bytes:
    """Worker function to render a plot in isolated process."""
    # Reconstruct spec and dataframe
    spec = PlotSpec(**spec_dict)
    df = pl.DataFrame(df_dict)

    # Apply sampling if needed
    if len(df) > spec.max_points:
        df = stable_sample(df, spec.max_points, spec.seed)

    # Create figure
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)

    try:
        _render_plot_on_axes(fig, ax, df, spec)
        plt.tight_layout()

        # Save to bytes
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
        buf.seek(0)
        return buf.read()
    finally:
        plt.close(fig)


def _render_plot_on_axes(fig: plt.Figure, ax: plt.Axes, df: pl.DataFrame, spec: PlotSpec) -> None:
    """Render a plot on the given axes with accessible styling."""
    vars_map = spec.variables
    x = vars_map.get("x")
    y = vars_map.get("y")
    hue = vars_map.get("hue")
    col = vars_map.get("col")

    # Prepare data for seaborn (convert to pandas for compatibility)
    pdf = df.to_pandas()

    # Set accessible style
    sns.set_theme(style="whitegrid", context="notebook", palette=OKABE_ITO_PALETTE)

    # Configure accessible defaults
    plt.rcParams.update({
        "axes.facecolor": "white",
        "figure.facecolor": "white",
        "axes.edgecolor": "#374151",
        "grid.color": "#E5E7EB",
        "grid.linewidth": 0.8,
        "axes.labelcolor": "#111827",
        "xtick.color": "#111827",
        "ytick.color": "#111827",
        "text.color": "#111827",
    })

    if spec.plot_type == PlotType.HISTOGRAM:
        if x:
            sns.histplot(data=pdf, x=x, hue=hue, ax=ax, bins=spec.transform.get("bins", 30),
                        element="step", stat="density", common_norm=False)

    elif spec.plot_type == PlotType.ECDF:
        if x:
            sns.ecdfplot(data=pdf, x=x, hue=hue, ax=ax, linewidth=2)

    elif spec.plot_type == PlotType.BOXPLOT:
        if x and y:
            # Horizontal boxplot for better label readability
            order = spec.category_order.get(x) if x in spec.category_order else None
            sns.boxplot(data=pdf, y=x, x=y, hue=hue, ax=ax, orient="h", order=order,
                       palette=OKABE_ITO_PALETTE, width=0.6,
                       showfliers=True, flierprops={"marker": "o", "markersize": 3, "alpha": 0.5})
            ax.set_xlabel(spec.labels.get("xlabel", y))
            ax.set_ylabel(spec.labels.get("ylabel", x))

    elif spec.plot_type == PlotType.RAINCLOUD:
        if x and y:
            # Raincloud = boxplot + violin + strip
            order = spec.category_order.get(x) if x in spec.category_order else None
            # Violin
            sns.violinplot(data=pdf, y=x, x=y, hue=hue, ax=ax, orient="h", order=order,
                          palette=OKABE_ITO_PALETTE, inner=None, alpha=0.3, linewidth=0)
            # Boxplot
            sns.boxplot(data=pdf, y=x, x=y, hue=hue, ax=ax, orient="h", order=order,
                       palette=OKABE_ITO_PALETTE, width=0.2, showfliers=False,
                       boxprops={"zorder": 3}, whiskerprops={"zorder": 3},
                       capprops={"zorder": 3}, medianprops={"zorder": 3, "color": "white", "linewidth": 2})
            # Strip
            sns.stripplot(data=pdf, y=x, x=y, hue=hue, ax=ax, orient="h", order=order,
                         palette=OKABE_ITO_PALETTE, size=2, alpha=0.4, jitter=0.2, zorder=2)
            # Remove duplicate legend
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(handles[:len(handles)//2] if hue else handles, labels[:len(labels)//2] if hue else labels)

    elif spec.plot_type == PlotType.STRIP_PLOT:
        if x and y:
            order = spec.category_order.get(x) if x in spec.category_order else None
            sns.stripplot(data=pdf, y=x, x=y, hue=hue, ax=ax, orient="h", order=order,
                         palette=OKABE_ITO_PALETTE, size=3, alpha=0.6, jitter=0.2)
            # Add mean/median markers
            if hue:
                for i, h in enumerate(pdf[hue].unique() if hue in pdf.columns else []):
                    subset = pdf[pdf[hue] == h] if hue in pdf.columns else pdf
                    if len(subset) > 0:
                        mean_val = subset[y].mean()
                        ax.plot(mean_val, i, "D", color=OKABE_ITO_PALETTE[i % len(OKABE_ITO_PALETTE)], markersize=8, markeredgecolor="white", zorder=5)
            else:
                mean_val = pdf[y].mean()
                ax.plot(mean_val, 0, "D", color=OKABE_ITO_PALETTE[0], markersize=10, markeredgecolor="white", zorder=5)

    elif spec.plot_type == PlotType.SCATTERPLOT:
        if x and y:
            sns.scatterplot(data=pdf, x=x, y=y, hue=hue, ax=ax, alpha=0.6, s=30,
                           palette=OKABE_ITO_PALETTE, edgecolor="white", linewidth=0.5)
            # Add trend line if no hue
            if not hue and len(pdf) > 2:
                from scipy import stats
                slope, intercept, _, _, _ = stats.linregress(pdf[x].dropna(), pdf[y].dropna())
                x_range = np.linspace(pdf[x].min(), pdf[x].max(), 100)
                ax.plot(x_range, intercept + slope * x_range, color=NEUTRAL_GRAY, linestyle="--", linewidth=2, alpha=0.8, label=f"Trend (r={slope:.2f})")
                ax.legend()

    elif spec.plot_type == PlotType.COUNT_CHART:
        if x:
            order = spec.category_order.get(x) if x in spec.category_order else None
            sns.countplot(data=pdf, y=x, hue=hue, ax=ax, orient="h", order=order,
                         palette=OKABE_ITO_PALETTE)
            # Add count labels
            for container in ax.containers:
                ax.bar_label(container, fmt="%d", padding=3, fontsize=9)

    elif spec.plot_type == PlotType.CORRELATION_HEATMAP:
        numeric_cols = pdf.select_dtypes(include=[np.number]).columns.tolist()
        if numeric_cols:
            corr = pdf[numeric_cols].corr()
            mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
            sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="vlag",
                       center=0, vmin=-1, vmax=1, ax=ax, cbar_kws={"label": "Correlation"},
                       square=True, linewidths=0.5)

    elif spec.plot_type == PlotType.MISSINGNESS_MATRIX:
        missing = pdf.isnull().astype(int)
        sns.heatmap(missing, cbar=False, cmap=["white", "#DC2626"], ax=ax,
                   yticklabels=False, xticklabels=True)
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

            colors = [OKABE_ITO_PALETTE[i % len(OKABE_ITO_PALETTE)] for i in positions]

            ax.errorbar(points, positions,
                       xerr=[np.array(points) - np.array(lowers), np.array(uppers) - np.array(points)],
                       fmt="o", capsize=5, color=colors[0], ecolor=colors[0], markersize=8)
            ax.set_yticks(positions)
            ax.set_yticklabels(labels)
            ax.axvline(0, color=NEUTRAL_GRAY, linestyle="--", alpha=0.5)
            ax.set_xlabel("Estimate with 95% CI")

    elif spec.plot_type == PlotType.PAIRED_SLOPE:
        if x and y:
            # Slope graph for paired data
            # Pivot to wide if needed
            pair_col = vars_map.get("pair_id")
            if pair_col and pair_col in pdf.columns:
                wide = pdf.pivot_table(index=pair_col, columns=x, values=y).reset_index()
                if wide.shape[1] >= 3:
                    occ_cols = [c for c in wide.columns if c != pair_col]
                    if len(occ_cols) >= 2:
                        for _, row in wide.iterrows():
                            ax.plot([0, 1], [row[occ_cols[0]], row[occ_cols[1]]],
                                   color=OKABE_ITO_PALETTE[0], alpha=0.3, linewidth=0.8)
                        # Group means
                        ax.plot([0, 1], [wide[occ_cols[0]].mean(), wide[occ_cols[1]].mean()],
                               color=OKABE_ITO_PALETTE[1], linewidth=3, marker="o", markersize=8, markeredgecolor="white")
                        ax.set_xticks([0, 1])
                        ax.set_xticklabels(occ_cols)
                        ax.set_ylabel(y)

    # Apply labels
    if spec.labels.get("title"):
        ax.set_title(spec.labels["title"], fontsize=14, fontweight="bold", pad=15)
    if spec.labels.get("xlabel") and not ax.get_xlabel():
        ax.set_xlabel(spec.labels["xlabel"], fontsize=12)
    if spec.labels.get("ylabel") and not ax.get_ylabel():
        ax.set_ylabel(spec.labels["ylabel"], fontsize=12)

    # Add sample size annotation
    n = len(pdf)
    ax.annotate(f"n = {n:,}", xy=(0.99, 0.01), xycoords="axes fraction",
               ha="right", va="bottom", fontsize=9, color=NEUTRAL_GRAY,
               bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=NEUTRAL_GRAY, alpha=0.8))

    # Apply category limits
    if hue and hue in pdf.columns:
        unique_hue = pdf[hue].nunique()
        if unique_hue > spec.max_categories:
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
            # Filter out None/null values
            cats = [c for c in cats if c is not None]
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
    discrete = [c for c, r in column_roles.items() if r == "discrete"]
    ordinal = [c for c, r in column_roles.items() if r == "ordinal"]
    categorical = [c for c, r in column_roles.items() if r == "nominal"]
    binary = [c for c, r in column_roles.items() if r == "binary"]

    all_numeric = continuous + discrete + ordinal
    all_categorical = categorical + ordinal + binary

    # Univariate continuous
    for col in all_numeric[:5]:
        specs.append(create_plot_spec(
            PlotType.HISTOGRAM, {"x": col}, profile_result,
            max_points=5000,
        ))
        specs.append(create_plot_spec(
            PlotType.ECDF, {"x": col}, profile_result,
            max_points=5000,
        ))

    # Numeric by categorical (raincloud/strip)
    for cat in all_categorical[:3]:
        for cont in all_numeric[:3]:
            specs.append(create_plot_spec(
                PlotType.RAINCLOUD, {"x": cat, "y": cont}, profile_result,
            ))

    # Scatterplots
    for i, x in enumerate(all_numeric[:4]):
        for y in all_numeric[i+1:4]:
            specs.append(create_plot_spec(
                PlotType.SCATTERPLOT, {"x": x, "y": y}, profile_result,
            ))

    # Categorical counts
    for cat in all_categorical[:5]:
        specs.append(create_plot_spec(
            PlotType.COUNT_CHART, {"x": cat}, profile_result,
        ))

    # Correlation heatmap
    if len(all_numeric) >= 2:
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
