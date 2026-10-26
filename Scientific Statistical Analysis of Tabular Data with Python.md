# Scientific Statistical Analysis of Tabular Data with Python

## Executive summary

Scientific analysis of tabular data is not a sequence of library calls. It is a chain of claims connecting a study design, an estimand, a data-generating process, a measurement system, a statistical model, diagnostics, uncertainty quantification, and a reproducible report. Python supplies mature components for this chain—primarily pandas, NumPy, SciPy, statsmodels, scikit-learn, PyMC, and visualization libraries—but scientific validity still depends on design-aware choices and explicit assumptions.

A defensible workflow has six properties:

- **Question-first:** define the population, unit of analysis, outcome, exposure or intervention, estimand, time horizon, and decision criterion before fitting models.
- **Design-aware:** preserve pairing, repeated measures, clusters, sampling weights, censoring, and temporal order.
- **Schema-controlled:** validate types, units, ranges, keys, categories, and missing-value codes before analysis.
- **Estimation-centered:** report effect sizes and uncertainty intervals; use hypothesis tests as model-based compatibility checks, not as binary truth machines. The American Statistical Association states that a p-value does not give the probability that a hypothesis is true, does not measure effect magnitude, and should not alone determine scientific conclusions.[^1]
- **Stress-tested:** evaluate assumptions, influential observations, missing-data mechanisms, multiplicity, alternative specifications, and out-of-sample behavior where relevant.
- **Reproducible:** publish executable code, data or a legally shareable substitute, dependency specifications, deterministic seeds, and the exact execution order. Reproducibility standards emphasize availability of data, models, code, dependencies, execution instructions, and control of random components.[^2]

The central technical recommendation is to treat the complete analysis as a versioned pipeline whose inputs are immutable raw tables and whose outputs—validated analytic tables, fitted models, diagnostics, figures, and publication tables—are generated automatically.

## Scope and conceptual frame

This report addresses domain-agnostic, advanced statistical analysis of rectangular data: observations represented by rows and measured variables represented by columns. It covers descriptive, inferential, predictive, and causal tasks, but it does not pretend that these tasks are interchangeable.

| Goal | Target | Typical evaluation | Main threat |
|---|---|---|---|
| Description | Features of the observed sample | Accurate summaries and visualization | Measurement errors and misleading aggregation |
| Population inference | Population parameter or contrast | Standard errors, confidence intervals, calibrated tests | Sampling/design violations and model misspecification |
| Prediction | Performance on future or unseen observations | Out-of-sample discrimination, calibration, and loss | Leakage, overfitting, and distribution shift |
| Causal inference | Counterfactual contrast under an intervention | Identification argument plus sensitivity analysis | Confounding, selection, positivity, and interference |

A model may predict well without identifying a causal effect, and a causal estimator may be intentionally optimized for an interpretable treatment contrast rather than predictive accuracy. Consequently, a scientific analysis should label its target explicitly rather than using the generic phrase “find relationships.”

## Scientific specification

### Define the estimand

Before inspecting inferential results, write a compact analysis specification:

- **Population:** to whom or what should the result generalize?
- **Unit:** person, device, specimen, site, transaction, time point, or another entity.
- **Outcome:** variable definition, scale, measurement time, and handling of competing events.
- **Exposure or intervention:** level, timing, reference condition, and assignment mechanism.
- **Estimand:** mean difference, risk ratio, odds ratio, rate ratio, marginal effect, conditional coefficient, quantile difference, survival contrast, predictive risk, or another functional.
- **Covariates:** prespecified adjustment variables, effect modifiers, precision variables, and variables explicitly excluded because they are mediators or colliders.
- **Uncertainty:** confidence or credible interval level, resampling structure, clustering level, and multiplicity family.
- **Sensitivity analyses:** plausible alternative assumptions to challenge the primary result.

For observational work, transparent reporting guidance calls for explicit definitions of outcomes, exposures, predictors, confounders, and effect modifiers, as well as explanations of how confounding was controlled. The estimand determines the proper model and interpretation; for example, a logistic-regression coefficient is a conditional log-odds contrast and is not automatically a marginal risk difference.[^3][^4]

### Separate exploration and confirmation

Exploratory analysis discovers patterns and model defects. Confirmatory analysis evaluates prespecified hypotheses or estimands. The same data may support both, but the report must distinguish them; undisclosed iteration turns nominal p-values and confidence intervals into overly optimistic summaries.

A robust project stores the primary specification in a machine-readable configuration or protocol before final analysis. Deviations should be logged with rationale, and exploratory findings should be marked for independent validation rather than retroactively presented as prespecified.

### Respect the sampling design

Independence belongs to the sampling or assignment process, not to a dataframe. Rows are correlated when they represent repeated observations from the same subject, members of the same household, samples processed in a batch, students within schools, or nearby measurements in space or time. Ignoring that structure commonly understates uncertainty.

Choose among cluster-robust covariance, generalized estimating equations, mixed-effects models, hierarchical Bayesian models, survey estimators, blocked permutations, or cluster-level resampling according to the design and estimand. Statsmodels includes linear mixed-effects models and generalized model families, though its documented generalized mixed-model implementation has specific family and random-effect limitations that should be checked before use.[^5][^6]

## Python statistical stack

| Layer | Recommended tools | Scientific role |
|---|---|---|
| Storage and interchange | Parquet/Arrow, CSV for interchange, SQL | Typed, inspectable data transport |
| Tabular manipulation | pandas, Polars where appropriate | Cleaning, joins, reshaping, grouped summaries |
| Numerical computation | NumPy | Arrays, linear algebra, random generators |
| Classical statistics | SciPy | Distributions, tests, bootstrap, permutation and Monte Carlo procedures |
| Statistical modeling | statsmodels, formulaic/patsy | Interpretable regression, GLMs, diagnostics, robust covariance, time series |
| Predictive modeling | scikit-learn | Preprocessing pipelines, resampling, metrics, model selection |
| Bayesian modeling | PyMC, ArviZ | Hierarchical models, posterior inference, predictive checking |
| Visualization | seaborn, matplotlib, plotnine, Altair | Distributional, diagnostic, and effect visualization |
| Validation | Pandera, Pydantic, Great Expectations | Executable data contracts |
| Reproducibility | uv/pip-tools/conda, Git, DVC, containers, Snakemake/Make | Environment, provenance, and workflow control |

Use stable public APIs and pin an environment for an archived analysis. The precise package choice matters less than documenting versions, validating numerical results, and keeping transformations deterministic and testable.

## Project architecture

A production-quality scientific repository can use this structure:

```text
project/
├── README.md
├── pyproject.toml
├── uv.lock                  # or another complete lock file
├── configs/
│   └── analysis.yaml
├── data/
│   ├── raw/                 # immutable; usually not committed
│   ├── interim/
│   └── processed/
├── src/project_name/
│   ├── io.py
│   ├── validation.py
│   ├── features.py
│   ├── estimands.py
│   ├── models.py
│   └── reporting.py
├── notebooks/               # exploration, not the sole source of logic
├── tests/
├── scripts/
└── outputs/
    ├── models/
    ├── tables/
    └── figures/
```

Notebooks are valuable computational narratives, but hidden state and out-of-order execution are hazards. Research guidance recommends meaningful modular cells, explanatory text, explicit dependency management, version control, shared data where possible, and testing by restarting and executing from top to bottom. Move reusable logic into tested modules and reserve notebooks for transparent orchestration and interpretation.[^7][^8]

A minimal reproducibility header should record the Git commit, input-data hash, configuration hash, Python and package versions, operating system, random seed, and execution timestamp. Provenance should permit every result to be traced through all transformations to its inputs.[^9]

## Data ingestion and schema validation

### Preserve raw evidence

Never overwrite raw files. Record cryptographic hashes and import them through a single, reviewed function. CSV is ubiquitous but weakly typed; Parquet better preserves types and metadata for internal analytic datasets.

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

Do not infer identifiers as numbers: leading zeros, large integers, and embedded check digits can be silently damaged. Parse dates with explicit timezone and locale assumptions, retain original values when conversion can fail, and harmonize units before concatenating sources.

### Enforce a data contract

Validation should fail loudly on structural violations rather than silently deleting problematic rows. At minimum, assert:

- Column presence, names, and order where order matters.
- Data types and nullability.
- Unique keys and expected table cardinality.
- Domain constraints and physically possible ranges.
- Category levels and reference coding.
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

For joins, assert cardinality explicitly. A supposedly many-to-one join that is actually many-to-many can duplicate observations and alter estimates without triggering a numerical error.

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

### Handle types and missing sentinels deliberately

Pandas uses dtype-dependent missing sentinels; its nullable dtypes and `convert_dtypes()` help preserve integer, Boolean, and string semantics instead of coercing everything through floating-point `NaN`. Nevertheless, software missingness is not a scientific missing-data strategy: converting `-999` to `NA` fixes representation, not bias.[^10][^11]

```python
df = df.convert_dtypes(dtype_backend="numpy_nullable")
missing_profile = (
    df.isna()
      .mean()
      .rename("missing_fraction")
      .sort_values(ascending=False)
)
```

Retain reason codes such as “not measured,” “below detection limit,” “not applicable,” and “participant withdrew” in separate variables. Collapsing these into one marker destroys information about the missingness process.

## Data quality audit

A quality audit should occur before outcome modeling and produce a versioned report. Useful checks include:

- Duplicate primary keys and near-duplicate records.
- Impossible or implausible ranges.
- Unit mixtures and unexpected precision.
- Category typos, rare levels, and structural zeros.
- Date ordering and follow-up windows.
- Monotone or intermittent missingness patterns.
- Batch, site, device, interviewer, and calendar-time effects.
- Distribution drift between collection periods or source systems.
- Inconsistencies between raw and derived fields.

Do not automatically remove “outliers.” An extreme value may be a transcription error, a valid rare observation, or evidence that the assumed model has light tails. Record a provenance-preserving correction rule, compare analyses with and without influential observations, and prefer robust models when tail behavior is intrinsic.

A compact audit function can expose high-risk columns:

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

Automated summaries are triage tools. Scientific review still requires a codebook, domain constraints, and knowledge of how each variable was generated.

## Exploratory data analysis

Exploration should reveal data structure and challenge assumptions without becoming an undisclosed hypothesis generator. Start with the unit of analysis and denominators, then examine univariate distributions, bivariate relationships, grouping structure, missingness, and temporal or batch effects.

### Distributional summaries

Report counts, missing counts, quantiles, robust location and scale, and scientifically meaningful thresholds. Means and standard deviations are useful for some distributions but insufficient for skewed, multimodal, zero-inflated, bounded, or censored variables.

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

Use plots that expose observations or distributions: empirical cumulative distributions, dot/strip plots, violin or box plots with raw points, histograms with sensitivity to bin width, and scatterplots with uncertainty. Avoid truncated axes and bar charts that hide distribution shape.

### Relationships and stratification

Examine nonlinear patterns, heteroskedasticity, interactions, and cluster structure. Correlation matrices alone can conceal nonlinearity, Simpson’s paradox, range restriction, and confounding. Compare crude and stratified relationships, but avoid conditioning on post-exposure variables or colliders when causal interpretation is intended.

An EDA finding should trigger one of four actions: repair a data problem, revise a scientifically implausible model, add a prespecified sensitivity analysis, or label a new hypothesis as exploratory. It should not trigger silent selection of whichever test gives the smallest p-value.

## Missing data

### Mechanisms and assumptions

Missingness is a property of the joint data-generating process. The standard conceptual categories are:

- **MCAR:** missingness is independent of observed and unobserved analysis variables.
- **MAR:** conditional on observed information included in the missingness or imputation model, missingness does not depend on the unseen value.
- **MNAR:** missingness still depends on unobserved values after conditioning on observed information.

These conditions generally cannot be established from the observed table alone. They require design knowledge and sensitivity analysis. Reporting guidance recommends making the assumed mechanism and the missing-data method explicit and presenting sensitivity analyses.[^12][^13]

### Diagnose patterns, not mechanisms

Report missingness by variable, group, site, time, and outcome-relevant predictors. Model missingness indicators descriptively to identify observed associations, but do not claim that a nonsignificant test proves MCAR or MAR.

```python
missing_by_group = (
    df.assign(outcome_missing=df["outcome"].isna())
      .groupby("group", observed=True)["outcome_missing"]
      .agg(["size", "sum", "mean"])
)
```

### Choose an analysis

| Method | Potentially defensible when | Main limitation |
|---|---|---|
| Complete-case analysis | Complete cases target the estimand under a justified mechanism and model | Can lose precision and induce selection bias |
| Available-case summaries | Estimand and denominator are clearly variable-specific | Produces inconsistent analytic populations |
| Single imputation | Primarily for deterministic recovery or limited sensitivity scenarios | Treats imputed values as known and understates uncertainty |
| Multiple imputation | Imputation model is compatible with analysis; MAR is plausible conditional on auxiliaries | Sensitive to model specification and unverifiable assumptions |
| Maximum likelihood | Correct joint/conditional likelihood with ignorable missingness | Model-dependent |
| Weighting | Response probabilities are estimable and positivity is adequate | Unstable weights and sensitivity to propensity model |
| MNAR models | Sensitivity parameters have scientific interpretation | Typically not identified without assumptions |

Multiple imputation creates several completed datasets, fits the analysis model in each, and pools estimates and uncertainty using Rubin’s rules. Include the outcome, exposure, analysis covariates, variables predictive of missingness, and useful auxiliary variables; respect bounds, categories, interactions, nonlinearities, clusters, and longitudinal structure. Never impute the entire dataset before train/test splitting for a predictive study, because that leaks information from the test set.[^14][^15]

Simple methods such as last observation carried forward are generally inadvisable because they can introduce bias and ignore imputation uncertainty, leading to confidence intervals that are too narrow. For primary analyses, pair an explicit assumption—often MAR—with sensitivity analyses such as delta adjustment, tipping-point analysis, pattern-mixture models, or selection models.[^13]

## Choosing statistical models

### Match outcome and design

| Outcome or structure | Common starting model | Important extensions/checks |
|---|---|---|
| Continuous, unbounded | OLS or Gaussian GLM | Splines, transformations, robust SE, robust regression, quantile regression |
| Binary | Binomial GLM with logit link | Marginal risks/effects, calibration, separation, penalization |
| Nominal multicategory | Multinomial model | Class imbalance, calibration, independence assumptions |
| Ordered category | Ordinal cumulative-link model | Proportional-odds assessment |
| Count | Poisson GLM | Exposure offset, overdispersion, negative binomial, zero inflation |
| Positive skewed | Gamma GLM with log link or lognormal model | Tail behavior and retransformation |
| Proportion | Binomial model for counts; beta-type model for continuous proportions | Boundary masses at 0 and 1 |
| Repeated continuous | Linear mixed model or GEE | Random slopes, covariance structure, cluster robustness |
| Time to event | Kaplan–Meier, Cox, parametric survival model | Censoring, competing risks, time-varying effects |
| Many predictors | Penalized regression | Nested validation, stability, post-selection inference |

Select the link and likelihood from the support and variance structure of the outcome, not from habit. For counts, include the logarithm of time or population at risk as an offset when modeling rates. For repeated observations, distinguish subject-specific mixed-model effects from population-average GEE effects.

### Encode predictors scientifically

Avoid categorizing continuous predictors merely to obtain easy tables. Categorization discards information, creates arbitrary discontinuities, and can leave residual confounding. Use meaningful nonlinear functions such as restricted cubic splines, fractional polynomials, or scientifically motivated transformations.

Centering changes the interpretation of the intercept and lower-order terms but not model fit in ordinary linear models. Scaling is essential for penalized models and numerical stability, but transformed coefficients should be translated back into meaningful units for reporting.

Interactions encode effect modification on the model’s scale. If `treatment * sex` is included, report estimated contrasts by sex with uncertainty rather than interpreting only the interaction coefficient. Remember that “no interaction” depends on whether effects are measured on additive, multiplicative, odds, or another scale.

### Formula-based inference

Statsmodels formulas make model specifications readable and retain categorical structure:

```python
import statsmodels.formula.api as smf

model = smf.ols(
    "outcome ~ treatment + bs(age, df=4) + C(site) + baseline",
    data=analysis,
).fit(cov_type="HC3")

result = model.summary2().tables[^1]
```

Heteroskedasticity-consistent covariance can protect standard-error calculations against some variance misspecification, but it does not repair an incorrect mean function, dependence, omitted confounding, measurement error, or influential extrapolation. Statsmodels explicitly points to robust regression and sandwich covariance estimators as responses to some specification uncertainty.[^16]

## Estimation and uncertainty

### Report effects, not stars

For every central result, report:

- The estimand and units.
- Point estimate.
- Confidence or credible interval.
- Model and adjustment set.
- Analytic sample size and cluster count.
- Missing-data strategy.
- A scale meaningful to subject-matter readers.

A p-value measures incompatibility between data and a specified model under a null restriction; it does not measure practical importance or the probability that the null is true. A large sample can make negligible effects statistically detectable, while a small sample can leave important effects imprecise. Interpret effect magnitude, uncertainty, design quality, multiplicity, and external evidence together.[^17][^1]

### Confidence intervals

A frequentist 95% confidence procedure has 95% long-run coverage under repeated use when its assumptions hold. It does not mean that a fixed realized interval has a 95% probability of containing a fixed parameter. Bayesian credible intervals can support probability statements conditional on the model and prior, but they require prior and computational diagnostics.

When analytic standard errors are questionable, use resampling that mirrors the sampling structure. SciPy provides percentile, basic, and bias-corrected and accelerated bootstrap confidence intervals, but its documentation warns that BCa can fail for degenerate bootstrap distributions. Resample clusters, subjects, matched pairs, or time blocks—not individual rows—when those are the independent sampling units.[^18]

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

### Permutation and randomization inference

Permutation tests construct a reference distribution by recomputing a statistic under label rearrangements allowed by the null and design. Exact validity depends on exchangeability. Randomized experiments should permute according to the actual assignment scheme, preserving blocks, pairs, or clusters.

SciPy includes permutation and Monte Carlo testing for built-in or custom statistics and notes their flexibility at the cost of computation and stochastic results. Set and record random generators, report the number of resamples, and use an appropriate finite-simulation p-value calculation rather than returning zero.[^19]

## Model diagnostics

Diagnostics should target assumptions relevant to the estimand, not serve as a ritual checklist. A nonsignificant assumption test does not prove an assumption, especially in small samples, and large samples can make immaterial deviations highly significant.

### Linear and generalized models

Examine:

- **Functional form:** residuals versus fitted values and component-plus-residual plots.
- **Variance:** residual spread, scale-location patterns, and variance by group.
- **Dependence:** cluster/time structure and residual autocorrelation.
- **Influence:** leverage, Cook’s distance, DFBETAs, and leave-one-cluster-out estimates.
- **Collinearity:** condition indices and variance inflation, interpreted relative to estimand and coding.
- **Outcome distribution:** quantile plots and tail behavior where likelihood inference depends on it.
- **GLM adequacy:** deviance, overdispersion, separation, residual patterns, and calibration.

```python
import statsmodels.api as sm

influence = model.get_influence()
diag = influence.summary_frame()
fig = sm.graphics.plot_regress_exog(model, "baseline")
```

Do not delete a point merely because Cook’s distance crosses a heuristic threshold. Verify source data, investigate why it is influential, and report sensitivity to its inclusion.

### Predictive diagnostics

Discrimination and calibration answer different questions. For binary outcomes, report a proper scoring rule such as log loss or Brier score, calibration intercept/slope or curve, and threshold-specific utility where decisions require a threshold. ROC AUC alone does not establish calibrated probabilities or usefulness under asymmetric costs.

Validate the entire modeling process, including preprocessing and variable selection. Scikit-learn warns that fitting preprocessing on all data leaks test information and yields overly optimistic performance; pipelines keep transformations inside cross-validation and apply `fit` only to training subsets.[^20]

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
    return_estimator=True,
)
```

Use grouped cross-validation for clustered data and forward-chaining or blocked validation for time-ordered data. If hyperparameters are tuned and performance is reported, use nested resampling or an untouched test set to avoid selection bias.

### Bayesian diagnostics

A Bayesian workflow includes prior predictive checks, diagnostics of the numerical approximation, posterior predictive checks, sensitivity to priors, and model criticism. PyMC describes prior predictive checks as a way to assess whether assumptions generate credible data and posterior predictive checks as comparisons between model-generated and observed data.[^21][^22]

For MCMC, inspect divergences, effective sample size, rank-normalized convergence diagnostics, energy behavior, trace plots, and chain mixing. A converged sampler does not imply a scientifically adequate model; posterior predictive discrepancies can expose misspecified tails, zero inflation, dependence, or subgroup behavior.

## Multiplicity and selective analysis

Multiplicity arises from multiple outcomes, exposures, subgroups, time points, model variants, transformations, and interim looks—not only from a visible column of p-values. Define the family of claims based on the scientific decision context.

- Use **Holm** or another family-wise error procedure when even one false positive in the family is costly.
- Use **Benjamini–Hochberg** or an appropriate false-discovery-rate method for discovery settings with many parallel hypotheses.
- Use hierarchical testing, gatekeeping, multilevel models, or partial pooling when hypotheses have structure.
- Report all prespecified analyses and label unplanned analyses.

Statsmodels implements Bonferroni, Holm, Sidak, Benjamini–Hochberg, Benjamini–Yekutieli, and other adjustment procedures, with assumptions and limitations documented for the methods.[^23][^24]

```python
from statsmodels.stats.multitest import multipletests

reject, p_adj, _, _ = multipletests(
    p_values,
    alpha=0.05,
    method="fdr_bh",
)
```

Adjustment does not repair p-hacking, outcome switching, data-dependent subgroup selection, or a misspecified model. Transparency about the complete analytical search space remains essential.

## Causal analysis of observational tables

A regression coefficient becomes a causal estimate only after an identification argument. Define a target trial or equivalent causal question: eligibility, treatment strategies, assignment, time zero, follow-up, outcome, causal contrast, and analysis plan. Draw a directed acyclic graph or otherwise justify the adjustment set before selecting variables with automated algorithms.

Key conditions include:

- **Consistency:** observed outcomes correspond to the defined intervention received.
- **Exchangeability:** no unmeasured confounding conditional on the adjustment set.
- **Positivity:** each relevant covariate pattern has a nonzero probability of each treatment strategy.
- **No interference**, unless the estimand and model explicitly include spillovers.
- **Correct time alignment:** treatment, confounders, eligibility, and follow-up share a coherent time zero.

Do not adjust mechanically for every available column. Post-treatment variables can mediate effects or induce collider bias; instruments can amplify bias under some misspecification; highly predictive but causally irrelevant variables do not automatically control confounding.

Candidate estimators include outcome regression, standardization, propensity-score weighting or matching, g-computation, inverse-probability weighting, and doubly robust estimators. Diagnostics should include overlap, weight distributions, covariate balance on the chosen scale, sensitivity to trimming or truncation, and alternative adjustment models. No balance metric or robustness method can test away unmeasured confounding.

Report both unadjusted and adjusted estimates with precision, define the confounders, and state why they were included, consistent with observational reporting guidance. Add quantitative bias analysis, negative controls, alternative exposure definitions, or an E-value where scientifically appropriate, while avoiding claims that a single sensitivity number proves causality.[^25][^26]

## Power, precision, and sample size

Design analyses around a scientifically meaningful effect and desired precision, not a generic target of 80% power detached from consequences. Specify variance, allocation, intracluster correlation, attrition, noncompliance, multiplicity, repeated measures, and the exact test or estimator.

Statsmodels provides analytical power functions for common t tests and other standard designs, parameterized by standardized effect size and sample size. Complex designs usually require simulation under explicit data-generating mechanisms. The simulation should reproduce clustering, missingness, treatment assignment, analysis code, and decision rule; varying uncertain inputs is more informative than reporting a single optimistic scenario.[^27]

Never estimate a post hoc “observed power” from the observed effect and p-value. Report the confidence interval and the design’s ability to distinguish scientifically relevant values.

## Sensitivity and robustness

A sensitivity analysis should alter a defensible assumption, not generate a multiverse from arbitrary choices. Prespecify a small set of assumption-targeted checks:

| Threat | Useful sensitivity analysis |
|---|---|
| Functional-form misspecification | Splines, transformations, semiparametric model |
| Heteroskedasticity | Robust covariance, variance model, bootstrap |
| Within-cluster dependence | Cluster-robust SE, mixed model, GEE, cluster bootstrap |
| Influential observations | Robust fit, leave-one-cluster-out analysis |
| Missing outcomes | MI under MAR plus delta/tipping-point MNAR analysis |
| Confounding | Alternative justified sets, weighting/outcome models, bias analysis |
| Poor overlap | Trimming, overlap weights, target-population revision |
| Outcome definition | Prespecified alternative operationalizations |
| Multiple testing | FWER/FDR procedures and hierarchical models |
| Distributional assumptions | Alternative likelihood, permutation, bootstrap |

A robustness claim is credible when conclusions remain substantively similar across plausible assumptions, not merely when all variants cross the same p-value threshold. Display estimates and intervals across specifications in a coefficient or multiverse plot and explain why each specification is scientifically plausible.

## Publication-quality reporting

### Results table

A machine-generated results table should include:

| Field | Content |
|---|---|
| Estimand | Human-readable contrast and time horizon |
| Estimate | Effect in scientific units |
| Interval | 95% CI or credible interval, clearly labeled |
| Scale | Difference, ratio, log scale, probability, or rate |
| Model | Family, link, covariance/cluster structure |
| Adjustment | Prespecified covariates and coding |
| Sample | Observations, independent units, events, clusters |
| Missing data | Complete case, MI details, likelihood, or weighting |
| Multiplicity | Family and procedure, if applicable |
| Sensitivity | Direction and materiality of changes |

Keep model coefficients separate from translated quantities. For nonlinear models, report marginal predictions or contrasts at scientifically relevant covariate distributions when these match the estimand better than raw link-scale coefficients.

### Methods checklist

The final methods section should state:

- Study design, sampling/assignment, unit, population, and dates.
- Outcome, exposure, covariates, confounders, and effect modifiers.
- Data exclusions, derivations, units, and quality checks.
- Missing-data mechanism assumptions and analysis.
- Model family, link, formula, reference levels, nonlinear terms, interactions, and offsets.
- Dependence and covariance handling.
- Estimand, interval procedure, test direction, and significance criterion if used.
- Multiplicity procedure and hypothesis family.
- Diagnostic and sensitivity analyses.
- Software, versions, seeds, and repository/data availability.

Transparent observational reporting specifically calls for statistical methods used to control confounding, subgroup and interaction methods, participant characteristics, and both unadjusted and adjusted estimates with precision.[^3]

## End-to-end analysis skeleton

The following template separates validation, descriptive analysis, estimation, diagnostics, and reporting. It is intentionally generic and must be adapted to the design.

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

# 1. Load without mutating raw evidence
raw = pd.read_parquet("data/raw/study.parquet")

# 2. Validate schema and keys
assert raw["subject_id"].notna().all()
assert not raw["subject_id"].duplicated().any()
assert raw["group"].isin(["control", "treated"]).all()

# 3. Derive the analysis table through named, testable transformations
analysis = (
    raw.assign(
        group=lambda d: pd.Categorical(
            d["group"], categories=["control", "treated"]
        ),
        age_centered=lambda d: d["age"] - d["age"].mean(),
    )
)

# 4. Record exclusions and denominators
flow = {
    "raw_n": len(raw),
    "outcome_observed_n": int(analysis["outcome"].notna().sum()),
}

# 5. Descriptive table
summary = (
    analysis.groupby("group", observed=True)["outcome"]
    .agg(n="count", mean="mean", sd="std", median="median")
)
summary.to_csv(OUT / "descriptive.csv")

# 6. Primary model; covariance must match the design
fit = smf.ols(
    "outcome ~ C(group) + baseline + age_centered + C(site)",
    data=analysis,
    missing="drop",
).fit(cov_type="HC3")

# 7. Structured output, not copied console text
coef = fit.summary2().tables[^1]
coef.to_csv(OUT / "primary_model.csv")

# 8. Diagnostics and sensitivity models
influence = fit.get_influence().summary_frame()
influence.to_parquet(OUT / "influence.parquet")

sensitivity = smf.ols(
    "outcome ~ C(group) + baseline + age_centered",
    data=analysis,
    missing="drop",
).fit(cov_type="HC3")
sensitivity.summary2().tables[^1].to_csv(OUT / "sensitivity_model.csv")

# 9. Provenance
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

For clustered data, replace `HC3` with a design-appropriate cluster covariance or model. For missing data, replace implicit listwise deletion with the prespecified complete-case, likelihood, weighting, or multiple-imputation analysis. For prediction, put every learned transformation inside a cross-validation pipeline.

## Verification strategy

Scientific code requires tests at three levels:

### Data tests

- Raw input hashes and expected file inventory.
- Schema, ranges, categories, units, uniqueness, and foreign keys.
- Expected join cardinalities and row-count reconciliation.
- Explicit tests for historically observed data errors.

### Statistical tests

- Hand-check small deterministic examples.
- Compare selected estimates against another trusted implementation.
- Verify invariances: row order, category relabeling, unit conversion, or duplicated irrelevant columns should not alter results unexpectedly.
- Use simulation to assess bias, interval coverage, Type I error, power, and convergence under known data-generating processes.
- Test edge cases such as separation, zero events, empty categories, singular matrices, and degenerate bootstrap samples.

### Pipeline tests

- Start from a clean environment and rebuild every artifact.
- Execute notebooks top-to-bottom.
- Confirm deterministic outputs where algorithms permit.
- Check that no script writes to raw data.
- Fail the workflow on validation errors, model convergence warnings, or stale inputs.

The notebook should not be the only executable record. A single command such as `make report`, `snakemake`, or a task runner should reconstruct the analysis from declared inputs.

## Common failure modes

| Failure | Why it is scientifically dangerous | Better practice |
|---|---|---|
| Treating rows as independent | Underestimates uncertainty | Model or resample at the true independent-unit level |
| Dropping missing rows silently | Changes the target population and may bias effects | Report flow; justify mechanism; use sensitivity analysis |
| Mean imputation before inference | Distorts distributions and understates uncertainty | MI, likelihood, weighting, or justified complete-case analysis |
| Preprocessing before splitting | Leaks information and inflates performance | Fit transformations inside each training fold[^20] |
| Selecting covariates by univariate p-values | Produces unstable adjustment and can miss confounding | Use design/causal knowledge and prespecification |
| Dichotomizing continuous variables | Loses information and creates artificial thresholds | Model nonlinear continuous effects |
| Testing normality to choose every test | Confuses outcome shape with sampling behavior and model assumptions | Inspect residual/design assumptions; use robust methods |
| Interpreting p > 0.05 as no effect | Absence of evidence is not equivalence | Report estimate and interval; use equivalence/noninferiority design if relevant |
| Interpreting p < 0.05 as important | Significance does not measure magnitude | Compare effect and interval with a meaningful threshold[^1] |
| Reporting only AUC | Omits calibration and decision value | Add proper scores, calibration, and utility |
| Ignoring multiple analyses | Inflates false discoveries | Define families, adjust, and disclose all analyses |
| Deleting influential points automatically | Can remove real scientific signal | Verify, diagnose, and perform sensitivity analyses |
| Using robust SE as a universal repair | Only changes covariance estimation | Reconsider mean model, dependence, confounding, and measurement |
| Claiming causality from adjusted regression | Adjustment alone does not establish identification | State causal assumptions and assess overlap/sensitivity |
| Publishing an unpinned notebook | Hidden state and dependency drift impede reproduction | Lock environment and execute cleanly[^7][^2] |

## Recommended operating procedure

1. **Write the scientific specification.** Define design, population, unit, outcome, exposure, estimand, causal or predictive purpose, and primary contrasts.
2. **Freeze and fingerprint inputs.** Preserve raw files, data dictionaries, collection metadata, and hashes.
3. **Build an executable schema.** Validate keys, dtypes, units, ranges, categories, dates, and table relationships.
4. **Create a provenance-preserving analytic table.** Derive variables in named functions and log all exclusions.
5. **Audit quality and missingness.** Report patterns by scientifically relevant groups and retain reason codes.
6. **Perform structured EDA.** Examine distributions, nonlinearities, clusters, time, batches, and influence without converting every observation into a hypothesis test.
7. **Fit the prespecified primary model.** Align outcome family, dependence, functional form, and covariance with the design.
8. **Quantify effects and uncertainty.** Report scientifically interpretable contrasts and intervals, with p-values in a supporting role.
9. **Run diagnostics and sensitivity analyses.** Challenge missingness, dependence, functional form, influence, multiplicity, and identification assumptions.
10. **Validate prediction honestly when relevant.** Place all adaptive steps inside grouped, temporal, or nested resampling as required.
11. **Generate every result programmatically.** Tables, figures, flow counts, and prose-facing numbers should share one source of truth.
12. **Rebuild in a clean environment.** Archive code, configuration, environment, logs, and legally shareable data or a transparent access procedure.

## Final checklist

### Scientific validity

- [ ] The research question and estimand are explicit.
- [ ] The unit of analysis matches the unit of independence.
- [ ] Causal, predictive, descriptive, and inferential claims are distinguished.
- [ ] Covariates and interactions have scientific justification.
- [ ] The model’s outcome family, link, and dependence structure are defensible.
- [ ] Effects and uncertainty—not only p-values—are reported.
- [ ] Multiplicity and selective analysis are addressed.

### Data integrity

- [ ] Raw data are immutable and fingerprinted.
- [ ] A schema validates types, units, ranges, keys, and categories.
- [ ] Join cardinality and row-count reconciliation are tested.
- [ ] Missing-value codes and reasons are preserved.
- [ ] Exclusions and corrections are auditable.

### Diagnostics

- [ ] Functional form, variance, dependence, and influence are examined.
- [ ] Resampling preserves pairing, clusters, and temporal structure.
- [ ] Predictive evaluation is out of sample and leakage-free.
- [ ] Bayesian computation and posterior predictive behavior are checked where applicable.
- [ ] Sensitivity analyses target plausible assumption failures.

### Reproducibility

- [ ] Code, configuration, and execution order are versioned.
- [ ] Dependencies are locked and software versions reported.
- [ ] Random generators and seeds are explicit.
- [ ] The workflow runs from a clean environment with one command.
- [ ] Tables and figures are generated rather than manually edited.
- [ ] Data and code are shared or access restrictions are documented.

## Conclusion

Scientific statistical analysis of tabular data with Python is strongest when the dataframe is treated as the observable endpoint of a study design rather than as an anonymous matrix. The decisive steps occur before and after model fitting: defining the estimand, preserving design structure, validating the schema, reasoning about missingness and confounding, stress-testing assumptions, and making the computation reproducible.

Python’s ecosystem provides the required numerical, statistical, predictive, Bayesian, and workflow components. SciPy supports bootstrap, permutation, and Monte Carlo procedures; statsmodels offers interpretable regression and covariance tools; scikit-learn provides leakage-resistant pipelines; PyMC supports model criticism through predictive simulation; and pandas supplies explicit missing-value and dtype handling. These tools become scientific only when embedded in a transparent chain of evidence whose assumptions, decisions, and limitations can be audited and challenged.[^10][^19][^16][^20][^21]

---

## References

1. [[PDF] P-ValueStatement.pdf - American Statistical Association](https://www.amstat.org/asa/files/pdfs/P-ValueStatement.pdf) - 2. P-values do not measure the probability that the studied hypothesis is true, or the 
...
importan...

2. [Reproducibility standards for machine learning in the life sciences - Nature Methods](https://www.nature.com/articles/s41592-021-01256-7) - Accordingly, the silver standard requires that authors record the order in which one should run thei...

3. [www.equator-network.org › wp-content › uploadsStrengthening the Reporting of Observational Studies in ...](https://www.equator-network.org/wp-content/uploads/2015/10/Strengthening_the_Reporting_of_Observational-Studies-in-Epidemiology-STROBE.pdf) - (a) Describe all statistical methods, including those used to control for confounding

4. [CONSORT](https://www.equator-network.org/wp-content/uploads/2009/09/STROBE-practical.pdf) - Clearly define all outcomes, exposures, predictors, potential confounders, and effect modifiers.

5. [www.statsmodels.org › dev › mixed_glmGeneralized Linear Mixed Effects Models — statsmodels 0.15.1...](https://www.statsmodels.org/dev/mixed_glm.html) - Generalized Linear Mixed Effects (GLIMMIX) models are generalized
linear models with random effects ...

6. [API Reference — statsmodels 0.15.1 (+573)](https://www.statsmodels.org/devel/api.html) - |`PoissonBayesMixedGLM`(endog, exog, exog_vc, ident)|Generalized Linear Mixed Model with Bayesian es...

7. [Ten Simple Rules for Reproducible Research in Jupyter ...](https://arxiv.org/pdf/1810.08055.pdf) - Strive to make your data, or a sample of your data, publicly available along with the notebook.

8. [Using Jupyter for reproducible](https://arxiv.org/pdf/2102.09562.pdf) - study within a single notebook and provides a
complete and executable record of the process.

9. [AiiDA 1.0, a scalable computational infrastructure for automated reproducible workflows and data provenance](https://www.nature.com/articles/s41597-020-00638-4) - In computational science, for a result to be reproducible, it should be possible to exactly retrace ...

10. [pandas.pydata.org › user_guide › missing_dataWorking with missing data — pandas 3.0.6 documentation](https://pandas.pydata.org/pandas-docs/stable/user_guide/missing_data.html) - `NA` is a scalar (singleton) used to represent missing values for nullable dtypes.

11. [Working with missing data — pandas 3.0.6 documentation - PyData |](https://pandas.pydata.org/docs/user_guide/missing_data.html) - `NA` is a scalar (singleton) used to represent missing values for nullable dtypes.

12. [Transparent reporting of missing outcome data in clinical trials: applying the general principles of CONSORT 2010](https://ebm.bmj.com/content/19/5/161) - Multiple imputation, an approach whereby regression techniques are used to predict the missing outco...

13. [item-27c-missing-data - SPIRIT CONSORT](https://www.consort-spirit.org/spiriteande27c/item-27c-missing-data) - It is often recommended that participants with missing data be included in the analysis using multip...

14. [1](https://researchonline.lshtm.ac.uk/id/eprint/4646052/1/Missing%20data%20in%20clinical%20research%20an%20integrated%20approach_GREEN%20AAM.pdf) - Then, we estimate the treatment effect from each imputed dataset, before combining the results using...

15. [Lecture 6: Handling Missing Data - University of Washington](https://si.biostat.washington.edu/sites/default/files/modules/SISCER_Mod13_Day3.pdf) - ˆβMI = Avg(ˆβ m)
...
analysis
▶Address extent to which results may be biased due to missing

16. [Regression Diagnostics and Specification Tests](https://www.statsmodels.org/v0.10.2/diagnostic.html) - to use robust methods, for example robust regression or robust covariance
(sandwich) estimators.

17. [The ASA s Statement on p Values Context Process and Purpose](https://math.montana.edu/ahoegh/teaching/stat491/notes/ASA_pvalues.pdf) - should not be based only on whether a p-value passes a specific threshold.

18. [bootstrap — SciPy v1.15.1 Manual](https://docs.scipy.org/doc//scipy-1.15.1/reference/generated/scipy.stats.bootstrap.html) - Two more common methods are available, `'basic'` (‘reverse percentile’) and `'BCa'` (‘bias-corrected...

19. [Statistical functions (scipy.stats) — SciPy v1.13.0 Manual](https://docs.scipy.org/doc/scipy-1.13.0/reference/stats.html) - |`permutation_test`(data, statistic, *[, ...])|Performs a permutation test of a given statistic on p...

20. [11. Common pitfalls and recommended practices](https://scikit-learn.org/1.7/common_pitfalls.html) - Data leakage occurs when information that would not be available at prediction
time is used when bui...

21. [Prior and Posterior Predictive Checks — PyMC v5.10.4 documentation](https://www.pymc.io/projects/docs/en/v5.10.4/learn/core_notebooks/posterior_predictive.html) - Posterior predictive checks (PPCs) are a great way to validate a model.

22. [Glossary — PyMC 6.3.2 documentation](https://www.pymc.io/projects/docs/en/stable/glossary.html) - When such predictions are used to check the internal consistency of the models by comparing it with ...

23. [statsmodels.stats.multitest.multipletests#](https://www.statsmodels.org/stable//generated/statsmodels.stats.multitest.multipletests.html) - The ‘fdr_gbs’ procedure is not verified against another package, p-values are derived from scratch a...

24. [statsmodels.stats.multitest.multipletests — statsmodels 0.15. ...](https://www.statsmodels.org/dev/generated/statsmodels.stats.multitest.multipletests.html) - The ‘fdr_gbs’ procedure is not verified against another package, p-values are derived from scratch a...

25. [Transparent and complete reporting of confounding in ... - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10242947/) - Because bias due to confounding is a major limitation of observational research, the STROBE checklis...

26. [STROBE checklist](https://www.equator-network.org/wp-content/uploads/2015/10/STROBE_checklist_cohort.docx) - Statistical methods            12                                                             (*a*) ...

27. [statsmodels.stats.power — statsmodels 0.15.0](https://www.statsmodels.org/stable/_modules/statsmodels/stats/power.html) - effect_size : float
Standardized effect size, mean divided by the standard deviation.

