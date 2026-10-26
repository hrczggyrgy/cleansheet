# Scientific Statistical Analysis of Tabular Data with Python

## Executive summary

Scientific analysis of tabular data is not a sequence of library calls. It is a chain of claims connecting a study design, estimand, measurement system, data-generating process, statistical model, diagnostics, uncertainty analysis, and reproducible report. Python provides mature components for that chain—especially pandas, NumPy, SciPy, statsmodels, scikit-learn, PyMC, ArviZ, and plotting libraries—but software cannot rescue an unidentified causal effect, a broken sampling design, or an ill-defined outcome.

A defensible workflow has six properties:

- **Question-first:** define the population, unit, outcome, exposure or intervention, estimand, time horizon, and decision criterion before fitting models.
- **Design-aware:** preserve pairing, repeated measures, clusters, sampling weights, censoring, and temporal order.
- **Schema-controlled:** validate types, units, ranges, keys, categories, and missing-value codes before analysis.
- **Estimation-centered:** report effect sizes and uncertainty intervals. The American Statistical Association states that a p-value does not give the probability that a hypothesis is true, does not measure effect size, and should not alone determine scientific conclusions.[cite:23]
- **Stress-tested:** examine assumptions, influential observations, missing-data mechanisms, multiplicity, alternative specifications, and out-of-sample behavior where relevant.
- **Reproducible:** publish executable code, data or a legally shareable substitute, dependencies, random seeds, and execution order. Reproducibility standards emphasize availability of data, models, code, dependencies, instructions, and deterministic handling of randomness.[cite:73]

The main engineering recommendation is to treat the analysis as a versioned pipeline whose inputs are immutable raw tables and whose outputs—validated analytic tables, fitted models, diagnostics, figures, and publication tables—are generated automatically.

## Analytical goals

Tabular analyses usually serve one or more distinct goals. These must not be conflated.

| Goal | Target | Typical evaluation | Principal threat |
|---|---|---|---|
| Description | Features of the observed sample | Accurate summaries and visualization | Measurement errors and misleading aggregation |
| Population inference | Population parameter or contrast | Standard errors, intervals, calibrated tests | Sampling/design violations and misspecification |
| Prediction | Performance on future observations | Out-of-sample loss, discrimination, calibration | Leakage, overfitting, distribution shift |
| Causal inference | Counterfactual contrast under intervention | Identification argument plus sensitivity analysis | Confounding, selection, positivity, interference |

A model can predict well without identifying a causal effect. A causal estimator may deliberately optimize an interpretable treatment contrast rather than prediction. Every report should therefore label its objective rather than using vague language such as “finding relationships.”

## Scientific specification

### Define the estimand

Before inspecting inferential results, write a short analysis specification:

- **Population:** to whom or what should the result generalize?
- **Unit:** person, specimen, device, site, transaction, time point, or another entity.
- **Outcome:** definition, scale, measurement time, and treatment of competing events.
- **Exposure/intervention:** level, timing, reference condition, and assignment process.
- **Estimand:** mean difference, risk difference, risk ratio, odds ratio, rate ratio, marginal effect, conditional coefficient, quantile contrast, survival contrast, or predictive risk.
- **Covariates:** prespecified confounders, precision variables, effect modifiers, and exclusions such as mediators or colliders.
- **Uncertainty:** interval level, clustering level, resampling unit, and multiplicity family.
- **Sensitivity analyses:** plausible assumptions that will be varied.

Observational reporting guidance calls for explicit definitions of outcomes, exposures, predictors, confounders, and effect modifiers, plus an explanation of confounding control.[cite:65][cite:67] The estimand determines both model choice and interpretation. For example, a logistic-regression coefficient estimates a conditional log-odds contrast; it is not automatically a marginal risk difference.

### Separate exploration and confirmation

Exploration discovers structure and defects. Confirmation evaluates prespecified hypotheses or estimands. The same dataset may support both, but the report must distinguish them. Undisclosed iteration makes nominal p-values and confidence intervals too optimistic.

Store the primary specification in a protocol or machine-readable configuration before final analysis. Log deviations and label newly discovered hypotheses as exploratory and in need of independent validation.

### Respect the design

Independence follows from sampling or assignment, not from a dataframe’s row structure. Rows are correlated when they represent repeated observations from one subject, members of a household, samples processed in a batch, students within schools, or nearby measurements in time or space. Ignoring correlation often understates uncertainty.

Choose cluster-robust covariance, generalized estimating equations, mixed-effects models, hierarchical Bayesian models, survey estimators, blocked permutations, or cluster resampling according to the design and estimand. Statsmodels includes linear mixed models and generalized families, although its generalized mixed-model implementation has documented family and random-effect limitations that must be checked.[cite:57][cite:60]

## Python stack

| Layer | Tools | Scientific role |
|---|---|---|
| Storage | Parquet/Arrow, CSV, SQL | Typed and inspectable interchange |
| Tabular operations | pandas; Polars where justified | Cleaning, joins, reshaping, aggregation |
| Numerical work | NumPy | Arrays, linear algebra, random generators |
| Classical statistics | SciPy | Distributions, tests, bootstrap, permutation, Monte Carlo |
| Statistical models | statsmodels, patsy/formulaic | Regression, GLMs, diagnostics, robust covariance |
| Prediction | scikit-learn | Pipelines, validation, metrics, tuning |
| Bayesian models | PyMC, ArviZ | Hierarchical inference and predictive checking |
| Visualization | seaborn, matplotlib, plotnine, Altair | Distribution, effect, and diagnostic graphics |
| Validation | Pandera, Pydantic, Great Expectations | Executable data contracts |
| Reproducibility | Git, uv/conda, containers, DVC, Make/Snakemake | Environment, provenance, workflow control |

Pin package versions for an archived analysis and use stable public APIs. Package choice matters less than documenting versions, validating numerical results, and making transformations deterministic and testable.

## Project architecture

```text
project/
├── README.md
├── pyproject.toml
├── uv.lock
├── configs/
│   └── analysis.yaml
├── data/
│   ├── raw/          # immutable
│   ├── interim/
│   └── processed/
├── src/project_name/
│   ├── io.py
│   ├── validation.py
│   ├── features.py
│   ├── estimands.py
│   ├── models.py
│   └── reporting.py
├── notebooks/
├── tests/
├── scripts/
└── outputs/
    ├── models/
    ├── tables/
    └── figures/
```

Notebooks are useful computational narratives, but hidden state and out-of-order execution are hazards. Guidance for reproducible notebooks recommends modular cells, explanatory text, explicit dependency management, version control, shared data where possible, and clean top-to-bottom execution.[cite:63][cite:71] Put reusable logic in tested modules and use notebooks for orchestration and interpretation.

Record the Git commit, input-data hash, configuration hash, Python/package versions, operating system, random seed, and execution timestamp. Provenance should permit each result to be traced through every transformation to its inputs.[cite:75]

## Ingestion and validation

### Preserve raw evidence

Never overwrite raw files. Record hashes and import them through one reviewed function. CSV is ubiquitous but weakly typed; Parquet better preserves data types and metadata for internal analytical datasets.

```python
from pathlib import Path
import hashlib
import pandas as pd

RAW = Path("data/raw/study.csv")
sha256 = hashlib.sha256(RAW.read_bytes()).hexdigest()

df = pd.read_csv(
    RAW,
    dtype={"subject_id": "string", "site": "category"},
    parse_dates=["visit_date"],
    na_values=["", "NA", "N/A", ".", "-999"],
    keep_default_na=True,
)
```

Identifiers should not be inferred as numeric: leading zeros, very large integers, and check digits can be damaged. Parse dates with explicit timezone and locale assumptions. Retain original text when parsing can fail, and harmonize units before concatenation.

### Enforce a contract

Validation should fail loudly instead of silently removing records. Assert:

- Required columns, types, and nullability.
- Unique keys and expected table cardinality.
- Physical and logical ranges.
- Permitted category levels and reference coding.
- Cross-field rules, such as discharge after admission.
- Referential integrity across tables.
- Expected row counts and join expansion.

```python
import pandera.pandas as pa
from pandera import Check, Column, DataFrameSchema

schema = DataFrameSchema(
    {
        "subject_id": Column(str, nullable=False),
        "age": Column(float, Check.in_range(0, 120), nullable=True),
        "group": Column(str, Check.isin(["control", "treated"])),
        "outcome": Column(float, nullable=True),
    },
    unique=["subject_id"],
    strict=True,
    coerce=True,
)
validated = schema.validate(df)
```

Assert join cardinality. An accidental many-to-many merge can duplicate observations and alter results without causing a numerical error.

```python
analysis = visits.merge(
    subjects,
    on="subject_id",
    how="left",
    validate="many_to_one",
    indicator=True,
)
assert analysis["_merge"].eq("both").all()
```

### Missing sentinels and dtypes

Pandas uses dtype-dependent missing sentinels. Nullable dtypes and `convert_dtypes()` help preserve integer, Boolean, and string semantics rather than coercing columns through floating-point `NaN`.[cite:8][cite:9]

```python
df = df.convert_dtypes(dtype_backend="numpy_nullable")
missing_profile = df.isna().mean().sort_values(ascending=False)
```

Converting `-999` to `NA` corrects representation, not statistical bias. Keep reason codes—“not measured,” “below detection,” “not applicable,” and “withdrew”—in separate fields because they contain information about the missingness process.

## Data-quality audit

Audit before outcome modeling and version the resulting report. Check duplicates, impossible ranges, mixed units, unexpected precision, category typos, structural zeros, date order, follow-up windows, missingness patterns, batch/site/device effects, source-system drift, and inconsistencies between raw and derived variables.

Do not remove “outliers” automatically. An extreme point may be a transcription error, a valid rare case, or evidence of heavy tails. Correct only with a documented provenance-preserving rule, examine influence, and compare robust or sensitivity analyses.

```python
import numpy as np
import pandas as pd


def audit_table(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "dtype": df.dtypes.astype(str),
        "n": df.notna().sum(),
        "missing_n": df.isna().sum(),
        "missing_pct": 100 * df.isna().mean(),
        "unique_n": df.nunique(dropna=True),
        "constant": df.nunique(dropna=True).le(1),
        "infinite_n": [
            np.isinf(s.to_numpy(dtype=float, na_value=np.nan)).sum()
            if pd.api.types.is_numeric_dtype(s) else 0
            for _, s in df.items()
        ],
    })
```

Automated summaries provide triage, not scientific adjudication. A codebook and knowledge of how each variable was generated remain necessary.

## Exploratory analysis

Start with the unit and denominator. Then examine univariate distributions, bivariate relations, grouping structure, time/batch effects, and missingness.

Report counts, missing counts, quantiles, robust location and scale, and meaningful thresholds. Mean and standard deviation alone are inadequate for skewed, multimodal, zero-inflated, bounded, or censored measurements.

```python
summary = (
    df.groupby("group", observed=True)["outcome"]
      .agg(
          n="count",
          mean="mean",
          sd="std",
          median="median",
          q1=lambda x: x.quantile(0.25),
          q3=lambda x: x.quantile(0.75),
      )
)
```

Prefer empirical CDFs, raw-point plots, box/violin plots with observations, thoughtfully binned histograms, and scatterplots with uncertainty. Avoid truncated axes and bar charts that conceal distributions.

Examine nonlinear patterns, heteroskedasticity, interactions, and cluster structure. Correlation matrices can hide nonlinearity, Simpson’s paradox, range restriction, and confounding. When causal interpretation is intended, avoid exploratory conditioning on mediators or colliders.

An exploratory discovery should lead to data repair, a scientifically justified model revision, a sensitivity analysis, or a clearly labeled new hypothesis—not silent selection of the smallest p-value.

## Missing data

### Mechanisms

The conceptual categories are:

- **MCAR:** missingness is independent of observed and unobserved analysis variables.
- **MAR:** after conditioning on observed information in the model, missingness no longer depends on the unseen value.
- **MNAR:** missingness still depends on unseen values after conditioning on observed information.

These assumptions generally cannot be proven from observed data. They require design knowledge and sensitivity analysis. Reporting guidance recommends explicit assumptions, methods, and sensitivity analyses.[cite:20][cite:24]

Report missingness by variable, group, site, time, and outcome-relevant predictors. Modeling a missingness indicator can reveal observed associations but cannot prove MCAR or MAR.

```python
missing_by_group = (
    df.assign(outcome_missing=df["outcome"].isna())
      .groupby("group", observed=True)["outcome_missing"]
      .agg(["size", "sum", "mean"])
)
```

### Methods

| Method | Potentially defensible when | Main limitation |
|---|---|---|
| Complete case | Complete cases target the estimand under justified assumptions | Precision loss and possible selection bias |
| Available case | Denominator is explicitly variable-specific | Inconsistent analysis populations |
| Single imputation | Deterministic recovery or limited sensitivity work | Treats imputed values as known |
| Multiple imputation | Imputation and analysis models are compatible; conditional MAR plausible | Specification-sensitive and assumption-dependent |
| Maximum likelihood | Correct likelihood with ignorable missingness | Model-dependent |
| Response weighting | Response probabilities and positivity are adequate | Unstable weights and model sensitivity |
| MNAR model | Sensitivity parameters have scientific meaning | Usually not identified without assumptions |

Multiple imputation creates several completed datasets, fits the scientific model in each, and pools estimates and variances with Rubin’s rules.[cite:16][cite:18] Include the outcome, exposure, analysis covariates, predictors of missingness, and auxiliary variables. Preserve bounds, categories, interactions, nonlinearities, clusters, and longitudinal structure.

Do not impute the full dataset before train/test splitting in prediction: that leaks test information. Simple last-observation-carried-forward methods can introduce bias and ignore imputation uncertainty, producing confidence intervals that are too narrow.[cite:24]

Pair a primary MAR analysis with an MNAR sensitivity analysis such as delta adjustment, a tipping-point procedure, a pattern-mixture model, or a selection model.

## Model selection by structure

| Outcome/structure | Common starting model | Extensions and checks |
|---|---|---|
| Continuous | OLS/Gaussian GLM | Splines, robust SE, robust/quantile regression |
| Binary | Binomial GLM | Marginal effects, calibration, separation, penalization |
| Nominal category | Multinomial model | Imbalance and calibration |
| Ordered category | Ordinal cumulative-link model | Proportional-odds assessment |
| Count | Poisson GLM | Offset, overdispersion, negative binomial, zero inflation |
| Positive skew | Gamma-log or lognormal model | Tail behavior and retransformation |
| Proportion | Binomial counts or beta-type model | Masses at 0 and 1 |
| Repeated continuous | Mixed model or GEE | Random slopes and covariance structure |
| Time to event | Cox or parametric survival | Censoring, competing risks, time-varying effects |
| Many predictors | Penalized regression | Nested validation, stability, post-selection inference |

Choose the likelihood and link from outcome support and variance structure. Include log time or population at risk as an offset for rates. Distinguish subject-specific mixed-model effects from population-average GEE effects.

Avoid categorizing continuous predictors merely for convenient tables. It discards information and creates artificial thresholds. Use splines, fractional polynomials, or scientifically motivated transformations.

Centering changes intercept and lower-order interpretations; scaling is important for penalized models and numerical stability. Translate transformed coefficients back into meaningful units.

Interactions represent effect modification on the model scale. When `treatment * sex` is present, report treatment contrasts by sex with uncertainty, not only the interaction coefficient. “No interaction” depends on whether effects are additive, multiplicative, odds-based, or on another scale.

```python
import statsmodels.formula.api as smf

model = smf.ols(
    "outcome ~ treatment + bs(age, df=4) + C(site) + baseline",
    data=analysis,
).fit(cov_type="HC3")
```

Robust covariance can address some variance misspecification, but it cannot repair a wrong mean function, dependence, omitted confounding, measurement error, or extrapolation. Statsmodels identifies robust regression and sandwich covariance as tools for specific forms of specification uncertainty.[cite:15]

## Estimation and uncertainty

For central results, report:

- Estimand and units.
- Point estimate and interval.
- Model and adjustment set.
- Analytic sample and cluster counts.
- Missing-data strategy.
- Translation to a scientifically meaningful scale.

A p-value summarizes compatibility between data and a specified model under a null restriction. It does not measure the probability that the null is true or practical importance.[cite:23][cite:25] Interpret magnitude, precision, design quality, multiplicity, and external evidence together.

A frequentist 95% confidence procedure has 95% coverage under repeated use when assumptions hold; a realized interval is not a 95% posterior-probability statement. Bayesian credible intervals permit probability statements conditional on the model and prior, but require prior and computation diagnostics.

### Bootstrap

When analytic standard errors are questionable, resample in a way that reproduces the sampling design. Resample subjects, clusters, matched pairs, or time blocks—not rows—when those are the independent units. SciPy provides percentile, basic, and BCa intervals and warns that BCa can fail for degenerate bootstrap distributions.[cite:76]

```python
from scipy.stats import bootstrap
import numpy as np

ci = bootstrap(
    (x,),
    np.mean,
    confidence_level=0.95,
    n_resamples=20_000,
    method="BCa",
    rng=np.random.default_rng(20261026),
).confidence_interval
```

### Permutation

Permutation tests recompute a statistic under rearrangements permitted by the null and design. Validity depends on exchangeability. For randomized experiments, permute according to the actual assignment scheme and preserve blocks, pairs, or clusters.

SciPy supports permutation and Monte Carlo tests for built-in or custom statistics, with added computational cost and stochastic error.[cite:13] Record the generator, seed, resample count, and finite-simulation p-value rule.

## Diagnostics

Diagnostics should target assumptions relevant to the estimand. A nonsignificant assumption test does not prove an assumption, and large samples can flag immaterial departures.

For regression and GLMs examine:

- Functional form through residual-versus-fitted and component-residual plots.
- Variance through spread and group patterns.
- Dependence through cluster/time structure and autocorrelation.
- Influence through leverage, Cook’s distance, DFBETAs, and leave-one-cluster-out analysis.
- Collinearity through condition measures interpreted relative to coding and estimand.
- Outcome distribution and tail behavior where likelihood inference depends on it.
- GLM-specific deviance, overdispersion, separation, residuals, and calibration.

```python
import statsmodels.api as sm

influence = model.get_influence()
diag = influence.summary_frame()
fig = sm.graphics.plot_regress_exog(model, "baseline")
```

Do not delete a point because it exceeds a heuristic Cook’s-distance cutoff. Verify its source, understand why it is influential, and report sensitivity to inclusion.

## Predictive validation

Discrimination and calibration answer different questions. For binary outcomes report a proper scoring rule such as log loss or Brier score, calibration behavior, discrimination, and decision utility if a threshold is used. ROC AUC alone does not establish calibrated probabilities or practical usefulness.

Validate the entire modeling process, including preprocessing and variable selection. Scikit-learn warns that fitting transformations on all data leaks test information and gives optimistic performance; pipelines keep transformations inside cross-validation and fit only on training partitions.[cite:31]

```python
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

pre = ColumnTransformer([
    ("num", Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
    ]), numeric_columns),
    ("cat", Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ]), categorical_columns),
])

pipe = Pipeline([
    ("preprocess", pre),
    ("model", LogisticRegression(max_iter=5000)),
])

cv = StratifiedKFold(n_splits=10, shuffle=True, random_state=20261026)
scores = cross_validate(
    pipe, X, y, cv=cv,
    scoring=["roc_auc", "neg_log_loss", "neg_brier_score"],
)
```

Use grouped cross-validation for clustered observations and forward or blocked validation for temporal data. If tuning and reporting performance on the same resamples, use nested validation or an untouched test set.

## Bayesian workflow

Bayesian analysis requires prior predictive checks, numerical diagnostics, posterior predictive checks, prior sensitivity, and model criticism. PyMC describes prior predictive checks as testing whether assumptions generate plausible data and posterior predictive checks as comparing model-generated and observed data.[cite:46][cite:50]

For MCMC inspect divergences, effective sample size, rank-normalized convergence statistics, energy behavior, trace plots, and mixing. Sampler convergence does not imply scientific adequacy. Posterior predictive discrepancies can expose wrong tails, zero inflation, dependence, or subgroup behavior.

## Multiplicity

Multiplicity arises from outcomes, exposures, subgroups, time points, model variants, transformations, and interim looks—not only from a visible list of p-values. Define the hypothesis family from the scientific decision context.

- Use Holm or another family-wise error method when any false positive is costly.
- Use Benjamini–Hochberg or another FDR method for high-dimensional discovery.
- Use hierarchical testing, gatekeeping, multilevel models, or partial pooling when claims have structure.
- Report all prespecified analyses and label unplanned ones.

Statsmodels implements Bonferroni, Holm, Sidak, Benjamini–Hochberg, Benjamini–Yekutieli, and related procedures with documented assumptions.[cite:42][cite:44]

```python
from statsmodels.stats.multitest import multipletests

reject, p_adj, _, _ = multipletests(
    p_values, alpha=0.05, method="fdr_bh"
)
```

Adjustment does not repair p-hacking, outcome switching, adaptive subgroup selection, or misspecification. The full analytical search space still requires disclosure.

## Causal analysis

Regression adjustment becomes causal only after an identification argument. Define a target trial or equivalent causal question: eligibility, treatment strategies, assignment, time zero, follow-up, outcome, contrast, and analysis. Justify the adjustment set with a causal graph or explicit causal reasoning before automated selection.

Core conditions include:

- **Consistency:** observed outcomes correspond to the well-defined intervention received.
- **Exchangeability:** no unmeasured confounding conditional on the adjustment set.
- **Positivity:** every relevant covariate pattern has a nonzero probability of each strategy.
- **No interference**, unless spillovers are modeled.
- **Correct time alignment:** eligibility, treatment, confounders, and follow-up share coherent time zero.

Do not adjust for every available column. Post-treatment variables can be mediators or colliders. Predictive variables are not automatically confounders.

Possible estimators include outcome regression, standardization, matching, propensity weighting, g-computation, inverse-probability weighting, and doubly robust methods. Examine overlap, weight distributions, covariate balance, sensitivity to trimming, and alternative justified models. No observed balance measure proves the absence of unmeasured confounding.

Report crude and adjusted estimates with precision, define confounders, and justify their inclusion, as recommended by observational reporting guidance.[cite:62][cite:72] Use quantitative bias analysis, negative controls, or other domain-appropriate sensitivity methods without claiming that one statistic proves causality.

## Power and sample size

Design around a scientifically meaningful effect and desired precision, not a generic 80% power target. Specify variance, allocation, intracluster correlation, attrition, noncompliance, multiplicity, repeated measures, and the exact estimator/test.

Statsmodels provides analytical power functions for common tests, parameterized by standardized effect size and sample size.[cite:83] Complex designs usually need simulation reproducing clustering, missingness, assignment, analysis code, and the decision rule. Vary uncertain inputs rather than reporting one optimistic scenario.

Do not report post hoc “observed power” calculated from the observed effect and p-value. Report the interval and whether it excludes scientifically important values.

## Sensitivity analysis

A sensitivity analysis should vary a defensible assumption rather than create arbitrary model permutations.

| Threat | Useful analysis |
|---|---|
| Functional form | Splines, transformations, semiparametric alternatives |
| Heteroskedasticity | Robust covariance, variance model, bootstrap |
| Cluster dependence | Cluster SE, mixed model, GEE, cluster bootstrap |
| Influential cases | Robust fit, leave-one-cluster-out |
| Missing outcomes | MI under MAR plus delta/tipping-point MNAR analysis |
| Confounding | Alternative justified sets and quantitative bias analysis |
| Weak overlap | Trimming, overlap weights, target-population revision |
| Outcome definition | Prespecified alternative operationalizations |
| Multiplicity | FWER/FDR and hierarchical approaches |
| Distributional assumptions | Alternative likelihood, permutation, bootstrap |

A result is robust when its scientific interpretation remains similar across plausible assumptions, not merely when each p-value falls on the same side of 0.05. Display estimates and intervals across specifications and justify each alternative.

## Reporting structure

A generated results table should contain:

| Field | Content |
|---|---|
| Estimand | Human-readable contrast and horizon |
| Estimate | Effect in scientific units |
| Interval | Clearly labeled CI or credible interval |
| Scale | Difference, ratio, probability, rate, or link scale |
| Model | Family, link, covariance/cluster structure |
| Adjustment | Covariates and coding |
| Sample | Observations, independent units, events, clusters |
| Missing data | Complete case, MI, likelihood, or weighting |
| Multiplicity | Family and procedure |
| Sensitivity | Direction and materiality of changes |

For nonlinear models, marginal predictions or contrasts may match the estimand better than raw link-scale coefficients.

The methods section should state design, sampling/assignment, dates, units, definitions, exclusions, derivations, missingness assumptions, model formula/family/link, reference levels, nonlinear terms, interactions, offsets, covariance handling, estimand, interval procedure, multiplicity, diagnostics, sensitivity analyses, software versions, seeds, and data/code availability. STROBE specifically calls for methods controlling confounding, subgroup and interaction analyses, participant characteristics, and crude and adjusted estimates with precision.[cite:65]

## End-to-end skeleton

```python
from __future__ import annotations

import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import statsmodels
import statsmodels.formula.api as smf

SEED = 20261026
RNG = np.random.default_rng(SEED)
OUT = Path("outputs")
OUT.mkdir(exist_ok=True)

# Immutable input
raw = pd.read_parquet("data/raw/study.parquet")

# Validation
assert raw["subject_id"].notna().all()
assert not raw["subject_id"].duplicated().any()
assert raw["group"].isin(["control", "treated"]).all()

# Named derivations
analysis = raw.assign(
    group=lambda d: pd.Categorical(
        d["group"], categories=["control", "treated"]
    ),
    age_centered=lambda d: d["age"] - d["age"].mean(),
)

# Denominators and flow
flow = {
    "raw_n": len(raw),
    "outcome_observed_n": int(analysis["outcome"].notna().sum()),
}

# Descriptive output
summary = (
    analysis.groupby("group", observed=True)["outcome"]
    .agg(n="count", mean="mean", sd="std", median="median")
)
summary.to_csv(OUT / "descriptive.csv")

# Primary model: change covariance to match the design
fit = smf.ols(
    "outcome ~ C(group) + baseline + age_centered + C(site)",
    data=analysis,
    missing="drop",
).fit(cov_type="HC3")
fit.summary2().tables[1].to_csv(OUT / "primary_model.csv")

# Diagnostics and sensitivity
fit.get_influence().summary_frame().to_parquet(OUT / "influence.parquet")

sensitivity = smf.ols(
    "outcome ~ C(group) + baseline + age_centered",
    data=analysis,
    missing="drop",
).fit(cov_type="HC3")
sensitivity.summary2().tables[1].to_csv(OUT / "sensitivity_model.csv")

# Provenance
metadata = {
    "seed": SEED,
    "python": platform.python_version(),
    "pandas": pd.__version__,
    "scipy": scipy.__version__,
    "statsmodels": statsmodels.__version__,
    "flow": flow,
}
(OUT / "metadata.json").write_text(json.dumps(metadata, indent=2))
```

This skeleton is not a universal model. For clusters use appropriate cluster covariance or a multilevel/GEE model. For missingness replace implicit listwise deletion with the prespecified analysis. For prediction place every learned transformation inside validation folds.

## Verification

### Data tests

- Input hashes and expected files.
- Types, ranges, categories, units, keys, and foreign keys.
- Join cardinality and row-count reconciliation.
- Regression tests for previously observed data faults.

### Statistical tests

- Hand-check small deterministic examples.
- Compare selected estimates with another trusted implementation.
- Verify expected invariance to row order, relabeling, and unit conversion.
- Use simulation to examine bias, coverage, Type I error, power, and convergence.
- Test separation, zero-event cells, empty levels, singular matrices, and degenerate bootstrap distributions.

### Pipeline tests

- Rebuild all artifacts in a clean environment.
- Execute notebooks from top to bottom.
- Confirm determinism where algorithms permit.
- Prohibit writes to raw data.
- Fail on validation errors, convergence warnings, and stale inputs.

A task runner should reconstruct the analysis with one command. The notebook should not be the only executable record.

## Common failures

| Failure | Danger | Better practice |
|---|---|---|
| Treating rows as independent | Underestimated uncertainty | Model/resample at the independent-unit level |
| Silent listwise deletion | Selection bias and changed target | Report flow, justify mechanism, test sensitivity |
| Mean imputation | Distorted variance and uncertainty | MI, likelihood, weighting, or justified complete case |
| Preprocessing before splitting | Leakage and optimistic performance | Fit transformations in each training fold[cite:31] |
| Covariate selection by p-value | Unstable and causally inappropriate adjustment | Design/causal knowledge and prespecification |
| Dichotomizing continuous predictors | Information loss and artificial thresholds | Flexible continuous functions |
| Universal normality testing | Misidentifies relevant assumptions | Diagnose residual/design assumptions |
| Reading p > 0.05 as no effect | Confuses imprecision with equivalence | Report estimate/interval; design equivalence tests |
| Reading p < 0.05 as important | Significance is not magnitude | Compare with meaningful effect thresholds[cite:23] |
| Reporting only AUC | Omits calibration and utility | Add proper scores and decision metrics |
| Ignoring multiplicity | Inflated false discoveries | Define families, adjust, disclose all analyses |
| Automatic outlier deletion | Can remove valid signal | Verify, diagnose, and perform sensitivity analysis |
| Treating robust SE as universal repair | Leaves bias and mean misspecification | Reconsider model, dependence, and identification |
| Calling adjusted regression causal | No identification guarantee | State causal assumptions and assess sensitivity |
| Publishing an unpinned notebook | Hidden state and dependency drift | Lock environment and execute cleanly[cite:63][cite:73] |

## Operating procedure

1. Define the design, population, unit, outcome, exposure, estimand, and analytical goal.
2. Freeze and fingerprint raw inputs and metadata.
3. Build executable schemas for types, units, ranges, keys, and relationships.
4. Create the analytical table through named, tested transformations.
5. Audit quality and missingness; preserve reason codes and denominators.
6. Perform structured exploration without converting each pattern into a test.
7. Fit the prespecified model with outcome and dependence structures matching the design.
8. Report interpretable effects and uncertainty, with p-values in a supporting role.
9. Diagnose functional form, variance, dependence, influence, multiplicity, and identification.
10. Validate prediction with leakage-free grouped, temporal, or nested resampling.
11. Generate tables, figures, flow counts, and manuscript-facing numbers from one source.
12. Rebuild in a clean environment and archive code, configuration, environment, logs, and shareable data.

## Final checklist

### Scientific validity

- [ ] The question and estimand are explicit.
- [ ] The analysis unit matches the independence unit.
- [ ] Descriptive, predictive, inferential, and causal claims are distinguished.
- [ ] Covariates and interactions have scientific justification.
- [ ] Outcome family, link, and dependence structure are defensible.
- [ ] Effects and intervals—not only p-values—are reported.
- [ ] Multiplicity and selective analysis are addressed.

### Data integrity

- [ ] Raw data are immutable and fingerprinted.
- [ ] Schema validates types, units, ranges, keys, and categories.
- [ ] Joins and row counts are reconciled.
- [ ] Missing codes and reasons are preserved.
- [ ] Exclusions and corrections are auditable.

### Diagnostics

- [ ] Functional form, variance, dependence, and influence are examined.
- [ ] Resampling respects pairing, clusters, and temporal structure.
- [ ] Prediction is evaluated out of sample without leakage.
- [ ] Bayesian computation and predictive behavior are checked where applicable.
- [ ] Sensitivity analyses target plausible assumption failures.

### Reproducibility

- [ ] Code, configuration, and execution order are versioned.
- [ ] Dependencies are locked and reported.
- [ ] Random generators and seeds are explicit.
- [ ] A clean one-command rebuild works.
- [ ] Tables and figures are generated, not manually edited.
- [ ] Data/code are shared or restrictions are documented.

## Conclusion

Scientific statistical analysis is strongest when a table is treated as the observed endpoint of a study design rather than an anonymous matrix. The decisive work surrounds model fitting: defining the estimand, preserving design structure, validating the schema, reasoning about missingness and confounding, stress-testing assumptions, and making the computation auditable.

Python supplies the required components. SciPy supports bootstrap, permutation, and Monte Carlo procedures; statsmodels provides interpretable regression and covariance tools; scikit-learn provides leakage-resistant pipelines; PyMC supports predictive model criticism; and pandas supplies explicit dtype and missing-value handling.[cite:13][cite:15][cite:31][cite:46][cite:8] These tools become scientific only when they form a transparent chain of evidence whose assumptions, choices, limitations, and outputs can be independently challenged and reproduced.
