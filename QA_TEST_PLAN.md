# QA and Debugging Test Plan for CleanSheet

## 1. Context Summary

- **Product**: CleanSheet — a Streamlit + Polars 2.0 statistical analysis application for no-code tabular data analysis
- **Core User Journeys**:
  1. Upload CSV/Parquet → Review import settings → Confirm semantic roles → Prepare data (reversible cleaning) → Select analysis goal & variables → Run analysis → View results with assumption diagnostics → Export reproducible bundle
  2. Autonomous Discovery: Upload → Auto-profile → Run 9-step discovery (BH-FDR controlled) → Review ranked findings → Drill into full analysis
  3. Headless CLI Replay: `cleansheet replay data.parquet recipe.json -o output/`
- **Critical Dependencies**: Polars 2.0 (streaming), SciPy/statsmodels (statistical tests), Matplotlib/Seaborn (plotting), Pydantic v2 (contracts), multiprocessing (worker isolation)
- **Release Risk**: Medium — statistical correctness is paramount; data integrity and reproducibility guarantees are core value propositions

---

## 2. Assumptions and Clarifications

| # | Assumption / Missing Information | Why It Matters | Clarification Needed |
|---|----------------------------------|----------------|----------------------|
| 1 | Exact version pins for SciPy, statsmodels, NumPy | Statistical results depend on exact algorithm implementations; version drift can change p-values/CIs | Confirm pinned versions in `requirements.txt`/`pyproject.toml` and test against them |
| 2 | Behavior of `pl.eval()` with user-provided filter expressions in `build_preparation_pipeline` | Security risk if arbitrary code execution possible; also affects reproducibility | Verify sandboxing or allowlist approach for filter expressions |
| 3 | Expected behavior when `StudyDesign.UNKNOWN` is selected for non-descriptive goals | Currently blocks inference but UI allows selection; should this be a hard error earlier? | Confirm if UNKNOWN should be selectable for inference goals or disabled in UI |
| 4 | Maximum dataset size for streaming collection on target deployment (Streamlit Cloud) | Resource limits (256 MiB materialization) may be too low/high for cloud | Confirm memory limits on deployment target; adjust `inference_materialization_limit_mib` if needed |
| 5 | Whether `TransformOp.FILTER` expression strings are user-facing or internal only | If user-facing, need injection protection; if internal, less critical | Clarify source of filter expressions — UI input or auto-generated? |
| 6 | Bootstrap CI availability depends on `scipy.stats.bootstrap` (SciPy ≥1.11) | Older SciPy falls back silently; CI status becomes "not_computed" | Define minimum SciPy version requirement; test fallback path explicitly |
| 7 | Pairing logic for wide-format paired data assumes exactly two occasion columns | Code validates `len(occasion_cols) != 2` but UI may allow more | Confirm wide format only supports pre/post (2 columns) |
| 8 | Autonomous discovery `target_column` scan vs full discovery produce different candidate sets | Target scan restricts to questions involving target; full discovery is all-pairs | Verify both modes produce consistent results for overlapping questions |

---

## 3. Risk Assessment

| Risk Area | Description | Potential User/Business Impact | Likelihood | Priority |
|-----------|-------------|--------------------------------|------------|----------|
| **Statistical Correctness** | Wrong p-values, CIs, effect sizes due to adapter bugs or SciPy version drift | Invalid scientific conclusions; loss of trust; potential publication retractions | Medium | **P0** |
| **Data Integrity / Reproducibility** | Recipe hash mismatch, SHA-256 verification failure, export bundle cannot reproduce results | Cannot verify published analyses; regulatory/compliance failure | Low | **P0** |
| **Assumption Routing Errors** | Parametric test used when assumptions violated (or vice versa) silently | Misleading results; Type I/II error inflation | Medium | **P0** |
| **Eligibility Gate Bypass** | Analysis runs despite failing hard eligibility checks (e.g., n<2 per group) | Crashes, meaningless results, or silent garbage output | Low | **P0** |
| **Resource Exhaustion** | Large file upload → OOM in worker process; streaming collection exceeds memory limit | App crash; denial of service; data loss in session | Medium | **P1** |
| **Worker Process Failures** | Plot rendering timeout, pickling errors, multiprocessing spawn issues on Windows | Silent failures; incomplete results; stuck jobs | Medium | **P1** |
| **Session State Corruption** | Stale results shown after recipe change; config hash mismatch not detected | User sees wrong results for current configuration | Medium | **P1** |
| **Formula Injection in CSV Export** | Malicious column names/values execute formulas in Excel/Sheets | Security vulnerability on downstream opening | Low | **P1** |
| **Accessibility/Usability** | Missing ARIA labels, keyboard traps, color-only status indicators | Excludes users; legal compliance risk (WCAG) | Medium | **P2** |
| **Cross-browser/Streamlit Version Drift** | UI breaks on Streamlit upgrade; CSS conflicts | Broken user flows; blocked releases | Low | **P2** |

---

## 4. QA Test Plan

### Test Case Table

| ID | Test Type | Title | Preconditions | Steps | Test Data | Expected Result | Priority | Requirement Trace | Automation Recommendation |
|----|-----------|-------|---------------|-------|-----------|-----------------|----------|-------------------|---------------------------|
| **Functional & Acceptance** |
| TC-001 | Functional | Upload CSV with valid encoding/delimiter | Fresh session | 1. Upload `examples/public-data/palmer_penguins.csv`<br>2. Confirm import settings<br>3. Confirm semantic roles<br>4. Proceed to preparation | Palmer Penguins CSV (344 rows, 8 cols) | Dataset loads; preview shows 100 rows; roles inferred correctly (species=nominal, bill_length=continuous, etc.) | P0 | Ingest → Profile → UI Start/ImportReview | Automate (pytest + Playwright) |
| TC-002 | Functional | Upload Parquet with schema overrides | Fresh session | 1. Upload Parquet file<br>2. Override one column dtype in import review<br>3. Confirm roles | Synthetic Parquet with 1000 rows, mixed types | Override applied; schema_hash reflects override; downstream analysis uses overridden types | P1 | Ingest → ImportReview | Automate (pytest) |
| TC-003 | Functional | Guided analysis: Compare two means (Welch's t-test) | Dataset with continuous outcome + binary group; study design=independent | 1. Select "Compare two groups"<br>2. Choose outcome=continuous, group=binary<br>3. Select 2 group levels<br>4. Set contrast direction<br>5. Confirm study design=independent<br>6. Run eligibility + assumptions<br>7. Run analysis | Palmer Penguins: outcome=bill_length_mm, group=sex (2 levels) | Eligibility passes; assumption report shows skewness/outliers/variance checks; Welch's t-test runs; result shows estimate, 95% CI, Hedges' g, p-value | P0 | Question → Statistics → Results | Automate (pytest + API test) |
| TC-004 | Functional | Guided analysis: Paired t-test (long format) | Dataset with pair_id, occasion, outcome; study design=paired | 1. Select "Compare before/after"<br>2. Choose long format<br>3. Map pair_id, occasion, outcome<br>4. Select 2 occasions<br>5. Set contrast<br>6. Run analysis | Synthetic paired data: 20 subjects, pre/post scores | Paired t-test runs; estimate = mean difference; CI correct; Hedges' g for paired computed; contrast direction respected | P0 | Question → Statistics → Results | Automate (pytest) |
| TC-005 | Functional | Guided analysis: Paired t-test (wide format) | Dataset with pair_id, pre_col, post_col | 1. Select "Compare before/after"<br>2. Choose wide format<br>3. Map pair_id, pre_col, post_col<br>4. Run analysis | Synthetic wide paired data | Wide format correctly pivoted; contrast = post_minus_pre; same results as long format equivalent | P1 | Question → Statistics | Automate (pytest) |
| TC-006 | Functional | Guided analysis: Pearson correlation | Two continuous variables; n≥10 | 1. Select "Explore linear relationship"<br>2. Choose two continuous vars<br>3. Run analysis | Palmer Penguins: bill_length_mm vs bill_depth_mm | Pearson r computed; Fisher-z CI; p-value; effect size = r | P0 | Question → Statistics | Automate (pytest) |
| TC-007 | Functional | Guided analysis: Spearman correlation | Two numeric/ordinal variables | 1. Select "Explore monotonic relationship"<br>2. Choose variables<br>3. Run analysis | Synthetic monotonic non-linear data | Spearman ρ computed; permutation p-value for n<30; bootstrap CI for n≥10 | P1 | Question → Statistics | Automate (pytest) |
| TC-008 | Functional | Guided analysis: Chi-square test | Two categorical variables; expected counts ≥5 | 1. Select "Test category association"<br>2. Choose two categorical vars<br>3. Run analysis | Palmer Penguins: species vs island | Chi-square statistic; Cramér's V; p-value; expected counts table in assumptions | P0 | Question → Statistics | Automate (pytest) |
| TC-009 | Functional | Guided analysis: Fisher's exact test | 2×2 table with small counts | 1. Select "Sparse 2×2 table"<br>2. Choose binary outcome + binary group<br>3. Run analysis | Synthetic 2×2 table (n=20, sparse) | Fisher's exact p-value; odds ratio estimate; CI status = not_computed | P1 | Question → Statistics | Automate (pytest) |
| TC-010 | Functional | Guided analysis: Kruskal-Wallis (3+ groups) | Continuous outcome, categorical group with ≥3 levels | 1. Select "Compare 3+ groups"<br>2. Choose outcome + group (3+ levels)<br>3. Run analysis | Palmer Penguins: bill_length_mm vs species (3 levels) | Kruskal-Wallis runs; if significant, Dunn post-hoc auto-runs with Holm correction | P1 | Question → Statistics → Nonparametric | Automate (pytest) |
| TC-011 | Functional | Autonomous discovery (full scan) | Dataset with mixed types | 1. Select "Autonomous Discovery" tab<br>2. Click "Run Full Discovery Scan"<br>3. Wait for completion | Palmer Penguins | Returns ≤5 candidates; all have q<0.05, |effect|≥0.1; ranked by composite score; no redundant pairs | P0 | Discovery Engine | Automate (pytest) |
| TC-012 | Functional | Target scan discovery | Dataset + target column selected | 1. Select "Target Scan" tab<br>2. Choose target=continuous<br>3. Click "Scan for Drivers" | Palmer Penguins: target=bill_length_mm | Returns drivers of target only; all eligible; FDR-adjusted | P1 | Discovery Engine | Automate (pytest) |
| TC-013 | Functional | Data preparation: reversible recipe | Dataset with missing values, outliers | 1. Go to Preparation screen<br>2. Apply: drop constant column, impute median, flag outliers<br>3. Verify preview updates<br>4. Undo last step<br>5. Verify revert | Synthetic data with known issues | Each step recorded in recipe; undo removes last step; redo reapplies; recipe_hash changes deterministically | P0 | Prepare → Execution | Automate (pytest) |
| TC-014 | Functional | Export bundle generation | Completed analysis with results + plots | 1. Go to Export screen<br>2. Click "Download Report"<br>3. Unzip bundle<br>4. Verify contents | Any completed analysis | ZIP contains: report.md, report.html, results.csv, assumption_diagnostics.csv, data_dictionary.csv, quality_issues.csv, recipe.json, run_manifest.json, cleansheet_reproduce.py, figures/*.png | P0 | Export → Reports | Automate (pytest + CLI) |
| TC-015 | Functional | CLI replay reproduces results | Exported recipe.json + original data file | 1. Run `cleansheet replay data.csv recipe.json -o out/`<br>2. Compare result.json with original | Exported artifacts from TC-014 | SHA-256 verified; recipe reapplied; analysis results match within 1e-6 tolerance | P0 | CLI → Reproducibility | Automate (pytest + subprocess) |
| **API Contract & Integration** |
| TC-016 | Integration | `run_analysis` end-to-end with recipe | Workspace + dataset_ref + recipe + AnalysisRequest | 1. Ingest data<br>2. Build recipe<br>3. Call `run_analysis(ws, ref, request, recipe)` | Palmer Penguins + drop column recipe | Returns AnalysisResult with status=complete; statistical_results populated; provenance includes assumption_report | P0 | Statistics Service | Automate (pytest) |
| TC-017 | Integration | `check_eligibility` blocks invalid requests | Various invalid configurations | 1. Call `check_eligibility` with each failing condition | See negative tests below | Returns EligibilityResult.allowed=False; rule_ids populated; reasons descriptive | P0 | Recommend Service | Automate (pytest) |
| TC-018 | Integration | `run_assumption_diagnostics` routes correctly | Data with known assumption violations | 1. Create data with high skewness/outliers/unequal variance<br>2. Run diagnostics for each goal | Synthetic data per violation type | Auto-routes to non-parametric when violations detected; routing_explanation clear | P0 | Assumptions Engine | Automate (pytest) |
| TC-019 | Integration | Job runner: analysis job completes within timeout | JobRunner started; valid spec submitted | 1. Submit "analyze" job<br>2. Wait for completion<br>3. Check result | Valid analysis request | Job status=COMPLETE; result stored as artifact; resource_usage recorded | P1 | Jobs → Runner | Automate (pytest) |
| TC-020 | Integration | Workspace janitor cleans old workspaces | Workspaces older than `session_inactivity_minutes * 2` | 1. Create workspace with old mtime<br>2. Run `janitor()`<br>3. Verify removal | Temp workspace dirs | Old workspaces removed; active preserved; count returned | P2 | Workspace → Janitor | Automate (pytest) |
| **Boundary & Equivalence Class** |
| TC-021 | Boundary | Upload at max size (50 MB) | `max_upload_size_mb=50` | 1. Generate 50 MB CSV<br>2. Upload | 50 MB CSV (synthetic) | Accepted; preview loads; profiling works | P1 | Config → Ingest | Automate (pytest) |
| TC-022 | Boundary | Upload exceeds max size (51 MB) | `max_upload_size_mb=50` | 1. Generate 51 MB CSV<br>2. Upload | 51 MB CSV | Rejected with ResourceLimitError; clear message | P1 | Config → Ingest | Automate (pytest) |
| TC-023 | Boundary | Profiling column limit (50 cols) | `max_profiling_columns=50` | 1. Upload 60-column dataset<br>2. Run profiling | 60-col synthetic data | Only first 50 columns profiled; no error | P1 | Config → Profile | Automate (pytest) |
| TC-024 | Boundary | Plot point limit (20,000) | `max_plot_points=20000` | 1. Generate 50,000-row dataset<br>2. Request scatterplot | 50k rows continuous×continuous | Sampled to 20k points deterministically; seed reproducible | P1 | Config → Visualize | Automate (pytest) |
| TC-025 | Boundary | Minimum group size for Welch (n=2 per group) | 2 groups, 2 obs each | 1. Create minimal data<br>2. Run Welch test | n=4 total (2 per group) | Runs; df≈2; CI very wide; warning about low power | P1 | Statistics → Eligibility | Automate (pytest) |
| TC-026 | Boundary | Minimum pairs for paired t-test (n=2 pairs) | 2 complete pairs | 1. Create 2-pair data<br>2. Run paired test | 2 pairs | Runs; df=1; CI extremely wide | P1 | Statistics → Eligibility | Automate (pytest) |
| TC-027 | Boundary | Correlation n=3 (minimum) | 3 complete paired observations | 1. Create 3-pair data<br>2. Run Pearson | 3 pairs | Runs; df=1; CI computed via Fisher-z | P1 | Statistics → Eligibility | Automate (pytest) |
| TC-028 | Equivalence | Decimal comma (European) parsing | `decimal_comma=True` in ImportSpec | 1. Upload CSV with `1,23` format<br>2. Set decimal_comma=True<br>3. Verify numeric values | European-format CSV | Values parsed correctly (1.23 not 123) | P1 | Ingest → ImportSpec | Automate (pytest) |
| TC-029 | Equivalence | Null token variations | `null_tokens=["NA","N/A",".","-999","null","NULL",""]` | 1. Upload CSV with each token<br>2. Verify all become null | CSV with mixed null tokens | All specified tokens parsed as null; empty string also null | P1 | Ingest → ImportSpec | Automate (pytest) |
| **Negative, Invalid Input & Error Handling** |
| TC-030 | Negative | Upload non-CSV/Parquet (e.g., .xlsx) | Fresh session | 1. Upload .xlsx file | Excel file | Rejected with SecurityError (disallowed MIME) | P1 | Ingest → Security | Automate (pytest) |
| TC-031 | Negative | Upload corrupted Parquet | Fresh session | 1. Upload truncated Parquet | Corrupted .parquet | ParsingError with clear message | P1 | Ingest → Parsing | Automate (pytest) |
| TC-032 | Negative | Welch test with 3 groups selected | Goal=COMPARE_TWO_MEANS, group_levels=3 | 1. Configure 3 groups<br>2. Run eligibility | Any 3-group data | Eligibility fails: "exactly two groups required" | P0 | Eligibility Gates | Automate (pytest) |
| TC-033 | Negative | Welch test with categorical outcome | Goal=COMPARE_TWO_MEANS, outcome=nominal | 1. Select nominal outcome<br>2. Run eligibility | Categorical outcome | Eligibility fails: "outcome must be continuous" | P0 | Eligibility Gates | Automate (pytest) |
| TC-034 | Negative | Paired test without pair_id | Goal=COMPARE_PAIRED_MEANS, no pair_id in variables | 1. Configure paired without pair_id<br>2. Run eligibility | Paired data, missing pair_id | Eligibility fails: "pair identifier must be specified" | P0 | Eligibility Gates | Automate (pytest) |
| TC-035 | Negative | Paired test with unknown study design | Goal=COMPARE_PAIRED_MEANS, study_design=UNKNOWN | 1. Set study_design=UNKNOWN<br>2. Run eligibility | Any paired data | Eligibility fails: "study design unknown" | P0 | Eligibility Gates | Automate (pytest) |
| TC-036 | Negative | Correlation with constant variable | One variable has zero variance | 1. Create constant column<br>2. Run Pearson eligibility | Constant + variable | Eligibility fails: "variables must have variation" | P1 | Eligibility Gates | Automate (pytest) |
| TC-037 | Negative | Chi-square with expected count <5 | Sparse contingency table | 1. Create sparse table<br>2. Run eligibility (warning gate) | Sparse 3×3 table | Eligibility passes but warning: "expected counts <5, consider Fisher" | P1 | Eligibility Gates | Automate (pytest) |
| TC-038 | Negative | Job timeout enforcement | `analysis_job_timeout_seconds=5`, slow analysis | 1. Submit job with artificial delay<br>2. Wait | Slow synthetic data | Job status=TIMED_OUT; error recorded; worker killed | P1 | Jobs → Timeout | Automate (pytest) |
| TC-039 | Negative | Worker process crash (OOM) | Large dataset > materialization limit | 1. Submit job with huge data<br>2. Monitor worker | 500MB+ data | Job status=FAILED; ResourceLimitError; main process survives | P1 | Jobs → Resource Limits | Automate (pytest) |
| TC-040 | Negative | Session state stale detection | Recipe changed after analysis run | 1. Run analysis<br>2. Modify recipe<br>3. Return to results | Any analysis + recipe change | `stale_results=True`; warning shown; re-run required | P1 | UI → Session State | Automate (Playwright) |
| **Authentication/Authorization** |
| TC-041 | Auth | No auth in current design (local app) | N/A | N/A | N/A | Documented as out of scope; single-user local tool | P3 | N/A | N/A |
| **Data Integrity & Persistence** |
| TC-042 | Data Integrity | SHA-256 verification on replay | Exported recipe + original file | 1. Modify source file by 1 byte<br>2. Run CLI replay | Modified source | Fails with "Source file hash mismatch" | P0 | Reproducibility | Automate (pytest + CLI) |
| TC-043 | Data Integrity | Recipe hash determinism | Same recipe steps in different order | 1. Create recipe A: [step1, step2]<br>2. Create recipe B: [step2, step1]<br>3. Compare hashes | Two recipes with same steps, different order | Hashes differ (order matters for correctness) | P0 | Contracts → compute_recipe_hash | Automate (pytest) |
| TC-044 | Data Integrity | Prepared data cache invalidation | Recipe changed | 1. Run with recipe v1<br>2. Change recipe to v2<br>3. Get prepared data | Two recipe versions | v2 computed fresh; v1 cached separately; no cross-contamination | P0 | Execution → Caching | Automate (pytest) |
| TC-045 | Data Integrity | Export bundle contains exact reproduction script | Completed analysis | 1. Export bundle<br>2. Run `cleansheet_reproduce.py` on original data | Exported ZIP | Script verifies hash, reapplies recipe, asserts results match within 1e-6 | P0 | Reports → Reproduction | Automate (pytest + subprocess) |
| **Concurrency & Race Conditions** |
| TC-046 | Concurrency | Multiple rapid job submissions | JobRunner max_workers=1 | 1. Submit 3 analysis jobs rapidly<br>2. Wait for all | 3 valid requests | Jobs queued; execute sequentially; all complete; no worker collisions | P1 | Jobs → Runner | Automate (pytest) |
| TC-047 | Concurrency | Cancel running job | Job submitted, not yet complete | 1. Submit long-running job<br>2. Cancel immediately | Slow analysis | Job status=CANCELLED; worker process terminated; no orphan processes | P1 | Jobs → Runner | Automate (pytest) |
| TC-048 | Concurrency | Session isolation (multi-tab) | Two browser tabs same session | 1. Open app in two tabs<br>2. Upload in tab 1<br>3. Check tab 2 | Same session_id | Tab 2 reflects tab 1 state (Streamlit session shared); no data corruption | P2 | UI → Session | Manual (exploratory) |
| **Performance & Load** |
| TC-049 | Performance | Profiling 50 columns × 100k rows | Large dataset within limits | 1. Generate 100k × 50 dataset<br>2. Run profiling | Synthetic mixed-type data | Completes <30s; memory <512 MiB; streaming used | P1 | Profile → Performance | Automate (benchmark) |
| TC-050 | Performance | Autonomous discovery on 20 numeric + 10 categorical | Max candidate generation | 1. Generate dataset with 30 eligible columns<br>2. Run full discovery | 30-col mixed dataset | Completes <60s; candidate pool ≤40; BH-FDR applied correctly | P1 | Discovery → Performance | Automate (benchmark) |
| TC-051 | Performance | Plot rendering 20k points | `max_plot_points=20000` | 1. Request raincloud plot on 50k rows<br>2. Measure render time | 50k continuous×categorical | Worker renders sampled 20k points; <10s timeout; PNG produced | P1 | Visualize → Performance | Automate (benchmark) |
| **Security** |
| TC-052 | Security | Formula injection protection in CSV export | `formula_injection_protection=True` | 1. Create column with values `=1+1`, `+cmd|'...`'<br>2. Export results CSV<br>3. Open in Excel | Malicious strings in data | Values prefixed with `'`; formulas neutralized | P1 | Reports → Security | Automate (pytest) |
| TC-053 | Security | Path traversal in workspace file ops | Malicious filename in upload | 1. Upload file named `../../../etc/passwd`<br>2. Check stored path | Malicious filename | Stored under workspace root with safe name; no directory traversal | P1 | Workspace → Security | Automate (pytest) |
| TC-054 | Security | Pickle safety in job runner | Job payloads serialized | 1. Submit job with complex payload<br>2. Verify no arbitrary code exec | Any job spec | Only Pydantic models + primitives pickled; no custom classes | P1 | Jobs → Security | Automate (code review) |
| **Accessibility** |
| TC-055 | Accessibility | Skip link present and functional | Any screen | 1. Tab to skip link<br>2. Press Enter | N/A | Focus jumps to main content; announced to screen reader | P2 | UI → Accessibility | Automate (Playwright + axe-core) |
| TC-056 | Accessibility | Color not sole indicator (status icons) | Results screen with pass/fail checks | 1. View assumption report<br>2. Check with color blindness sim | Assumption checks with pass/fail | Icons + text indicate status; not color-only | P2 | UI → Accessibility | Manual (exploratory) |
| TC-057 | Accessibility | Keyboard navigation all interactive elements | All UI screens | 1. Tab through entire flow<br>2. Verify focus order | Full app | All buttons, selects, inputs reachable; focus visible; no traps | P2 | UI → Accessibility | Automate (Playwright) |

---

## 5. Exploratory Testing Charters

| Charter | Target Risk | Duration | Notes on Signals of Failure |
|---------|-------------|----------|------------------------------|
| **Charter 1: Statistical Edge Cases** | Statistical correctness under extreme data conditions | 90 min | Test: n=2 per group, perfect separation, all identical values, extreme outliers, perfect multicollinearity. Signals: NaN results, infinite CIs, wrong test selection, crashes. |
| **Charter 2: Session State & Navigation Chaos** | Session corruption, stale results, back/forward browser behavior | 60 min | Rapidly navigate back/forth between stages; refresh browser; duplicate tabs; modify recipe mid-analysis. Signals: Wrong data shown, lost recipe, duplicate job submissions, state desync. |
| **Charter 3: Autonomous Discovery Stress** | Discovery engine correctness, redundancy pruning, FDR control | 60 min | Run discovery on datasets with: many correlated predictors, known true effects + noise, all null effects. Signals: False positives (q<0.05 but known null), missed true effects, redundant candidates not pruned, score ranking anomalies. |
| **Charter 4: Worker Process Resilience** | Plot rendering failures, timeouts, memory leaks in subprocesses | 45 min | Submit many plot jobs rapidly; kill worker mid-render; submit oversized plot data. Signals: Orphan processes, memory growth, timeout not enforced, partial results returned. |
| **Charter 5: Cross-Format & Encoding Compatibility** | Ingest robustness across CSV variants | 45 min | Test: UTF-16, ISO-8859-1, CRLF/LF mixed, quoted fields with embedded delimiters, BOM, empty files, header-only files. Signals: Silent data corruption, wrong row counts, encoding errors, crash. |

---

## 6. Debugging and Root-Cause Plan

| Issue / Suspected Failure | Reproduction Steps | Evidence to Collect | Likely Root Causes | Isolation Steps | Fix Verification | Regression Test to Add |
|---------------------------|-------------------|---------------------|-------------------|-----------------|------------------|------------------------|
| **Wrong p-value / CI in Welch's t-test** | Run TC-003; compare with SciPy `ttest_ind(equal_var=False)` | 1. `result.p_value`, `result.interval`<br>2. SciPy reference values<br>3. Input data arrays | 1. Contrast direction logic error (first/second swap)<br>2. df_welch formula bug<br>3. SciPy version difference | 1. Add debug logging in `WelchTTestAdapter.run()` printing group arrays, contrast, computed values<br>2. Compare intermediate values (mean_diff, se, df_welch) with manual calculation<br>3. Pin SciPy version; test with known-good version | 1. Unit test `test_welch_ttest_adapter` passes with tolerance 1e-6<br>2. Manual verification on known dataset | `test_welch_ttest_adapter_precision` with fixed seed data |
| **Paired t-test fails on wide format** | Run TC-005; observe error or wrong result | 1. Error traceback or result values<br>2. Input DataFrame schema<br>3. `request.variables` content | 1. `pre_col`/`post_col` not in `request.variables`<br>2. Pivot logic expects long format columns<br>3. Contrast string parsing for wide format | 1. Breakpoint in `PairedTTestAdapter.run()` at `is_wide_format` detection<br>2. Verify `request.variables` contains `pre_col` and `post_col`<br>3. Check pivot output columns | 1. Wide format test passes with same results as long format equivalent<br>2. Contrast direction correct | `test_paired_ttest_wide_format` |
| **Assumption routing doesn't trigger non-parametric** | Create highly skewed data (log-normal); run COMPARE_TWO_MEANS | 1. `assumption_report.auto_routed`<br>2. `assumption_report.recommended_method`<br>3. Skewness check values | 1. `check_skewness` threshold too high (1.5)<br>2. `check_outliers` not detecting<br>3. `_determine_method_routing` logic error | 1. Print all assumption check values in `_determine_method_routing`<br>2. Verify `assumption_failures` list populated<br>3. Check `design_mismatch` logic | 1. Skewed data → auto_routed=True, recommended=MANN_WHITNEY_U<br>2. Normal data → auto_routed=False, recommended=WELCH_T | `test_assumption_routing_skewed_data` |
| **Eligibility gate not blocking (e.g., n<2)** | Create data with 1 observation per group; run Welch | 1. `eligibility.allowed`<br>2. `eligibility.rule_ids`<br>3. Group counts in data | 1. `_check_group_counts` filters incorrectly<br>2. `group_levels` not passed to eligibility<br>3. Data materialization drops rows unexpectedly | 1. Debug `check_eligibility`: print `df` height, group counts, finite filter result<br>2. Verify `req.group_levels` matches data levels<br>3. Check `materialize_for_analysis` columns | 1. n=1 per group → allowed=False, rule_ids contains "sufficient_data"<br>2. Clear error message to user | `test_welch_eligibility_insufficient_group_size` |
| **Session state shows stale results after recipe change** | 1. Run analysis<br>2. Go back to Preparation<br>3. Add/remove cleaning step<br>4. Return to Results | 1. `st.session_state.stale_results`<br>2. `st.session_state.recipe_hash` vs current<br>3. UI warning presence | 1. `_invalidate_pending_analysis` not called on recipe change<br>2. `stale_results` flag not set in `apply_transform`<br>3. Results screen doesn't check `stale_results` | 1. Trace `recipe` mutations in session state<br>2. Add logging to `reset_session`, `apply_transform`, `render_results`<br>3. Verify `recipe_hash` comparison in results screen | 1. Recipe change → `stale_results=True`<br>2. Results screen shows "Results outdated — re-run analysis"<br>3. Re-run produces new results | `test_stale_results_after_recipe_change` (Playwright) |
| **Job runner worker OOM / timeout not caught** | Submit job with data exceeding `inference_materialization_limit_mib` | 1. Job status (TIMED_OUT/FAILED)<br>2. Worker process memory (OS level)<br>3. Error message in `spec.error` | 1. `_check_materialization_size` estimation inaccurate<br>2. `resource.setrlimit` not working on platform<br>3. `ProcessPoolExecutor` doesn't propagate OOM kill | 1. Run with `ulimit -v` to simulate limit<br>2. Check `resource.setrlimit` return value<br>3. Monitor worker PID memory via `psutil` | 1. OOM → Job status=FAILED, error="Memory limit exceeded"<br>2. Timeout → Job status=TIMED_OUT<br>3. Main process stable | `test_job_runner_oom_handling` (may need CI skip) |
| **Export reproduction script fails verification** | Run TC-015; check verification output | 1. Script stdout (MISMATCH lines)<br>2. `original` vs `res` dict values<br>3. Tolerance threshold | 1. Floating-point non-determinism (bootstrap CI)<br>2. Recipe application order difference<br>3. Polars streaming vs in-memory collection difference | 1. Run script with `--verbose` to see each step<br>2. Compare intermediate DataFrames (recipe output)<br>3. Set `polars_streaming=False` for reproducibility | 1. All numeric keys match within 1e-6<br>2. Bootstrap CI may vary — document as known variance | `test_reproduction_script_verification` (allow bootstrap CI variance) |
| **Plot rendering hangs / worker deadlock** | Submit many plot jobs; observe completion | 1. Job statuses<br>2. Worker process count<br>3. Timeout errors | 1. `ProcessPoolExecutor` max_workers=1 but multiple submits<br>2. Matplotlib backend not 'Agg' in worker<br>3. `plt.close(fig)` not called on exception | 1. Verify `matplotlib.use("Agg")` at module top in `visualize.py`<br>2. Check worker cleanup in `finally` block<br>3. Add timeout to `future.result()` | 1. All plots complete or timeout cleanly<br>2. No orphan matplotlib processes<br>3. Memory stable across repeated renders | `test_plot_worker_isolation` |
| **Formula injection not escaped in CSV** | Export results with `=1+1` in column name/value | 1. Generated CSV content<br>2. Open in Excel (or check raw) | 1. `escape_csv_value` not applied to all string columns<br>2. Column names not escaped<br>3. `formula_injection_protection` setting False | 1. Check `generate_results_csv` applies escape to all string cols<br>2. Verify column names also escaped<br>3. Test with `settings.formula_injection_protection=True` | 1. Malicious strings prefixed with `'`<br>2. CSV opens safely in Excel/LibreOffice | `test_formula_injection_protection` |

---

## 7. Test Data and Environment Requirements

| Requirement | Details |
|-------------|---------|
| **Test Accounts/Permissions** | None (local single-user app); Streamlit Cloud deployment uses public access |
| **Test Fixtures** | - `examples/public-data/palmer_penguins.csv` (primary)<br>- Synthetic datasets: paired (long/wide), skewed, sparse 2×2, high-cardinality, constant columns, missingness patterns<br>- Edge-case CSVs: European decimal, mixed null tokens, BOM, CRLF, quoted delimiters |
| **Mocks** | - `Workspace` for unit tests (in-memory)<br>- `LazyExecutor` with controlled LazyFrames<br>- `ProcessPoolExecutor` mocked for job runner tests |
| **Seeded Data** | All statistical tests use `seed=42`; sampling uses deterministic hash; bootstrap/permutation use fixed RNG |
| **Test Environments** | - Local: Python 3.12, full deps<br>- CI: GitHub Actions (ubuntu-latest, macos-latest, windows-latest)<br>- Streamlit Cloud: smoke test on deploy |
| **Third-Party Sandboxes** | None required |
| **Cleanup Steps** | - `pytest` tmp_path for workspace dirs<br>- `WorkspaceManager.cleanup_all(force=True)` in test teardown<br>- Kill any orphan `python` processes from `ProcessPoolExecutor` |

---

## 8. Automation Strategy

| Test | Automate? | Framework/Tool Suggestion | Reason | CI/CD Trigger |
|------|-----------|---------------------------|--------|---------------|
| TC-001–TC-015 (Functional API) | ✅ Yes | `pytest` + direct service calls | Fast, deterministic, tests core logic | Every push |
| TC-016–TC-020 (Integration) | ✅ Yes | `pytest` with real Workspace | Tests service boundaries | Every push |
| TC-021–TC-029 (Boundary) | ✅ Yes | `pytest` with parametrize | Clear pass/fail; low flakiness | Every push |
| TC-030–TC-040 (Negative) | ✅ Yes | `pytest` with `pytest.raises` | Validates error handling | Every push |
| TC-042–TC-045 (Data Integrity) | ✅ Yes | `pytest` + CLI subprocess | Reproducibility is core feature | Every push |
| TC-046–TC-048 (Concurrency) | ⚠️ Partial | `pytest` for queue logic; manual for multi-tab | Multi-tab hard to automate reliably | PR merge |
| TC-049–TC-051 (Performance) | ✅ Yes (benchmarks) | `pytest-benchmark` or custom timing | Track regressions; not gate | Nightly / weekly |
| TC-052–TC-054 (Security) | ✅ Yes | `pytest` + static analysis (bandit) | Formula injection testable; path traversal unit-testable | Every push |
| TC-055–TC-057 (Accessibility) | ✅ Partial | Playwright + axe-core for skip link, focus order; manual for color | Automated a11y catches regressions; color needs human | PR merge |
| Exploratory Charters | ❌ No | Manual testing sessions | Requires human judgment, creativity | Pre-release |
| Debugging Investigations | ❌ No | Ad-hoc with debug logs, breakpoints | Non-deterministic; expert-driven | As needed |

---

## 9. Definition of Done for Testing

- [ ] All P0 tests pass (TC-001–TC-010, TC-014–TC-015, TC-021–TC-022, TC-032–TC-035, TC-042–TC-045, TC-052)
- [ ] All P1 tests pass (TC-011–TC-013, TC-016–TC-020, TC-023–TC-027, TC-028–TC-031, TC-036–TC-039, TC-046–TC-047, TC-049–TC-051, TC-053–TC-054)
- [ ] Critical user journeys verified manually: Upload → Guided Analysis → Results → Export → CLI Replay
- [ ] Known defects triaged with severity (Critical/High/Medium/Low) and owner assigned
- [ ] Regression suite updated with new tests for any fixed bugs
- [ ] No unresolved Critical/High severity issues in: statistical correctness, data integrity, reproducibility, security (formula injection, path traversal)
- [ ] Performance benchmarks within 20% of baseline (profiling <30s, discovery <60s, plot render <10s)
- [ ] Accessibility: Skip link works, keyboard navigation complete, no color-only indicators
- [ ] Export bundle verified: `cleansheet_reproduce.py` passes verification on clean environment
- [ ] CLI `replay` and `profile` commands work end-to-end
- [ ] Documentation updated for any behavior changes (AGENTS.md, README, blueprint)

---

*Generated: 2026-10-27 | CleanSheet v0.1.0 | Based on codebase analysis of src/CleanSheet/, tests/, app.py, AGENTS.md*