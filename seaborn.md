# Seaborn Ecosystem: Analytical Usage Guide

**Seaborn is a statistical visualization layer built on Matplotlib, with close integration into the pandas-based analysis workflow—not simply a collection of attractive chart templates.** Effective usage requires understanding data structure, implicit statistical operations, semantic mappings, figure ownership, and the responsibilities that remain with other libraries. [seaborn.pydata](https://seaborn.pydata.org/introduction.html)

**Version baseline:** Seaborn 0.13.2. This is a version-scoped guide, not a guarantee that every future release will retain the same defaults. [github](https://github.com/mwaskom/seaborn/releases)

**Audience:** Data analysts and Python practitioners building exploratory analyses, recurring reports, and reproducible visualization workflows.

**Scope:** The public plotting ecosystem: dependencies and integration boundaries; conventional function APIs; figure and grid APIs; the objects grammar; statistical interpretation; themes and palettes; utility functions; production engineering; performance; migration; and export. “Full ecosystem” does not mean every parameter combination, private implementation detail, or third-party extension.

**Examples:** Recipes use real datasets available through Seaborn's example-data repository. They illustrate workflows rather than report new empirical findings. First-time dataset loading normally requires internet access. Examples build on the shared setup unless stated otherwise; not every block is an independent program.[Dataset API][datasets]

## Contents

- [Architecture and responsibilities](#architecture-and-responsibilities)
- [Installation and environment](#installation-and-environment)
- [Shared example setup](#shared-example-setup)
- [Data contracts and reshaping](#data-contracts-and-reshaping)
- [Three plotting interfaces](#three-plotting-interfaces)
- [Semantic mappings](#semantic-mappings)
- [Plot-family selection](#plot-family-selection)
- [Relational analysis](#relational-analysis)
- [Distribution analysis](#distribution-analysis)
- [Categorical analysis](#categorical-analysis)
- [Estimation and uncertainty](#estimation-and-uncertainty)
- [Regression and diagnostics](#regression-and-diagnostics)
- [Matrix visualization](#matrix-visualization)
- [Structured multi-plot grids](#structured-multi-plot-grids)
- [The objects grammar](#the-objects-grammar)
- [Transformations and limits](#transformations-and-limits)
- [Themes and configuration](#themes-and-configuration)
- [Color as analytical encoding](#color-as-analytical-encoding)
- [Utilities and customization](#utilities-and-customization)
- [Performance and scale](#performance-and-scale)
- [Integration boundaries](#integration-boundaries)
- [Reusable production functions](#reusable-production-functions)
- [Export and reproducibility](#export-and-reproducibility)
- [Migration and compatibility](#migration-and-compatibility)
- [Failure modes](#failure-modes)
- [End-to-end workflow](#end-to-end-workflow)
- [Analytical review checklist](#analytical-review-checklist)

## Architecture and Responsibilities

Seaborn maps dataset variables to visual roles, optionally performs statistical transformations, and arranges the result into one or more panels. Matplotlib supplies the underlying figures, axes, artists, rendering backends, and export facilities. [seaborn.pydata](https://seaborn.pydata.org/introduction.html)

A conceptual pipeline is:

```text
Source data
    -> Validation and reshaping
    -> Variable-to-visual-role mappings
    -> Grouping and statistical transformations
    -> Marks, scales, and subplot structure
    -> Matplotlib rendering
    -> Display or export
```

This is a conceptual model, not a guarantee about the execution order of every internal operation.

| Component | Main responsibility | Relationship to Seaborn |
|---|---|---|
| Seaborn | Statistical graphics, semantic mappings, faceting, themes | Dataset-oriented visualization layer. [seaborn.pydata](https://seaborn.pydata.org/introduction.html) |
| pandas | DataFrames, grouping, reshaping, validation | Common input and preparation layer.[Data tutorial][data] |
| NumPy | Arrays and numerical operations | Required dependency and array-oriented foundation.[Installation][install] |
| Matplotlib | Rendering, axes, artists, annotations, backends, export | Rendering and detailed customization layer. [seaborn.pydata](https://seaborn.pydata.org/introduction.html) |
| SciPy | Scientific statistics and clustering | Optional functionality, including hierarchical clustering.[Installation][install] |
| statsmodels | Statistical modeling | Supports advanced regression options and separate quantitative model analysis.[Regression tutorial][regression] |
| fastcluster | Accelerated hierarchical clustering | Optional acceleration for suitable clustering workloads.[Installation][install] |
| Jupyter/IPython | Interactive exploration and rich display | Common execution and display environment. [seaborn.pydata](https://seaborn.pydata.org/introduction.html) |

**Architectural recommendation:** Keep business definitions, data validation, statistical inference, and rendering as separate responsibilities. A chart should visualize an analytical contract, not silently define it.

## Installation and Environment

NumPy, pandas, and Matplotlib are mandatory dependencies. The `stats` extra installs optional statistical dependencies.[Installation][install]

```bash
python -m pip install "seaborn[stats]==0.13.2"
```

For notebook work, install a notebook environment separately:

```bash
python -m pip install jupyterlab
```

Pin the entire resolved environment for production work rather than assuming that pinning Seaborn alone freezes all behavior. Defaults and artist implementations can change across releases and dependency versions.[Release notes][releases][FAQ][faq]

### Record Package Versions

```python
from importlib.metadata import version
from pathlib import Path
import json
import platform

packages = [
    "seaborn", "matplotlib", "pandas",
    "numpy", "scipy", "statsmodels",
]

environment = {
    "python": platform.python_version(),
    "packages": {name: version(name) for name in packages},
}

Path("environment.json").write_text(
    json.dumps(environment, indent=2),
    encoding="utf-8",
)
```

This recipe assumes every listed package is installed. For a full environment lock, use the dependency-locking workflow appropriate to the project.

## Shared Example Setup

The examples use the real `penguins`, `tips`, and `fmri` example datasets. These are ordinary pandas DataFrames, not special plotting objects. [seaborn.pydata](https://seaborn.pydata.org/introduction.html)

```python
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import seaborn as sns
import seaborn.objects as so

sns.set_theme(style="whitegrid", context="notebook")

penguins = sns.load_dataset("penguins")
tips = sns.load_dataset("tips")
fmri = sns.load_dataset("fmri")

measurements = [
    "bill_length_mm",
    "bill_depth_mm",
    "flipper_length_mm",
    "body_mass_g",
]

species_order = ["Adelie", "Chinstrap", "Gentoo"]
day_order = ["Thur", "Fri", "Sat", "Sun"]

plot_data = penguins.dropna(
    subset=["species", *measurements]
).copy()

plot_data["species"] = pd.Categorical(
    plot_data["species"],
    categories=species_order,
    ordered=True,
)

species_palette = dict(zip(
    species_order,
    sns.color_palette(
        "colorblind", len(species_order)
    ).as_hex(),
))

output_dir = Path("figures")
output_dir.mkdir(exist_ok=True)
```

The choice to remove missing measurements is local to these examples; it is not a general missing-data policy. Examples that additionally use `sex` should consider its missingness separately.

## Data Contracts and Reshaping

Seaborn accepts long-form data, wide-form data, vectors, arrays, and mappings. Long-form data usually makes variable assignment, grouping, and faceting most explicit.[Data tutorial][data]

| Representation | Structure | Suitable usage | Main analytical risk |
|---|---|---|---|
| Long-form | Variables in columns, observations in rows | Semantics, grouping, faceting | Incorrect observational grain |
| Wide-form | Measured series in separate columns | Quick comparisons | Implicit interpretation of columns and index |
| Matrix | Rows and columns identify cells | Heatmaps and clustering | Incomparable units or missing combinations |
| Vectors | Individual arrays or Series | Small focused plots | Lost provenance or alignment mistakes |
| Mapping | Dictionary-like collections | Programmatic lightweight inputs | Inconsistent lengths or unclear metadata |

These representations have distinct interpretation rules; equivalent-looking containers need not imply equivalent semantic assignments.[Data tutorial][data]

### Define the Observational Unit

Before plotting, specify:

- What one row represents.
- Whether the same entity occurs repeatedly.
- Whether values are raw measurements, aggregates, rates, or predictions.
- Which variables identify sampling units.
- Which missing values are structural.
- Whether an absent category is genuinely zero or merely unobserved.
- Whether numeric identifiers have meaningful numeric distances.

These are analytical design questions. Seaborn cannot infer their substantive answers from column names.

### Validate the Schema

```python
required = {"species", *measurements}
missing_columns = required - set(penguins.columns)

if missing_columns:
    raise ValueError(
        f"Missing columns: {sorted(missing_columns)}"
    )

missingness = penguins[list(required)].isna().sum()
```

**Recommendation:** Validate each plotting table against its own required fields. Dropping rows with a missing value anywhere in a large table can remove observations irrelevant to the particular analysis.

### Reshape Explicitly

```python
long_measurements = plot_data.melt(
    id_vars=["species", "island"],
    value_vars=measurements,
    var_name="measurement",
    value_name="value",
)
```

Reshaping turns measurement names into a variable that can be mapped or faceted.[Data tutorial][data] These measurements have different units, so directly comparing their magnitudes requires justification or normalization.

```python
sns.displot(
    data=long_measurements,
    x="value",
    col="measurement",
    hue="species",
    palette=species_palette,
    kind="ecdf",
    facet_kws={"sharex": False},
    height=3,
)
```

Independent x-axes are intentional here because a common numeric scale would conflate millimetres and grams.

## Three Plotting Interfaces

The conventional API distinguishes axes-level and figure-level functions. The objects interface provides a separate declarative grammar.[FAQ][faq][Objects tutorial][objects]

| Interface | Layout ownership | Typical result | Main use |
|---|---|---|---|
| Axes-level | Draws into one supplied or current axes | Matplotlib `Axes` | Custom layouts and mixed chart types.[FAQ][faq] |
| Figure-level | Creates and manages a figure | `FacetGrid`, `PairGrid`, or `JointGrid` | Faceting and structured exploration.[FAQ][faq] |
| Objects | Declares layout or targets an existing container | Plot specification or compiled plot | Layered reusable specifications.[Objects tutorial][objects] |

### Axes-Level Composition

```python
fig, axes = plt.subplots(
    1, 2,
    figsize=(11, 4),
    layout="constrained",
)

sns.scatterplot(
    data=plot_data,
    x="bill_length_mm",
    y="body_mass_g",
    hue="species",
    palette=species_palette,
    ax=axes[0],
)

sns.boxplot(
    data=plot_data,
    x="species",
    y="body_mass_g",
    order=species_order,
    ax=axes [seaborn.pydata](https://seaborn.pydata.org/introduction.html),
)

axes[0].set_title("Relationship")
axes [seaborn.pydata](https://seaborn.pydata.org/introduction.html).set_title("Group distributions")
```

Passing `ax=` is the intended way to place an axes-level function inside a custom Matplotlib layout.[FAQ][faq]

### Figure-Level Composition

```python
g = sns.relplot(
    data=plot_data,
    x="bill_length_mm",
    y="body_mass_g",
    hue="species",
    palette=species_palette,
    col="sex",
    height=4,
    aspect=1.1,
)

g.set_axis_labels("Bill length (mm)", "Body mass (g)")
g.set_titles("Sex: {col_name}")
```

For figure-level functions, `height` and `aspect` usually describe each facet rather than an existing figure.[FAQ][faq] Do not expect `relplot(..., ax=ax)` or `catplot(..., ax=ax)` to behave like axes-level functions.[FAQ][faq]

## Semantic Mappings

A semantic mapping assigns a data variable to a visual role rather than assigning one constant appearance to every observation.[Relational tutorial][relational]

| Role | Scatterplot | Lineplot |
|---|---|---|
| `hue` | Marker color | Line color |
| `size` | Marker area | Line width |
| `style` | Marker shape | Dashes and/or markers |
| `row`, `col` | Separate panels | Separate panels |
| `units` | Not the usual scatterplot grouping mechanism | Distinct unit trajectories without individual legend entries |

The relational functions document these semantics and their type-dependent behavior.[Relational tutorial][relational]

### Mapping Versus Setting

```python
sns.scatterplot(
    data=plot_data,
    x="bill_length_mm",
    y="body_mass_g",
    hue="species",   # Data mapping
    alpha=0.7,       # Constant setting
    s=45,            # Constant marker area
)
```

`hue="species"` communicates data through color; `color="navy"` sets a fixed color.[Relational tutorial][relational]

Numeric hue generally produces a quantitative mapping, while categorical hue produces distinct category colors. The relational `style` semantic remains categorical even for numeric values.[Relational tutorial][relational][Lineplot API][lineplot]

**Recommendations:**

- Convert numeric identifiers to categories when distances are meaningless.
- Use stable palette dictionaries across reports.
- Reuse numeric normalizations across comparable views.
- Avoid assigning too many unrelated variables to one chart.
- Use redundant color and shape when accessibility warrants it.

Color and shape redundancy is supported by the relational interface and can improve interpretation when colors are difficult to distinguish.[Relational tutorial][relational]

## Plot-Family Selection

The public API organizes functions around relational, distributional, categorical, regression, matrix, and multi-plot use cases.[API reference][api]

| Analytical question | Main tools | Inspect carefully |
|---|---|---|
| Relationship between numeric variables | `scatterplot`, `relplot` | Overlap, subgroups, nonlinear patterns |
| Change along an ordered dimension | `lineplot`, `relplot(kind="line")` | Sorting, units, aggregation |
| Distribution | `histplot`, `kdeplot`, `ecdfplot`, `rugplot`, `displot` | Binning, smoothing, normalization |
| Group differences | `stripplot`, `swarmplot`, `boxplot`, `violinplot`, `boxenplot`, `pointplot`, `barplot`, `countplot`, `catplot` | Distribution versus estimate versus frequency |
| Fitted trend | `regplot`, `lmplot`, `residplot` | Model assumptions and diagnostics |
| Rectangular values | `heatmap` | Units, missing cells, color limits |
| Similar profiles | `clustermap` | Preprocessing, metric, linkage |
| Pairwise relationships | `pairplot`, `PairGrid` | Variable selection and visual overload |
| Conditional relationships | `FacetGrid` and figure-level wrappers | Consistent mappings and statistics |
| Joint and marginal structure | `jointplot`, `JointGrid` | Compatible representations |

These are the documented plotting families; the inspection column is analytical guidance rather than an additional API guarantee.[API reference][api]

## Relational Analysis

### Individual Observations

Scatterplots display observations individually, making them useful before aggregation.[Relational tutorial][relational]

```python
fig, ax = plt.subplots(figsize=(7, 5))

sns.scatterplot(
    data=plot_data,
    x="bill_length_mm",
    y="body_mass_g",
    hue="species",
    style="species",
    palette=species_palette,
    alpha=0.65,
    s=40,
    ax=ax,
)

ax.set(
    xlabel="Bill length (mm)",
    ylabel="Body mass (g)",
    title="Body mass and bill length",
)
```

**Interpretive recommendations:** Inspect subgroups before interpreting pooled patterns; treat transparency as an overlap aid rather than a calibrated density estimate; and use bivariate bins when individual points become unreadable.

Numeric `size` values are normalized into a display-size range rather than used as literal marker areas.[Relational tutorial][relational]

### Default Line Aggregation

With repeated observations at an x-coordinate, `lineplot()` normally estimates the mean and displays a 95% bootstrap confidence interval.[Lineplot API][lineplot]

```python
sns.lineplot(
    data=fmri.query("region == 'frontal'"),
    x="timepoint",
    y="signal",
    hue="event",
    style="event",
    errorbar=("ci", 95),
    n_boot=2000,
    seed=42,
)
```

Adding grouping semantics changes which observations contribute to each estimate.[Relational tutorial][relational] Always ask which rows are being combined at each displayed point.

### Individual Trajectories

```python
fmri_frontal = fmri.query("region == 'frontal'").copy()

sns.lineplot(
    data=fmri_frontal,
    x="timepoint",
    y="signal",
    hue="event",
    units="subject",
    estimator=None,
    errorbar=None,
    alpha=0.25,
    linewidth=0.8,
)
```

`units` separates trajectories without assigning every unit a legend entry.[Lineplot API][lineplot] Displaying trajectories is not itself a repeated-measures model or a cluster-corrected uncertainty procedure.

### Sorting and Time

`lineplot()` sorts by default; `sort=False` preserves observation order within the relevant group.[Lineplot API][lineplot]

For time-oriented analyses, define timestamp uniqueness, resampling frequency, missing periods, interpolation policy, and uncertainty target upstream. A line connecting observations does not establish that interpolation is substantively valid.

## Distribution Analysis

Histograms, KDEs, ECDFs, and rugs represent distributions with different assumptions.[Distribution tutorial][distributions]

### Histogram Statistics

| `stat` | Meaning | Main distinction |
|---|---|---|
| `"count"` | Observations per bin | Depends directly on sample size |
| `"frequency"` | Count divided by bin width | Not automatically a probability density |
| `"probability"` / `"proportion"` | Heights sum to 1 in the normalization scope | Bin probability mass |
| `"percent"` | Heights sum to 100 in the normalization scope | Probability mass on a percentage scale |
| `"density"` | Areas sum to 1 in the normalization scope | Height is not probability |

These statistics and their normalization conventions are documented by `histplot`. [seaborn.pydata](https://seaborn.pydata.org/generated/seaborn.histplot.html?highlight=histogram)

For one unweighted group:

\[
\text{density}_j = \frac{n_j}{n\,\Delta_j}
\]

Here, \(n_j\) is bin count, \(n\) is the normalization count, and \(\Delta_j\) is bin width. Probability is represented by area.[Distribution tutorial][distributions]

### Shape Versus Prevalence

```python
sns.histplot(
    data=plot_data,
    x="body_mass_g",
    hue="species",
    palette=species_palette,
    stat="density",
    common_norm=False,
    common_bins=True,
    element="step",
    fill=False,
    bins=20,
)
```

`common_norm=False` normalizes groups independently, making shape comparisons less dominated by group-size differences.[Distribution tutorial][distributions]

**Trade-off:** Independent normalization suppresses prevalence differences. Show group counts separately when prevalence matters.

### Binning and Discreteness

Histogram appearance can change materially with bin choices; compare several plausible settings before interpreting apparent features.[Distribution tutorial][distributions]

```python
sns.histplot(
    data=tips,
    x="size",
    discrete=True,
    shrink=0.85,
)
```

`discrete=True` chooses bins suitable for discrete observations.[Distribution tutorial][distributions]

### Kernel Density Estimation

```python
sns.kdeplot(
    data=plot_data,
    x="body_mass_g",
    hue="species",
    palette=species_palette,
    common_norm=False,
    bw_adjust=0.8,
    cut=0,
)
```

Bandwidth controls smoothness: too little smoothing can emphasize noise, while too much can hide genuine structure.[Distribution tutorial][distributions] Discrete observations and strong boundary effects can make a smooth KDE misleading.[Distribution tutorial][distributions]

`cut=0` limits the evaluation range but does not correct boundary bias.[Distribution tutorial][distributions] Density can exceed 1 because probability is obtained by integrating over a range.[FAQ][faq]

### Empirical Cumulative Distributions

```python
sns.ecdfplot(
    data=plot_data,
    x="body_mass_g",
    hue="species",
    palette=species_palette,
)
```

An ECDF shows the proportion at or below each value without selecting bins or a smoothing bandwidth.[Distribution tutorial][distributions]

\[
\widehat{F}(x) = \frac{1}{n}\sum_{i=1}^{n}\mathbf{1}(X_i \leq x)
\]

This permits direct percentile and threshold interpretation.[Distribution tutorial][distributions]

```python
sns.ecdfplot(
    data=plot_data,
    x="body_mass_g",
    hue="species",
    complementary=True,
)
```

A complementary ECDF provides an empirical exceedance view.[ECDF API][ecdf] Do not substitute it for a censoring-aware survival-analysis procedure.

### Rugs and Bivariate Views

`rugplot()` marks individual values along an axis and can complement another distribution display.[API reference][api]

```python
fig, ax = plt.subplots(figsize=(7, 4))
sns.histplot(data=tips, x="total_bill", bins=20, ax=ax)
sns.rugplot(data=tips, x="total_bill", height=0.04, ax=ax)
```

For two numeric variables:

```python
sns.histplot(
    data=plot_data,
    x="bill_length_mm",
    y="bill_depth_mm",
    bins=25,
    cbar=True,
)
```

A bivariate histogram bins observations in two dimensions; a bivariate KDE estimates a smooth density.[Distribution tutorial][distributions] KDE contour levels use an iso-proportion convention rather than simply labeling raw density heights.[Distribution tutorial][distributions]

## Categorical Analysis

Categorical tools expose individual observations, distribution summaries, point estimates, or frequencies.[Categorical tutorial][categorical]

| Function | Display | Appropriate interpretation |
|---|---|---|
| `stripplot` | Jittered observations | Raw-data visibility |
| `swarmplot` | Non-overlapping observations | Detailed views of manageable datasets |
| `boxplot` | Quartiles, whiskers, fliers | Compact distribution summary |
| `boxenplot` | Additional tail-oriented quantiles | Distribution detail for larger datasets |
| `violinplot` | KDE-based shape | Smoothed distribution comparison |
| `pointplot` | Estimates and intervals | Group-level central tendency |
| `barplot` | Estimates represented by bars | Aggregated values, not necessarily counts |
| `countplot` | Frequencies or normalized frequencies | Category prevalence |
| `catplot` | Figure-level categorical wrapper | Faceted categorical analysis |

The public API documents all of these categorical functions.[API reference][api]

### Combine Observations and Summaries

```python
fig, ax = plt.subplots(figsize=(8, 5))

sns.boxplot(
    data=tips,
    x="day",
    y="total_bill",
    order=day_order,
    color="0.85",
    showfliers=False,
    ax=ax,
)

sns.stripplot(
    data=tips,
    x="day",
    y="total_bill",
    order=day_order,
    color="0.2",
    jitter=0.15,
    alpha=0.45,
    size=3,
    ax=ax,
)
```

Categorical plots support overlays of individual observations and summaries.[Categorical tutorial][categorical] Here the strip layer retains observations while `showfliers=False` avoids duplicate outlier symbols from the boxplot.

### Mean Is Not Total

```python
sns.barplot(
    data=tips,
    x="day",
    y="total_bill",
    order=day_order,
    estimator="mean",
    errorbar=("ci", 95),
    seed=42,
)
```

`barplot()` defaults to a mean, whereas `countplot()` counts observations.[Categorical tutorial][categorical] State the estimator in the label or title; average value and total value answer different questions.

### Percentage Denominators

```python
sns.countplot(
    data=tips,
    x="day",
    hue="time",
    order=day_order,
    stat="percent",
)
```

An axes-level `countplot` normalizes across the plot, not automatically within every x-category.[Countplot API][countplot]

For within-day percentages:

```python
counts = (
    tips.groupby(["day", "time"], observed=True)
    .size()
    .rename("n")
    .reset_index()
)

counts["percent_within_day"] = (
    counts["n"]
    / counts.groupby("day", observed=True)["n"].transform("sum")
    * 100
)

sns.barplot(
    data=counts,
    x="day",
    y="percent_within_day",
    hue="time",
    order=day_order,
    errorbar=None,
)
```

Do not bootstrap the few aggregate rows as though they represented the original independent observations. Any interval should reflect the sampling process behind the proportions.

### Native Numeric Scales

Categorical functions normally place groups at ordinal positions. `native_scale=True` preserves numeric or datetime positions.[Release notes][v0130]

```python
sns.boxplot(
    data=tips,
    x="size",
    y="total_bill",
    native_scale=True,
)
```

Use native spacing when distances are meaningful; use ordinal spacing for equal-width category comparison.

### Violin Normalization

| Setting | Meaning |
|---|---|
| `density_norm="area"` | Normalize violin areas within the applicable grouping |
| `density_norm="width"` | Equal maximum widths |
| `density_norm="count"` | Width reflects observation count |
| `common_norm=True` | Share normalization across violins |

These settings are explicit in the modern violin API.[Violin API][violin]

A wide violin does not automatically mean greater variance, prevalence, or importance. Its meaning depends on the normalization and local density.

## Estimation and Uncertainty

Seaborn distinguishes intervals describing observation spread from intervals describing uncertainty in an estimator.[Error-bar tutorial][errors]

| Setting | Target | Interpretation |
|---|---|---|
| `errorbar="sd"` | Data spread | One standard deviation around the estimate |
| `errorbar=("pi", 95)` | Data spread | Central 95% percentile interval of observations |
| `errorbar="se"` | Estimation uncertainty | One standard error around the estimate |
| `errorbar=("ci", 95)` | Estimation uncertainty | Bootstrap confidence interval |
| `errorbar=None` | No interval | Uncertainty is not displayed |
| Callable | User-defined | Vector-to-boundaries operation |

The interval construction and parameter meanings are documented in the error-bar tutorial.[Error-bar tutorial][errors]

### Bootstrap Reproducibility

```python
sns.pointplot(
    data=tips,
    x="day",
    y="total_bill",
    order=day_order,
    estimator="median",
    errorbar=("ci", 95),
    n_boot=5000,
    seed=42,
    capsize=0.15,
    linestyles="none",
)
```

Bootstrapping supports estimators such as the median; `seed` controls randomness and `n_boot` controls the number of resamples.[Error-bar tutorial][errors]

**Analytical safeguards:**

- Reproducibility does not establish validity.
- More resamples do not repair biased sampling.
- Narrow intervals need not imply small observation-level variation.
- Interval overlap is not a universal significance test.
- Pointwise intervals are not a simultaneous confidence region.
- Repeated observations require an uncertainty method appropriate to dependence.

### Weighted Estimation

Weighted means and bootstrap confidence intervals were added to the estimation functions in the 0.13.x series.[Release notes][v0131]

```python
sns.barplot(
    data=tips,
    x="day",
    y="total_bill",
    weights="size",
    order=day_order,
    estimator="mean",
    errorbar=("ci", 95),
    seed=42,
)
```

This demonstration weights bills by party size; it changes the estimand and is not a recommendation for a particular business measure.

In this version, weighted estimation restricts the estimator to the mean and the interval method to confidence intervals.[Lineplot API][lineplot][Est API][est] Observation weights do not by themselves implement complex survey-design inference.

### Precomputed Intervals

For intervals calculated externally, use explicit Matplotlib calls or compatible objects-interface variables rather than asking an aggregation function to rediscover the interval from aggregate rows.[Error-bar tutorial][errors][Objects tutorial][objects]

```python
summary = (
    tips.groupby("day", observed=True)["total_bill"]
    .agg(
        estimate="median",
        lower=lambda s: s.quantile(0.25),
        upper=lambda s: s.quantile(0.75),
    )
    .reindex(day_order)
)

positions = np.arange(len(summary))
fig, ax = plt.subplots(figsize=(7, 4))

ax.errorbar(
    positions,
    summary["estimate"],
    yerr=np.vstack([
        summary["estimate"] - summary["lower"],
        summary["upper"] - summary["estimate"],
    ]),
    fmt="o",
    capsize=4,
)

ax.set_xticks(positions, summary.index)
ax.set(
    xlabel="Day",
    ylabel="Total bill",
    title="Median and interquartile range",
)
```

This interval is an interquartile range, not a confidence interval.

## Regression and Diagnostics

Seaborn regression functions are exploratory graphical tools, not a general model-analysis API.[Regression tutorial][regression]

| Tool or option | Purpose | Main caution |
|---|---|---|
| `regplot` | One fitted relationship on an axes | Does not expose `hue` like `lmplot` |
| `lmplot` | Fits across groups and facets | Group-specific fits can differ |
| `residplot` | Residual display | Not a complete diagnostic suite |
| `order=2` or greater | Polynomial fit | Flexibility and extrapolation need review |
| `robust=True` | Robust regression | Requires optional statistical support |
| `logistic=True` | Binary-response trend | Requires a suitable outcome interpretation |
| `lowess=True` | Nonparametric smoother | Does not provide the usual Seaborn confidence band |

These options and their limitations are described in the regression tutorial.[Regression tutorial][regression]

### Inspect Fit and Residuals

```python
fig, axes = plt.subplots(
    1, 2,
    figsize=(11, 4),
    layout="constrained",
)

sns.regplot(
    data=tips,
    x="total_bill",
    y="tip",
    ci=95,
    seed=42,
    scatter_kws={"alpha": 0.45},
    ax=axes[0],
)

sns.residplot(
    data=tips,
    x="total_bill",
    y="tip",
    lowess=True,
    scatter_kws={"alpha": 0.45},
    ax=axes [seaborn.pydata](https://seaborn.pydata.org/introduction.html),
)

axes[0].set_title("Exploratory linear fit")
axes [seaborn.pydata](https://seaborn.pydata.org/introduction.html).set_title("Residual structure")
```

Structured residual patterns can indicate that a simple fitted relationship is inadequate.[Regression tutorial][regression]

### Interval API Exception

`regplot()` and `lmplot()` retain `ci=` rather than adopting the general `errorbar=` interface.[Error-bar tutorial][errors]

A confidence band for the fitted relationship is not a prediction interval for individual future observations.

### Move Inference Upstream

Use a dedicated modeling workflow for coefficients, tests, model formulas, interactions, robust covariance, prediction intervals, validation, and model comparison. Seaborn explicitly directs users toward statsmodels for quantitative regression analysis.[Regression tutorial][regression]

## Matrix Visualization

### Heatmaps

`heatmap()` visualizes a rectangular matrix and can inherit row and column labels from a DataFrame.[Heatmap API][heatmap]

```python
correlations = plot_data[measurements].corr()
mask = np.triu(
    np.ones_like(correlations, dtype=bool),
    k=1,
)

fig, ax = plt.subplots(figsize=(7, 6))

sns.heatmap(
    correlations,
    mask=mask,
    cmap="vlag",
    center=0,
    vmin=-1,
    vmax=1,
    annot=True,
    fmt=".2f",
    square=True,
    cbar_kws={"label": "Pearson correlation"},
    ax=ax,
)
```

Fixed limits preserve a consistent numeric-to-color mapping across comparable matrices.[Heatmap API][heatmap]

**Safeguards:** Inspect missingness and effective sample sizes; avoid treating association as causation; do not assume equal uncertainty across cells; and distinguish an unobserved cell from zero.

Annotation arrays passed through `annot=` are matched by position, not by index labels.[Heatmap API][heatmap]

### Clustered Heatmaps

`clustermap()` adds hierarchical clustering, requires SciPy, and returns a `ClusterGrid`.[Clustermap API][clustermap]

```python
X = plot_data[measurements].copy()
Z = X.sub(X.mean()).div(X.std(ddof=1))
row_colors = plot_data["species"].map(species_palette)

g = sns.clustermap(
    Z,
    method="average",
    metric="euclidean",
    cmap="vlag",
    center=0,
    row_colors=row_colors,
    xticklabels=True,
    yticklabels=False,
    figsize=(9, 9),
)
```

This recipe standardizes columns so that comparisons reflect deviations relative to each measurement's scale rather than raw millimetre-versus-gram magnitudes.

### Clustering Decisions

| Decision | Analytical question |
|---|---|
| Raw or standardized values | Magnitude or relative profile? |
| Euclidean or correlation distance | Absolute differences or profile shape? |
| Row or column clustering | Observations, variables, or both? |
| Precomputed linkage | Must clustering be controlled separately? |
| Metadata color strips | Do clusters align with known groups? |

Seaborn supports configurable metrics and linkage methods, externally computed linkage matrices, and index-aligned metadata colors.[Clustermap API][clustermap]

Important constraints:

- Input used for clustering cannot contain missing values.[Clustermap API][clustermap]
- A display mask does not remove values from clustering.[Clustermap API][clustermap]
- `z_score=0` standardizes rows; `z_score=1` standardizes columns.[Clustermap API][clustermap]
- `standard_scale` performs a different normalization from z-scoring.[Clustermap API][clustermap]
- Use the grid's `savefig()` method to avoid clipping dendrograms.[Clustermap API][clustermap]

## Structured Multi-Plot Grids

| Structure | What varies? | Main purpose |
|---|---|---|
| `FacetGrid` | Data subset | Conditional comparisons |
| `PairGrid` | Coordinate-variable assignment | Multivariate screening |
| `JointGrid` | Joint versus marginal view | Detailed analysis of one pair |

These grid types have separate responsibilities and should not be treated as interchangeable layout containers.[Grid tutorial][grids][Distribution tutorial][distributions]

### High-Level Faceting

```python
g = sns.displot(
    data=plot_data,
    x="body_mass_g",
    hue="species",
    col="sex",
    palette=species_palette,
    kind="ecdf",
    height=4,
)
```

High-level wrappers perform bookkeeping that helps synchronize semantic mappings across facets.[Grid tutorial][grids] Start with `relplot`, `displot`, `catplot`, or `lmplot`, then use a grid directly when customization requires it.

### Custom Facet Functions

```python
def median_reference(data, x, color=None, **kwargs):
    ax = plt.gca()
    ax.axvline(
        data[x].median(),
        color=color,
        linestyle="--",
        linewidth=1.5,
    )

bin_edges = np.histogram_bin_edges(
    tips["total_bill"].dropna(),
    bins=15,
)

g = sns.FacetGrid(
    tips,
    col="time",
    height=3.5,
    sharex=True,
    sharey=True,
)

g.map_dataframe(
    sns.histplot,
    x="total_bill",
    bins=bin_edges,
    color="0.6",
)

g.map_dataframe(
    median_reference,
    x="total_bill",
    color="firebrick",
)
```

Mapped functions must cooperate with the grid's calling conventions and axes management.[Grid tutorial][grids] Common bin edges are explicit here: shared axes alone do not guarantee identical statistics.

### Pairwise Screening

```python
g = sns.pairplot(
    data=plot_data,
    vars=measurements,
    hue="species",
    palette=species_palette,
    corner=True,
    diag_kind="hist",
    plot_kws={"alpha": 0.45, "s": 20},
)
```

`pairplot()` is the convenience interface to `PairGrid`; the latter supports different functions on diagonal, upper, and lower panels.[Grid tutorial][grids]

For \(p\) variables, a full square arrangement contains \(p^2\) panel positions. Select variables intentionally rather than treating a large pair grid as an automatic analysis.

### Joint and Marginal Views

```python
g = sns.JointGrid(
    data=plot_data,
    x="bill_length_mm",
    y="body_mass_g",
    height=6,
)

g.plot_joint(sns.scatterplot, alpha=0.45, s=25)
g.plot_marginals(sns.histplot, bins=20, color="0.5")
```

`JointGrid` allows separate control of joint and marginal representations.[Distribution tutorial][distributions] Check compatibility between a convenience function's `kind` and the semantic mappings requested.

## The Objects Grammar

`seaborn.objects` explicitly separates data mappings, marks, statistics, positional moves, scales, and layout. The 0.13.2 documentation describes it as experimental and incomplete, so production use should be version-scoped.[Objects tutorial][objects]

### Core Specification

```python
plot = (
    so.Plot(
        plot_data,
        x="bill_length_mm",
        y="body_mass_g",
        color="species",
    )
    .add(so.Dots(alpha=0.5))
    .scale(color=species_palette)
    .label(
        x="Bill length (mm)",
        y="Body mass (g)",
        color="Species",
    )
)
```

`Plot` establishes variable assignments, and `.add()` defines layers. [seaborn.pydata](https://seaborn.pydata.org/generated/seaborn.objects.Plot.add.html)

```text
Plot(data, mappings)
    .add(mark, optional_stat, optional_moves)
    .scale(...)
    .facet(...)
    .label(...)
    .layout(...)
```

### Complete Mark Inventory

| Family | Classes | Distinction |
|---|---|---|
| Dots | `Dot`, `Dots` | Point representations with different implementations/defaults |
| Sorted connections | `Line`, `Lines` | Sort along the orientation axis |
| Ordered paths | `Path`, `Paths` | Preserve observation order |
| Segments | `Dash`, `Range` | Short oriented marks or intervals |
| Bars | `Bar`, `Bars` | Baseline-to-value rectangles |
| Filled regions | `Area`, `Band` | Baseline fill or interval fill |
| Text | `Text` | Data-positioned labels |

These are the public mark classes in the version baseline.[API reference][api] Plural classes are optimized alternatives with behavioral differences, not simply aliases.[Objects tutorial][objects]

### Complete Statistical Inventory

| Stat | Operation | Main analytical choice |
|---|---|---|
| `Agg` | Aggregate values within groups | Estimator |
| `Est` | Estimate and interval | Uncertainty definition |
| `Count` | Count observations at grouping values | Group definition rather than automatic numeric binning |
| `Hist` | Bin, count, normalize, accumulate | Bins and normalization scope |
| `KDE` | Univariate density estimation | Bandwidth and boundaries |
| `Perc` | Selected percentiles | Percentile levels |
| `PolyFit` | Polynomial fit and resampling | Polynomial degree |

The API exposes these statistics separately from marks.[API reference][api] A mark does not inherently choose an estimator: a mean can be displayed using bars, dots, or other compatible marks.[Objects tutorial][objects]

### Complete Move Inventory

| Move | Operation | Interpretation |
|---|---|---|
| `Dodge` | Separate and narrow overlapping marks | Group-position adjustment |
| `Jitter` | Random displacement | Overlap reduction, not measured variation |
| `Norm` | Divide by a group-derived reference | Relative normalization |
| `Stack` | Cumulative displacement | Part-to-whole arrangement |
| `Shift` | Fixed displacement | Alignment or offset |

These are the documented positional transformations.[API reference][api]

At most one `Stat` is accepted in a layer, and it precedes any `Move` transformations. [seaborn.pydata](https://seaborn.pydata.org/generated/seaborn.objects.Plot.add.html)

```python
(
    so.Plot(
        tips,
        x="day",
        y="total_bill",
        color="time",
    )
    .add(
        so.Bar(),
        so.Agg("mean"),
        so.Dodge(),
    )
)
```

**Critical difference:** `so.Line()` does not automatically reproduce `sns.lineplot()`'s mean-and-interval calculation. Declare aggregation explicitly.[Objects tutorial][objects][Lineplot API][lineplot]

### Complete Scale Inventory

| Scale | Domain |
|---|---|
| `Nominal` | Categories without numeric magnitude |
| `Continuous` | Numeric values, normalization, transformations |
| `Temporal` | Date/time values |
| `Boolean` | True/false values |

The scale classes provide explicit control over data-to-property mappings.[API reference][api]

```python
(
    so.Plot(
        plot_data,
        x="bill_length_mm",
        y="body_mass_g",
        color="body_mass_g",
    )
    .add(so.Dots())
    .scale(
        color=so.Continuous(
            "crest", norm=(2500, 6500)
        )
    )
)
```

The normalization endpoints are explicit display choices, not a newly reported dataset range.

### Base Classes

The public extension foundations are `Mark`, `Stat`, `Move`, and `Scale`.[API reference][api] Prefer built-in classes and upstream data transformations unless an extension is necessary; custom subclasses create an additional maintenance surface, particularly while the interface remains experimental.[Objects tutorial][objects]

### Mappings Versus Constants

```python
mapped = so.Plot(
    plot_data,
    x="bill_length_mm",
    y="body_mass_g",
    color="species",
).add(so.Dot())

constant = so.Plot(
    plot_data,
    x="bill_length_mm",
    y="body_mass_g",
).add(so.Dot(color="navy"))
```

Properties assigned to the plot or a layer are data mappings; properties supplied directly to a mark are constants.[Objects tutorial][objects]

### Layer-Specific Grouping

```python
(
    so.Plot(tips, x="total_bill", y="tip")
    .add(so.Dots(alpha=0.4), color="time")
    .add(
        so.Line(color="black"),
        so.PolyFit(order=1),
    )
)
```

The dots map `time` to color, while the fit is pooled because that mapping is not global.[Objects tutorial][objects] A globally assigned mapping can be disabled for a layer using the corresponding mapping set to `None`. [seaborn.pydata](https://seaborn.pydata.org/generated/seaborn.objects.Plot.add.html)

**Analytical implication:** Changing a semantic can change statistical grouping, not just appearance.

### Estimates and Intervals

```python
(
    so.Plot(tips, x="day", y="total_bill")
    .scale(x=so.Nominal(order=day_order))
    .add(
        so.Range(),
        so.Est(
            func="mean",
            errorbar=("ci", 95),
            n_boot=2000,
            seed=42,
        ),
    )
    .add(so.Dot(pointsize=8), so.Agg("mean"))
)
```

`Est` calculates compatible interval variables; marks determine their visual representation.[Est API][est]

### Normalization Scope

```python
(
    so.Plot(
        plot_data,
        x="body_mass_g",
        color="species",
    )
    .add(
        so.Bars(alpha=0.35),
        so.Hist(
            stat="density",
            bins=20,
            common_norm=False,
        ),
    )
    .scale(color=species_palette)
)
```

Objects statistics can control common bins, evaluation grids, and normalization across groups or within selected grouping variables.[Hist API][objectshist][KDE API][objectskde]

### Plot Method Inventory

| Method | Responsibility |
|---|---|
| `.add()` | Layer a mark and transformations |
| `.scale()` | Configure mapping, transformation, ticks, formatting |
| `.facet()` | Divide observations into panels |
| `.pair()` | Vary coordinate variables across panels |
| `.layout()` | Configure layout |
| `.label()` | Set labels and titles |
| `.limit()` | Restrict visible coordinate ranges |
| `.share()` | Control axis sharing |
| `.theme()` | Set theme properties |
| `.on()` | Target an existing Matplotlib container |
| `.plot()` | Compile the specification |
| `.show()` | Display the result |
| `.save()` | Compile and export |

These methods form the public plotting workflow.[API reference][api][Objects tutorial][objects]

### Specifications Are Cloned

Plot methods return modified copies rather than mutating the original specification.[Objects tutorial][objects]

```python
base = so.Plot(tips, x="total_bill", y="tip")
points = base.add(so.Dots(alpha=0.5))
fitted = points.add(
    so.Line(color="black"),
    so.PolyFit(),
)
```

Assign or chain the returned specification; calling a method without retaining its result does not update the earlier variable.

### Matplotlib Integration

```python
fig, ax = plt.subplots(figsize=(7, 5))

(
    so.Plot(tips, x="total_bill", y="tip")
    .add(so.Dots(alpha=0.5))
    .on(ax)
    .plot()
)

ax.axhline(0, color="0.4", linewidth=0.8)
```

`.on()` supports integration with Matplotlib axes, figures, and subfigures for more complex compositions.[Objects tutorial][objects]

## Transformations and Limits

Nonlinear scales can affect statistical computation rather than only final visual spacing. In the 0.13 categorical overhaul, statistical operations moved into the relevant transformed scale space.[Release notes][v0130]

For positive measurements:

\[
\text{Arithmetic mean} = \frac{1}{n}\sum_{i=1}^{n}x_i
\]

\[
\text{Geometric mean} = \exp\left(\frac{1}{n}\sum_{i=1}^{n}\log x_i\right)
\]

An arithmetic summary and an exponentiated mean in log space are different quantities. This distinction matters when choosing a transformed aggregation workflow.[Release notes][v0130]

**Recommendations:** Define the target quantity; precompute when necessary; distinguish applying an axes transformation after plotting from aggregating in transformed space; and audit values outside the scale domain.

The 0.13 notes describe dropping observations outside a scale transformation's domain before statistical operations.[Release notes][v0130]

### Limits Are Not Filters

In the objects interface, `.limit()` restricts visibility without excluding the hidden observations from statistical transforms.[Limit API][limit]

```python
visible_window = plot.limit(x=(35, 50))

restricted_data = plot_data.query(
    "35 <= bill_length_mm <= 50"
)
```

Filter upstream to change the analytical population. Set limits to change the viewing window.

## Themes and Configuration

Seaborn themes operate through Matplotlib's rc configuration and can affect plots created directly with Matplotlib. [seaborn.pydata](https://seaborn.pydata.org/introduction.html)

### Global Configuration

```python
sns.set_theme(
    style="whitegrid",
    context="notebook",
    palette="colorblind",
    font_scale=1.05,
    rc={
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 120,
        "savefig.dpi": 300,
    },
)
```

### Local Configuration

```python
with sns.axes_style("ticks"), sns.plotting_context("paper"):
    fig, ax = plt.subplots(figsize=(6, 4))
    sns.boxplot(
        data=tips,
        x="day",
        y="total_bill",
        order=day_order,
        ax=ax,
    )
    sns.despine(ax=ax)
```

Styles and contexts can be applied temporarily through context managers.[Aesthetics tutorial][aesthetics]

### Complete Theme Inventory

| API | Role |
|---|---|
| `set_theme` | Overall theme, context, palette, fonts, rc settings |
| `axes_style`, `set_style` | Retrieve or set general appearance |
| `plotting_context`, `set_context` | Retrieve or set element scaling |
| `set_palette` | Set the color cycle |
| `set_color_codes` | Reinterpret Matplotlib shorthand colors |
| `reset_defaults` | Restore default rc settings |
| `reset_orig` | Restore original rc settings |
| `set` | Compatibility alias; prefer `set_theme` |

These functions form the public theme-related API.[API reference][api]

Objects specifications also support `.theme()` and global objects configuration through `so.Plot.config.theme`.[Objects tutorial][objects]

**Recommendation:** Reusable library functions should avoid changing a caller's global configuration unexpectedly.

## Color as Analytical Encoding

Palette selection should reflect the meaning of the variable.[Palette tutorial][palettes]

| Meaning | Family | Examples |
|---|---|---|
| Unordered groups | Qualitative | `colorblind`, `deep`, `Set2` |
| Increasing magnitude | Sequential | `crest`, `flare`, `mako`, `rocket`, `viridis` |
| Signed deviation around a center | Diverging | `vlag`, `icefire`, custom diverging ramps |

These palette families support different perceptual tasks.[Palette tutorial][palettes] A diverging palette needs a meaningful midpoint; zero is not automatically appropriate for every quantity.

### Complete Palette Inventory

| Function | Purpose |
|---|---|
| `color_palette` | General palette interface |
| `husl_palette` | Perceptually motivated hue variation |
| `hls_palette` | Hue/lightness/saturation palette |
| `cubehelix_palette` | Parameterized sequential palette |
| `dark_palette` | Dark-to-color ramp |
| `light_palette` | Light-to-color ramp |
| `diverging_palette` | Two-sided centered palette |
| `blend_palette` | Interpolate specified colors |
| `xkcd_palette` | Named colors from the xkcd survey |
| `crayon_palette` | Crayola named colors |
| `mpl_palette` | Matplotlib registry palettes |
| `set_palette` | Install a Matplotlib color cycle |

These functions are listed in the public API.[API reference][api]

```python
categorical_colors = sns.color_palette("colorblind", 3)
continuous_map = sns.color_palette("crest", as_cmap=True)
diverging_map = sns.diverging_palette(240, 10, as_cmap=True)
```

A finite color list and a continuous colormap are distinct outputs with different uses.[Palette tutorial][palettes]

### Shared Numeric Normalization

```python
mass_norm = Normalize(vmin=2500, vmax=6500)

sns.scatterplot(
    data=plot_data,
    x="bill_length_mm",
    y="bill_depth_mm",
    hue="body_mass_g",
    hue_norm=mass_norm,
    palette="crest",
)
```

Numeric hue normalization controls the value-to-color mapping.[Relational tutorial][relational] Reuse it across comparable charts so that the same color retains the same meaning.

### Palette Widgets

The widget helpers are `choose_colorbrewer_palette`, `choose_cubehelix_palette`, `choose_light_palette`, `choose_dark_palette`, and `choose_diverging_palette`.[API reference][api]

Use widgets for design-time exploration, then preserve the final palette definition in code. An unrecorded interactive choice is not a reproducible specification.

## Utilities and Customization

| Utility | Role |
|---|---|
| `despine` | Remove selected spines |
| `move_legend` | Recreate a legend at a new location |
| `saturate` | Increase saturation to its full value |
| `desaturate` | Reduce saturation |
| `set_hls_values` | Change color channels |
| `load_dataset` | Load example datasets |
| `get_dataset_names` | Discover available example datasets |
| `get_data_home` | Find the cache location |

These utilities are part of Seaborn's public API.[API reference][api]

```python
ax = sns.scatterplot(
    data=plot_data,
    x="bill_length_mm",
    y="body_mass_g",
    hue="species",
    palette=species_palette,
)

sns.move_legend(
    ax,
    "upper left",
    bbox_to_anchor=(1.02, 1),
    frameon=False,
)

sns.despine(ax=ax)
```

### Customization Hierarchy

Prefer, in order:

1. Explicit Seaborn parameters.
2. Supported Matplotlib keyword arguments forwarded by the function.
3. Matplotlib axes and figure methods.
4. Direct artist manipulation only when necessary.

This follows the documented integration model.[FAQ][faq] Artist types and positions in collections such as `ax.lines` or `ax.patches` are not stable implementation contracts.[FAQ][faq]

**Recommendation:** Avoid code that assumes an undocumented artist index always represents the same statistical element.

## Performance and Scale

Bootstrapping, KDE, regression, clustering, and dense rendering can each become a bottleneck.[Error-bar tutorial][errors][Distribution tutorial][distributions][Regression tutorial][regression][Clustermap API][clustermap]

| Bottleneck | Mechanism | Suggested response |
|---|---|---|
| Bootstrap intervals | Repeated estimation | Disable while iterating, restore justified intervals |
| KDE | Evaluation over a grid | Reduce resolution or choose histograms/ECDFs |
| Swarms | Non-overlap positioning | Use jitter or distribution summaries |
| Pair grids | Quadratic panel count | Select variables, use a corner grid |
| Dense vector exports | Many rendered elements | Rasterize dense layers or use raster output |
| Hierarchical clustering | Distance/linkage work | Precompute or evaluate suitable acceleration |

Swarm plots are particularly suited to manageable datasets, and the installation guide identifies fastcluster as an optional clustering accelerator.[Categorical tutorial][categorical][Installation][install]

### Aggregate Upstream

```python
summary = (
    fmri.groupby(
        ["timepoint", "event", "region"],
        observed=True,
        as_index=False,
    )
    .agg(mean_signal=("signal", "mean"))
)

sns.lineplot(
    data=summary,
    x="timepoint",
    y="mean_signal",
    hue="event",
    style="region",
    estimator=None,
    errorbar=None,
)
```

This separates the aggregation contract from rendering. Preserve raw data or appropriate uncertainty estimates: a table of means alone does not reconstruct the original sampling distribution.

### Sampling Policy

If rendering requires sampling, preserve rare groups, record the rule and seed, label sampled displays, and assess the loss of tails or local structure. Do not present sampled counts as full-population counts.

These are workflow safeguards rather than automatic Seaborn protections.

## Integration Boundaries

### Alternative DataFrames

Version 0.13 introduced provisional support through the dataframe exchange protocol while still converting the data to pandas internally.[Release notes][v0130]

Accepting a non-pandas DataFrame does not imply lazy, distributed, or zero-copy visualization. Materialize a deliberate plotting table after necessary filtering and aggregation.

### Notebooks and Applications

Seaborn inherits Matplotlib's display and backend model, including notebooks, GUI applications, and raster/vector export. [seaborn.pydata](https://seaborn.pydata.org/introduction.html)

For an application, distinguish static statistical rendering from browser-native interaction requirements. Linked selection, hover inspection, and dashboard state need an explicit application design rather than an assumption about Seaborn's plotting API.

### Modeling Workflows

Use plotting tables to visualize observed versus fitted values, residuals, calibration summaries, feature distributions, and evaluation metrics. Keep model fitting, train/test definitions, leakage controls, and metric calculations outside the charting function.

### Third-Party Extensions

Third-party annotation, labeling, or report-integration packages are not part of Seaborn's core public API. Evaluate compatibility and statistical behavior separately; an extension that draws significance brackets does not by itself establish a valid testing design.

## Reusable Production Functions

A production plotting function should accept data, validate inputs, expose analytical choices, accept an optional axes, return a useful object, and avoid hidden global side effects.

```python
def plot_measurement_relationship(
    data,
    *,
    x,
    y,
    hue,
    palette,
    ax=None,
    title=None,
):
    required = {x, y, hue}
    missing = required - set(data.columns)

    if missing:
        raise ValueError(
            f"Missing columns: {sorted(missing)}"
        )

    clean = data.dropna(subset=[x, y, hue])

    if ax is None:
        _, ax = plt.subplots(
            figsize=(7, 5),
            layout="constrained",
        )

    sns.scatterplot(
        data=clean,
        x=x,
        y=y,
        hue=hue,
        palette=palette,
        alpha=0.6,
        s=35,
        ax=ax,
    )

    if title is not None:
        ax.set_title(title)

    return ax
```

This follows the axes-level composition model, leaving outer layout and export to the caller.[FAQ][faq]

### Separate Three Contracts

| Contract | Suggested contents |
|---|---|
| Data | Grain, schema, population, units, missingness |
| Statistics | Grouping, estimator, weights, interval, transformations |
| Visuals | Palette, order, scales, labels, dimensions, output |

This separation makes it easier to review whether a change is analytical, statistical, or presentational.

### Testing Strategy

Recommended tests include schema checks; explicit aggregate-table checks; expected axis labels and category order; successful noninteractive rendering; file creation; and selected image-regression tests under a controlled environment.

Treat pixel comparisons as environment-sensitive regression checks rather than proof that the underlying analytical definition is correct.

## Export and Reproducibility

Seaborn supports Matplotlib's raster and vector export workflows. [seaborn.pydata](https://seaborn.pydata.org/introduction.html)

### Axes-Level Export

```python
fig, ax = plt.subplots(
    figsize=(7, 5),
    layout="constrained",
)

sns.scatterplot(
    data=plot_data,
    x="bill_length_mm",
    y="body_mass_g",
    hue="species",
    palette=species_palette,
    ax=ax,
)

fig.savefig(
    output_dir / "penguin_relationship.png",
    dpi=300,
    bbox_inches="tight",
)

fig.savefig(
    output_dir / "penguin_relationship.svg",
    bbox_inches="tight",
)

plt.close(fig)
```

### Grid Export

```python
g = sns.relplot(
    data=plot_data,
    x="bill_length_mm",
    y="body_mass_g",
    hue="species",
    col="sex",
    palette=species_palette,
)

g.savefig(
    output_dir / "penguin_facets.png",
    dpi=300,
)

plt.close(g.figure)
```

### Objects Export

```python
plot.save(
    output_dir / "objects_relationship.svg",
    bbox_inches="tight",
)
```

`Plot.save()` compiles and forwards export options to Matplotlib's figure-saving machinery.[Save API][objectsave]

### Preserve the Analytical Artifact

Store the plotting table or reproducible extraction, provenance, population filters, missingness rules, grouping, category order, weights, estimator, interval, seed, transformations, normalization, package versions, dimensions, and generation code.

A polished image alone does not document the process that produced it.

## Migration and Compatibility

Older tutorials often use deprecated or changed interfaces. [github](https://github.com/mwaskom/seaborn/releases)

| Older pattern | Modern direction |
|---|---|
| `distplot(...)` | `histplot`, `kdeplot`, or `displot`.[API reference][api] |
| `ci=` in aggregation plots | `errorbar=`; regression functions remain an exception.[Error-bar tutorial][errors] |
| Categorical `palette=` without hue | Use an explicit mapping, including redundant hue when appropriate.[Release notes][v0130] |
| Violin `bw=` | `bw_method` and `bw_adjust`.[Release notes][v0130] |
| Violin `scale=` | `density_norm`.[Release notes][v0130] |
| Violin `scale_hue=` | Review `common_norm` and normalization scope.[Release notes][v0130] |
| Barplot `errcolor` / `errwidth` | `err_kws`.[Release notes][v0130] |
| Pointplot `join` / `scale` / `errwidth` | Line, marker, and error-style options.[Release notes][v0130] |
| Numeric categories always ordinal | `native_scale=True` when meaningful.[Release notes][v0130] |

### Explicit Per-Category Colors

```python
sns.boxplot(
    data=tips,
    x="day",
    y="total_bill",
    hue="day",
    order=day_order,
    hue_order=day_order,
    palette="colorblind",
    legend=False,
)
```

This uses an explicit redundant mapping rather than relying on old implicit coloring behavior.[Release notes][v0130]

**Documentation caution:** For behavior changed by a release, prefer the matching API reference and release notes over unversioned tutorials or older explanatory text.[Release notes][v0130]

## Failure Modes

| Failure | Consequence | Better practice |
|---|---|---|
| Mean bars interpreted as counts | Estimate and frequency confused.[Categorical tutorial][categorical] | State estimator and units |
| Default line aggregation unnoticed | Observations silently summarized.[Lineplot API][lineplot] | Specify estimator and units |
| Density height interpreted as probability | Wrong quantity interpreted.[Distribution tutorial][distributions] | Interpret area or use ECDF |
| `cut=0` treated as boundary correction | KDE bias overlooked.[Distribution tutorial][distributions] | Audit boundaries or change representation |
| Percent bars assumed within-category | Wrong denominator.[Countplot API][countplot] | Compute denominator explicitly |
| Display limits treated as filters | Statistics still include hidden values.[Limit API][limit] | Filter upstream |
| Nonlinear scale treated as cosmetic | Estimand may change.[Release notes][v0130] | Document transformed computation |
| Automatic color ranges reused without checking | Colors no longer comparable.[Relational tutorial][relational] | Fix normalization |
| Dendrogram treated as proof of natural classes | Algorithm choices mistaken for evidence.[Clustermap API][clustermap] | Evaluate sensitivity |
| Fitted line treated as causal evidence | Exploratory graphics overinterpreted.[Regression tutorial][regression] | Separate description and causal design |
| Aggregate rows bootstrapped as raw data | Sampling process misrepresented | Calculate justified uncertainty upstream |
| Artist indices hard-coded | Fragile customization.[FAQ][faq] | Prefer public controls |

## End-to-End Workflow

This standalone recipe demonstrates input validation, missingness accounting, stable category mappings, multiple analytical views, and export. It does not claim that these plots establish a particular scientific result.

```python
from pathlib import Path
import json

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sns.set_theme(style="whitegrid", context="notebook")

out = Path("analysis_output")
out.mkdir(exist_ok=True)

raw = sns.load_dataset("penguins")
required = ["species", "bill_length_mm", "body_mass_g"]

missing_columns = set(required) - set(raw.columns)
if missing_columns:
    raise ValueError(sorted(missing_columns))

clean = raw.dropna(subset=required).copy()
order = ["Adelie", "Chinstrap", "Gentoo"]
palette = dict(zip(
    order,
    sns.color_palette("colorblind", len(order)).as_hex(),
))

clean["species"] = pd.Categorical(
    clean["species"], categories=order, ordered=True
)

audit = {
    "dataset": "seaborn example penguins",
    "rows_loaded": int(len(raw)),
    "rows_plotted": int(len(clean)),
    "required_columns": required,
    "missing_required": {
        col: int(raw[col].isna().sum())
        for col in required
    },
    "species_order": order,
}

summary = (
    clean.groupby("species", observed=True)
    .agg(
        n=("body_mass_g", "size"),
        mean_mass_g=("body_mass_g", "mean"),
        median_mass_g=("body_mass_g", "median"),
    )
    .reindex(order)
)

clean[required].to_csv(out / "plotting_data.csv", index=False)
summary.to_csv(out / "group_summary.csv")
(out / "audit.json").write_text(
    json.dumps(audit, indent=2), encoding="utf-8"
)

fig, axes = plt.subplots(
    1, 3, figsize=(16, 4.5), layout="constrained"
)

sns.scatterplot(
    data=clean,
    x="bill_length_mm", y="body_mass_g",
    hue="species", style="species",
    hue_order=order, palette=palette,
    alpha=0.6, s=35, ax=axes[0],
)
axes[0].set_title("Individual observations")
axes[0].set_xlabel("Bill length (mm)")
axes[0].set_ylabel("Body mass (g)")

sns.ecdfplot(
    data=clean, x="body_mass_g",
    hue="species", hue_order=order,
    palette=palette, ax=axes [seaborn.pydata](https://seaborn.pydata.org/introduction.html),
)
axes [seaborn.pydata](https://seaborn.pydata.org/introduction.html).set_title("Distribution by species")
axes [seaborn.pydata](https://seaborn.pydata.org/introduction.html).set_xlabel("Body mass (g)")

sns.pointplot(
    data=clean,
    x="species", y="body_mass_g",
    order=order, estimator="mean",
    errorbar=("ci", 95), n_boot=2000, seed=42,
    linestyles="none", capsize=0.15,
    color="0.2", ax=axes [github](https://github.com/mwaskom/seaborn/releases),
)
axes [github](https://github.com/mwaskom/seaborn/releases).set_title("Mean and bootstrap 95% CI")
axes [github](https://github.com/mwaskom/seaborn/releases).set_xlabel("Species")
axes [github](https://github.com/mwaskom/seaborn/releases).set_ylabel("Body mass (g)")

fig.savefig(out / "analytical_overview.png", dpi=300)
fig.savefig(out / "analytical_overview.svg")
plt.close(fig)
```

The three panels intentionally separate observations, distributions, and estimated central tendency. Their supported API behaviors are documented in the relational, distribution, and error-bar guides.[Relational tutorial][relational][Distribution tutorial][distributions][Error-bar tutorial][errors]

**Interpretive boundary:** The bootstrap panel is a default observation-level demonstration. Real inferential use must justify the population, sampling process, and independence assumptions.

## Analytical Review Checklist

### Data

- [ ] The observational unit is explicit.
- [ ] Required columns and units are validated.
- [ ] Population and missingness rules are documented.
- [ ] Repeated entities are identified.
- [ ] Numeric identifiers are classified correctly.
- [ ] Category order is intentional.
- [ ] Provenance and extraction logic are preserved.

### Statistics

- [ ] The estimator answers the intended question.
- [ ] Grouping keys are explicit.
- [ ] Weighting has a defensible interpretation.
- [ ] Interval labels distinguish spread and uncertainty.
- [ ] Dependence and sampling design are considered.
- [ ] Transformations and normalization are documented.
- [ ] Filters and display limits are distinguished.
- [ ] Raw distributions accompany summaries where useful.

### Visual Encoding

- [ ] Palette family matches variable meaning.
- [ ] Comparable views use meaningful shared scales.
- [ ] Numeric color normalization is consistent.
- [ ] Labels contain units and estimators.
- [ ] Legends explain mappings.
- [ ] Faceting does not conceal incompatible statistics.
- [ ] Dense marks remain interpretable.
- [ ] Accessibility does not depend on color alone.

### Engineering

- [ ] The appropriate interface owns the figure.
- [ ] Functions return useful objects.
- [ ] Global changes are controlled.
- [ ] Seeds and versions are recorded.
- [ ] Plotting tables can be reconstructed.
- [ ] Noninteractive rendering is tested.
- [ ] Export size and format match the destination.
- [ ] Figures are closed during batch processing.