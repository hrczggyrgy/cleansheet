# Statistical Analysis of Tabular Data

## Executive overview

Statistical analysis turns a table of observations into defensible answers. The essential sequence is: define the decision, understand what each row and column means, check data quality, describe patterns visually and numerically, quantify uncertainty, compare or model only when appropriate, test how sensitive the answer is to reasonable alternatives, and communicate the result with limitations.

The most important lesson is that sophisticated calculations cannot repair a poorly framed question or unrepresentative data. Sample adequacy depends not only on sample size, but also on representativeness, population variability, and the precision required; survey results can additionally suffer from nonresponse, coverage, measurement, coding, and processing errors.[^1][^2]

For most non-technical readers, a trustworthy analysis should answer five questions:

- **What happened?** Describe counts, percentages, typical values, variation, and unusual cases.
- **How certain are we?** Show intervals or other uncertainty measures rather than a single number alone.
- **What differs or moves together?** Compare relevant groups and examine relationships.
- **What might explain the pattern?** Consider competing explanations, data collection, and possible confounders.
- **What action is justified?** Translate the effect into practical units and state what the analysis cannot establish.

## Understanding the table

A tabular dataset is a rectangle in which rows usually represent cases—such as customers, orders, patients, products, or days—and columns represent recorded attributes. Good spreadsheet practice uses one observation per row, one variable per column, one item per cell, a single header row, consistent missing-value codes, a data dictionary, and a separate untouched raw-data file.[^3][^4]

### The unit of analysis

The **unit of analysis** is the thing each row represents. If rows are transactions, then one customer may appear many times; treating those rows as independent customers exaggerates the effective amount of information. Repeated measurements, households, stores, schools, and other clusters often require aggregation, cluster-aware uncertainty estimates, or multilevel methods rather than an ordinary test that assumes every row is unrelated to every other row.[^5]

Before calculating anything, write a one-sentence row definition: “Each row is one customer,” “Each row is one invoice,” or “Each row is one store-month.” Then identify the population to which conclusions should apply. A convenient file is not automatically a representative sample of that population.

### Common column types

| Column type | Plain-language meaning | Examples | Useful first summaries |
|---|---|---|---|
| Identifier | A label, not a measured quantity | Customer ID, invoice number | Uniqueness, duplicates, missing IDs |
| Category | Membership in an unordered group | Region, product type, channel | Counts and percentages |
| Ordered category | A ranked group with unequal or unknown gaps | Low/medium/high, satisfaction level | Counts, percentages, median category |
| Numeric measure | A quantity with meaningful differences | Revenue, age, delivery time | Mean, median, quartiles, spread |
| Binary flag | A yes/no condition | Churned, defect, response | Count and proportion |
| Date or time | When something occurred | Order date, month, timestamp | Coverage period, gaps, trends, seasonality |
| Free text | Unstructured language | Complaint, comment | Coding or text analysis before statistics |

Do not treat an identifier as a number merely because it contains digits. Likewise, category codes such as 1, 2, and 3 are labels unless their numerical spacing has a real interpretation.

### A data dictionary

A short data dictionary prevents many errors. For every field, record its business definition, unit, permitted values, time window, source, missing-value meaning, and known quality issues. Also identify derived columns, such as margin percentage or customer age, and write down the exact calculation so that another person can reproduce it.

## Start with the question

Analysis should begin with a decision, not with a menu of tests. A useful question names the population, outcome, comparison or exposure, time period, and intended action—for example: “Among active retail customers in 2026, how much higher is median annual grocery spending for Channel B than Channel A, and is the difference large enough to justify separate campaigns?”

Distinguish four broad goals:

| Goal | Question form | Typical output | Main caution |
|---|---|---|---|
| Description | What is happening? | Counts, rates, distributions, trends | Do not generalize beyond the observed population without a sampling basis |
| Comparison | How do groups differ? | Difference, ratio, uncertainty interval | Groups may differ for reasons other than the label being compared |
| Association | What moves together? | Correlation or adjusted model | Association is not automatically causation |
| Prediction | What is likely next? | Forecast, probability, error on unseen data | Accuracy must be evaluated on data not used to fit the model |

Write the main question and planned outcome before examining dozens of relationships. Exploring is valuable, but exploratory findings should be labeled as such and ideally checked on new data; otherwise, chance patterns can be mistaken for stable discoveries.

## Audit data quality

Data cleaning is part of the analysis because every correction changes the evidence. Preserve the original file, perform cleaning in a separate reproducible step, and keep an audit log of exclusions, recodes, joins, and imputations.

### Structural checks

Begin with a compact quality report:

- Number of rows and columns.
- Exact row definition and intended unique key.
- Duplicate keys and duplicated full rows.
- Missing count and percentage for every field.
- Values outside valid ranges or impossible combinations.
- Category spelling and capitalization variants.
- Date coverage, missing periods, and future or impossible dates.
- Unit consistency, such as euros versus thousands of euros.
- Join success rates and rows lost or multiplied after merging.
- Whether totals reconcile with a trusted control source.

A duplicated key does not always mean an error: it may reveal that the assumed row definition was wrong. Similarly, an impossible negative quantity may be a return, a correction, or a coding problem. Investigate the generating process before changing the value.

### Missing values

Missing values are information, not merely blank cells. Report how much is missing, where it occurs, why it may be missing, and whether rows with missing values differ from complete rows. Recommended reporting includes missing counts by variable, reasons when known, comparisons of complete and incomplete cases, the handling method, and its assumptions.[^6][^7]

| Situation | Reasonable response | Risk to explain |
|---|---|---|
| A few accidental blanks with no visible pattern | Complete-case analysis may be adequate | Reduced sample size and precision |
| Missingness related to observed fields | Adjustment or multiple imputation may help | Results depend on the model and “missing at random” assumption |
| Missingness may depend on the unobserved value itself | Sensitivity analysis and expert input | The missingness mechanism cannot be verified from observed data alone |
| Blank means “not applicable” | Encode separately from “unknown” | Combining the two changes the meaning of rates and averages |

Multiple imputation creates several plausible completed datasets, analyzes each, and combines the results so that uncertainty about missing values is represented. It is not a universal remedy: the choice between complete-case analysis and imputation depends on the outcome, missingness pattern, available auxiliary information, and assumptions; no single missing-percentage threshold determines the right method.[^8][^7]

### Outliers

An outlier is an observation far from most others. It may be an error, a valid rare event, or evidence that the population contains distinct processes. NIST advises correcting or removing a value when it is demonstrably erroneous, but not simply deleting a valid unusual observation; robust methods or separate analyses may be more appropriate.[^9]

Use histograms, box plots, scatterplots, and record-level investigation together. Report results with and without influential observations when the decision changes, and explain which version better matches the business question. An outlier rule should flag cases for review—not automatically rewrite reality.

## Explore before testing

Exploratory data analysis combines graphs and numerical summaries to reveal shape, spread, shifts, non-random patterns, and possible assumption failures. NIST’s framework emphasizes techniques such as histograms, box plots, scatterplots, run-sequence plots, and quantitative measures rather than relying on one summary number.[^10][^11]

### One column at a time

For categories, show counts and percentages, including missing or “unknown.” For numeric variables, show at least the valid count, median, quartiles, minimum, maximum, mean, and standard deviation; then add a histogram or box plot. For time fields, plot values in chronological order and look for trend, seasonality, gaps, and abrupt changes.

The **mean** adds all values and divides by their count; the **median** is the middle value after sorting. The mean is informative for totals and symmetric distributions, but extreme values and skew pull it toward the long tail; the median is more resistant. For skewed or heavy-tailed data, reporting both often communicates the distribution better than choosing only one.[^12][^13]

| Measure | What it tells a reader | Main limitation |
|---|---|---|
| Mean | Average amount per case | Sensitive to extreme values and skew |
| Median | Middle case | Does not reflect the magnitude of extremes |
| Standard deviation | Typical spread around the mean | Harder to interpret for strongly skewed data |
| Interquartile range | Width of the middle 50% | Ignores tail magnitude |
| Minimum and maximum | Observed endpoints | Highly sensitive to errors and rare cases |
| Percentiles | Practical thresholds, such as the 90th percentile | Require enough observations for stable tail estimates |

### Two columns together

Choose displays based on variable types:

- Category versus category: cross-tabulation, row percentages, and a grouped bar chart.
- Numeric versus category: group counts, medians and means, box plots, and differences with intervals.
- Numeric versus numeric: scatterplot, correlation, and possibly a fitted curve.
- Numeric versus time: line plot with relevant aggregation and seasonal comparisons.

Correlation measures the strength and direction of a relationship, usually linear for Pearson correlation, and ranges from -1 to 1. Spearman correlation works on ranks and can be useful for ordered data, non-linear monotonic relationships, or settings where normality is implausible.[^14][^15]

Always inspect the scatterplot. The same correlation can hide curves, separate clusters, changing variance, or a handful of influential points. Most importantly, correlation does not show that changing one variable will change the other.

## Quantify uncertainty

A sample statistic is an estimate, not the population truth. A confidence interval gives a range produced by a method designed to capture the target value at a stated long-run rate; a 95% interval does not mean that 95% of individual observations lie inside it, nor does it remove nonsampling biases.[^16][^17]

Intervals should accompany the quantities decision-makers care about: means, medians, proportions, differences, ratios, model coefficients, and predictions. Wider intervals mean less precision. Larger, well-designed samples generally narrow sampling uncertainty, but very large biased samples can remain confidently wrong.

### Practical versus statistical importance

An **effect size** expresses how large a difference or relationship is in meaningful units. Examples include “€12 more per order,” “4 percentage points lower churn,” or “1.3 times the defect rate.” A p-value instead describes how incompatible the observed data are with a specified null model, assuming the model’s conditions hold.[^18]

The American Statistical Association warns that p-values do not state the probability that a hypothesis is true, do not measure effect size or practical importance, and should not be the sole basis for a scientific or business decision. Report the estimate, effect size, interval, exact p-value when relevant, assumptions, and decision context together.[^19][^20]

If many hypotheses are tested, some small p-values appear by chance. Either pre-specify a small set of primary questions or use a multiplicity adjustment such as Holm for family-wise error control or Benjamini–Hochberg for false discovery rate control; disclose the complete family of tests rather than only favorable results.[^21][^18]

## Choose the method

The right method follows from the question, outcome type, group structure, and assumptions. The following table is an orientation guide, not an automatic selector; more than one method can be legitimate, and the estimand—the exact quantity the analysis intends to estimate—comes first.[^22]

| Question | Simple starting method | What to report |
|---|---|---|
| What proportion has an outcome? | Proportion with confidence interval | Numerator, denominator, percentage, interval |
| Do two independent groups differ in a numeric outcome? | Welch two-sample t-test for means; rank-based alternative for distributional shifts | Each group’s count and summary, difference, interval, effect size |
| Do the same cases change before versus after? | Paired test or paired regression | Paired count, within-case change, interval |
| Do three or more groups differ? | ANOVA/regression; robust or rank-based alternative when justified | Group summaries, overall test, adjusted pairwise comparisons |
| Are two categories associated? | Chi-square or Fisher’s exact test | Contingency table, row percentages, effect measure, interval |
| Are two numeric variables related? | Correlation and regression | Plot, coefficient, interval, diagnostics |
| Is an outcome affected by several factors? | Linear, logistic, count, or other regression matched to the outcome | Adjusted effects, intervals, assumptions, predictive performance if relevant |
| What happens over time? | Time-series description or forecasting | Trend/seasonality, forecast horizon, backtest error, prediction intervals |

Welch’s t-test compares independent-group means without assuming equal population variances. A Mann–Whitney test compares independent distributions using ranks and is often used for location differences, but it should not automatically be described as a test of medians unless the distributional conditions justify that interpretation.[^23][^24]

### Regression in plain language

Regression estimates how an outcome changes as one or more explanatory variables change while holding the other included variables constant. Linear regression suits a roughly continuous outcome; logistic regression suits a yes/no outcome; count models suit event counts; survival models suit time until an event.

“Adjusted for” does not mean “all bias removed.” An adjusted result is conditional on the selected variables, their measurement quality, the model form, and the absence of important omitted structure. Classical regression and ANOVA commonly assume residuals are approximately independent, centered around zero, and have stable variance; residual plots should be used to check for remaining patterns.[^25][^26]

### Causality

A statistically significant association can arise from a causal effect, chance, selection bias, measurement bias, confounding, or analysis choices. Statistical significance alone does not establish cause and effect.[^27]

Causal language requires a credible design and assumptions: randomized assignment where feasible, or careful observational methods with a defensible comparison group, timing, confounder control, and sensitivity analysis. In routine tabular analysis, prefer “associated with,” “linked to,” or “predicts” unless the design supports stronger wording.

## Time and prediction

Randomly splitting rows is inappropriate when the task predicts the future, because it lets later information help evaluate an earlier prediction. Train on earlier periods and evaluate on later periods, using rolling or expanding windows when enough history exists. Time-series cross-validation and chronological holdouts allow competing forecast models to be compared on genuinely later observations.[^28]

For any predictive model, separate model development from final evaluation. Preprocessing—imputation, scaling, category encoding, and feature selection—must be learned only from training data; allowing test data to influence these steps creates leakage and overly optimistic performance estimates.[^29]

Report performance in terms users understand. For numeric outcomes, consider mean absolute error and show the distribution of errors; for yes/no outcomes, include sensitivity, specificity, precision, recall, calibration, and the consequences of false positives and false negatives. A model can rank cases well while producing poorly calibrated probabilities, so performance should match the intended decision.

## Worked example

Consider the public UCI Wholesale Customers dataset. It contains 440 distributor clients, annual monetary-unit spending in six product categories, customer channel, and region, with no missing values reported by the repository.[^30]

The source reports strong right-skew potential: for Fresh spending, the mean is 12,000.30 while the maximum is 112,151; other product categories similarly have standard deviations comparable to or larger than their means. The dataset includes 298 hotel/restaurant/café customers and 142 retail customers, and regional counts of 77 Lisbon, 47 Oporto, and 316 other.[^30]

A non-technical analysis could proceed as follows:

1. **Define the decision.** Determine whether channel-specific purchasing patterns are large and stable enough to justify different account strategies.
2. **Confirm structure.** Treat each row as one customer; verify that channel and region codes match the metadata.
3. **Describe the mix.** Report channel and region counts and percentages so readers see the imbalance.
4. **Inspect distributions.** Plot each spending field by channel; report median and interquartile range alongside mean and standard deviation because extreme spenders can dominate averages.
5. **Estimate differences.** For every product category, report the channel difference in a clearly defined measure, with a confidence interval and effect size.
6. **Control multiplicity.** Mark one or two primary product categories in advance or adjust the set of six comparisons.
7. **Check robustness.** Compare raw-scale results with rank-based or log-scale analyses; show whether conclusions depend on a few very large customers.
8. **Avoid causal claims.** The data can describe channel differences but cannot prove that switching channel causes spending to change.

A decision-ready sentence would look like this: “Retail customers had a higher typical grocery spend than hospitality customers by an estimated amount of X monetary units; the uncertainty interval was Y to Z, and the result remained similar under a robust analysis.” The placeholders must be filled from the actual analysis rather than invented.

## Reporting for leaders

Lead with the answer, then the evidence, then the caveat. A good executive result can fit into four lines:

- **Finding:** State the direction and size in business units.
- **Uncertainty:** Give the interval and sample size.
- **Meaning:** Compare the effect with a practical threshold, cost, target, or baseline.
- **Limitation:** Name the most important reason the result may not generalize or be causal.

Prefer plain labels such as “typical customer,” “middle 50%,” and “uncertainty range,” while placing formal terms in parentheses once. Avoid “proved,” “no effect,” and “significant” without qualification. A non-significant result may reflect low precision; a statistically significant result may still be too small to matter.[^31][^20]

### Minimum result table

| Item | What to include |
|---|---|
| Scope | Population, period, inclusion and exclusion rules |
| Data | Source, row definition, sample size, missingness, weighting |
| Estimate | Effect in natural units and relative units when helpful |
| Uncertainty | Confidence or credible interval; prediction interval for forecasts |
| Method | Test or model and why it matches the question |
| Diagnostics | Key assumption and robustness checks |
| Limitations | Bias, confounding, measurement, missingness, generalizability |
| Decision | Recommended action, threshold, and monitoring plan |

## Reproducible workflow

A defensible project leaves a trail from raw data to final statement:

1. Freeze and label the raw input; never overwrite it.
2. Write the question, target population, outcome, unit of analysis, and decision threshold.
3. Create the data dictionary and quality report.
4. Script or record all transformations, exclusions, joins, and recodes.
5. Produce descriptive tables and graphs before formal testing.
6. Select the primary estimand and method; document assumptions.
7. Quantify effect size and uncertainty, not only p-values.
8. Run diagnostics and sensitivity analyses.
9. Separate exploratory findings from pre-specified or confirmed findings.
10. Save software versions, analysis settings, and a refreshable final report.

For point-and-click work, jamovi offers a free spreadsheet-style interface backed by R and can save data, analyses, and results together; JASP provides a free graphical interface for classical and Bayesian procedures. Ease of use does not remove the need to understand the row definition, assumptions, and interpretation.[^32][^33]

## Common failure modes

| Failure | Why it misleads | Better practice |
|---|---|---|
| Reporting only an average | Hides skew, spread, and subgroups | Add median, quartiles, distribution plot, and count |
| Deleting all outliers | Removes valid rare cases and understates risk | Investigate, justify corrections, and use robust checks |
| Filling blanks with zero | Confuses “unknown” with a real zero | Preserve missingness and model or report it explicitly |
| Testing every column pair | Produces chance findings | Pre-specify priorities or adjust for multiplicity |
| Treating repeated rows as independent | Makes uncertainty look too small | Aggregate or use cluster/repeated-measures methods |
| Using p < 0.05 as the decision | Ignores magnitude, uncertainty, and cost | Report effects, intervals, practical thresholds, and trade-offs |
| Claiming causation from correlation | Ignores confounding and selection | Use cautious language and a causal design |
| Randomly splitting time data | Leaks future patterns into evaluation | Use chronological validation |
| Cleaning before the train/test split | Leaks test information | Fit every learned preprocessing step on training data only |
| Hiding exclusions or failed analyses | Prevents audit and inflates confidence | Report the full analytical path and sensitivity checks |

## Final checklist

Before release, confirm that a non-technical reader can answer each question:

- What does one row represent?
- Who or what is represented—and who is not?
- What time period and units apply?
- How much data is missing, duplicated, invalid, or excluded?
- What is the main question and primary outcome?
- What do the distributions look like, not just the averages?
- What is the effect in practical units?
- How uncertain is the estimate?
- Which assumptions could change the answer?
- Were multiple comparisons, repeated observations, and time order handled correctly?
- Is the statement descriptive, associational, predictive, or genuinely causal?
- Can another analyst reproduce the result from the raw input?

If any answer is unclear, the analysis is not yet ready for a decision. Statistical rigor is less about choosing the most advanced technique than about preserving meaning from the original rows through to the final claim.

---

## References

1. [Data Quality - U.S. Census Bureau](https://www.census.gov/programs-surveys/gus/technical-documentation/methodology/data-quality.html) - However, the data are subject to nonsampling error, which includes all other sources of survey error...

2. [3.1.3.4. Populations and Sampling](https://www.itl.nist.gov/div898/handbook/ppc/section1/ppc134.htm) - The other option is to survey a small group (Sample) of the people whose opinions you are interested...

3. [Data organization in spreadsheets](https://gzahn.github.io/data-course/Readings/Broman_and_Woo_2017_Data_organization_in_spreadsheets.pdf) - Focusing on the data entry and storage aspects, this paper offers prac- tical recommendations for or...

4. [Paper_DataOrg/manuscript.md at master - GitHub](https://github.com/kbroman/Paper_DataOrg/blob/master/manuscript.md) - |title|Data organization in spreadsheets|
...
|author|<table><tr><td> <table><tr><td>name</td><td>af...

5. [Mixed Effects Cox Regression | R Data Analysis Examples](https://stats.oarc.ucla.edu/r/dae/mixed-effects-cox-regression/) - when there are repeated measures on an individual, individuals
nested within some other hierarchy, o...

6. [A review of the reporting and handling of missing data in cohort studies with repeated assessment of exposure measures - PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3464662/) - Multiple imputation for missing data in epidemiological and clinical research: potential and pitfall...

7. [Multiple imputation for missing data in epidemiological ... - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC2714692/) - by JAC Sterne · 2009 · Cited by 9412 — Abstract. Most studies have some missing data. Jonathan Stern...

8. [Accounting for missing data in statistical analyses - PMC - NIH](https://pmc.ncbi.nlm.nih.gov/articles/PMC6693809/) - Multiple imputation for missing data in epidemiological and clinical research: potential and pitfall...

9. [1.3.5.17. Detection of Outliers](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm) - Detection of Outliers · An outlier may indicate bad data. For example, the data may have been coded ...

10. [1. Exploratory Data Analysis - NIST](https://www.itl.nist.gov/div898/handbook/eda/eda_d.htm) - 1. Measures of Location [1.3.5.1.]

11. [1.4.1.](https://www.itl.nist.gov/div898//handbook/eda/section4/eda41.htm) - run sequence plot which is useful for detecting shifts of location or scale 2.

12. [1.3.3.13.6. Histogram Interpretation: Skewed (= Non-Normal) Right](https://www.itl.nist.gov/div898/handbook/eda/section3/eda33d6.htm) - As a third choice, others may argue that the median (= that value on the horizontal axis which has e...

13. [Backtesting Terms A to Z: Plain-English Definitions](https://tradelyze.io/learn/backtesting-glossary/) - - **Median** The middle value once the values are sorted: half are smaller and half are larger.

14. [SPEARMAN DISSIMILARITY](https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/speardis.htm) - # SPEARMAN DISSIMILARITY Name: - - SPEARMAN SIMILARITY (LET) - - Type: Purpose: - Spearman rank corr...

15. [Glossary](https://www.itl.nist.gov/div898/handbook/glossary.htm) - The usual correlation coefficient, called the Pearson correlation coefficient, ranges from -1 to 1.

16. [Confidence interval | Definition, Interpretation, Example ...](https://www.britannica.com/science/confidence-interval) - A popular framework adheres to the following template: “We are [level of confidence] percent confide...

17. [Small Business Pulse Survey Phases 5 through 8 Nonresponse ...](https://portal.census.gov/pulse/data/downloads/research/SBPS-Nonresponse-Bias-Analysis-Phases-5-through-8-Final.pdf) - The sampling error of an estimate based on a probability sample survey is the difference between the...

18. [[PDF] ASA Statement on Statistical Significance and P-Values](https://www.burtthompson.net/uploads/9/6/8/4/9684389/wasserstein-2016__asa_p-value_statement.pdf) - ASA Statement on Statistical Significance and P-Values
...
Informally, a p-value is the probability ...

19. [Why do we read many articles with bad statistics? - PMC - NIH](https://pmc.ncbi.nlm.nih.gov/articles/PMC4823402/) - A *p*-value does not measure the probability that the research hypothesis is true, given the definit...

20. [Understanding Significance and P-Values - PMC - NIH](https://pmc.ncbi.nlm.nih.gov/articles/PMC4850233/) - 2. P-values do not measure the probability that the studied hypothesis is true, or the probability t...

21. [statsmodels.stats.multitest.multipletests#](https://www.statsmodels.org/stable//generated/statsmodels.stats.multitest.multipletests.html) - Available methods are: - bonferroni : one-step correction - sidak : one-step correction - holm-sidak...

22. [Quantitative Analysis in SoTL - UVA Teaching Hub](https://teaching.virginia.edu/collections/quantitative-analysis-in-sotl) - This table from UCLA OARC Statistical Method and Data Analytics group will help you identify appropr...

23. [scipy.stats.mannwhitneyu — SciPy v1.10.1 Manual](https://docs.scipy.org/doc//scipy-1.10.1/reference/generated/scipy.stats.mannwhitneyu.html) - When the means of samples from the populations are normally distributed, consider `scipy.stats.ttest...

24. [scipy.stats.ttest_ind — SciPy v1.11.2 Manual](https://docs.scipy.org/doc//scipy-1.11.2/reference/generated/scipy.stats.ttest_ind.html) - If False, perform Welch’s t-test, which does not assume equal population variance [2].

25. [5.2.4. Are the model residuals well-behaved?](https://www.itl.nist.gov/div898/handbook/pri/section2/pri24.htm) - Assumptions for residuals, These are the assumptions behind ANOVA and classical regression analysis....

26. [5.2.4.5. Check of assumptions](https://www.itl.nist.gov/div898/handbook/pri/section2/pri245.htm) - Residuals are elements of variation unexplained by the regression model generated. Since this is a f...

27. [Analyzing and Interpreting Data | Field Epi Manual](https://www.cdc.gov/field-epi-manual/php/chapters/analyze-interpret-data.html?CDC_AAref_Val=https://www.cdc.gov/eis/field-epi-manual/chapters/analyze-interpret-data.html) - An observed association might indeed represent a causal connection, but it might also result from ch...

28. [9.10 ARIMA vs ETS | Forecasting: Principles and Practice (3rd ed)](https://otexts.robjhyndman.com/fpp3/arima-ets.html) - We can use time series cross-validation to compare ARIMA and ETS models.

29. [scikit-learn: machine learning in Python — scikit-learn 1.5.0 ...](https://scikit-learn.org/stable/_sources/common_pitfalls.rst.txt) - * Always split the data into train and test subsets first, particularly
...
methods.

30. [Wholesale customers - UCI Machine Learning Repository](https://archive.ics.uci.edu/ml/datasets/wholesale+customers) - The data set refers to clients of a wholesale distributor. It includes the annual spending in moneta...

31. [The Story Behind the ASA Statement on P-Values - Amstat News](https://magazine.amstat.org/blog/2016/04/01/pres-apr16/) - **The ASA recently released a statement on *p*-values, and you were involved throughout the process.

32. [jamovi — open statistical software](https://www.jamovi.org/index.html) - jamovi is a free and open statistical spreadsheet, designed to be easy to use and powered by the R s...

33. [JASP - A Fresh Way to Do Statistics](https://jasp-stats.org/) - JASP is an open-source statistics program that is free, friendly, and flexible. Armed with an easy-t...

