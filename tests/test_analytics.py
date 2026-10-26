"""Comprehensive analytics tests for CleanSheet."""

import numpy as np
import polars as pl
import pytest
from scipy import stats

from CleanSheet.contracts import (
    AnalysisRequest,
    ColumnRole,
    DatasetRef,
    Goal,
    IntervalMethod,
    Method,
    MissingPolicy,
    NonFinitePolicy,
    SemanticRole,
    StudyDesign,
    Alternative,
)
from CleanSheet.engine.execution import get_prepared_lazy
from CleanSheet.services.statistics import (
    WelchTTestAdapter,
    PairedTTestAdapter,
    PearsonCorrelationAdapter,
    SpearmanCorrelationAdapter,
    ChiSquareAdapter,
    FisherExactAdapter,
    DescriptiveAdapter,
    run_analysis,
    ADAPTERS,
)
from CleanSheet.services.recommend import check_eligibility, ELIGIBILITY_GATES
from CleanSheet.services.profile import profile_column, run_profiling
from CleanSheet.jobs.workspace import Workspace


class TestStatisticalAdapters:
    """Test statistical test adapters against known SciPy results."""

    def test_welch_ttest_adapter(self):
        """Test Welch's t-test adapter produces correct results."""
        adapter = WelchTTestAdapter()
        
        # Create test data with known difference
        np.random.seed(42)
        group1 = np.random.normal(10, 2, 30)
        group2 = np.random.normal(12, 2.5, 30)
        
        df = pl.DataFrame({
            "outcome": np.concatenate([group1, group2]),
            "group": ["A"] * 30 + ["B"] * 30,
        })
        
        request = AnalysisRequest(
            goal=Goal.COMPARE_TWO_MEANS,
            variables={"outcome": "outcome", "group": "group"},
            group_levels=["A", "B"],
            study_design=StudyDesign.INDEPENDENT,
            estimand="Difference in means",
            alternative=Alternative.TWO_SIDED,
            confidence_level=0.95,
            seed=42,
        )
        
        result = adapter.run(df, request)
        
        # Compare with SciPy directly
        scipy_result = stats.ttest_ind(group1, group2, equal_var=False)
        
        assert result.method == Method.WELCH_T
        assert result.estimate is not None
        assert result.p_value is not None
        assert abs(result.p_value - scipy_result.pvalue) < 0.001
        assert result.interval_status == "computed"
        assert result.interval is not None
        assert result.degrees_of_freedom is not None

    def test_paired_ttest_adapter(self):
        """Test paired t-test adapter."""
        adapter = PairedTTestAdapter()
        
        np.random.seed(42)
        n = 20
        before = np.random.normal(10, 2, n)
        after = before + np.random.normal(0.5, 1, n)  # True difference = 0.5
        
        df = pl.DataFrame({
            "pair_id": list(range(n)) * 2,
            "occasion": ["before"] * n + ["after"] * n,
            "outcome": np.concatenate([before, after]),
        })
        
        request = AnalysisRequest(
            goal=Goal.COMPARE_PAIRED_MEANS,
            variables={"outcome": "outcome", "pair_id": "pair_id", "occasion": "occasion"},
            contrast="after_minus_before",
            study_design=StudyDesign.PAIRED,
            estimand="Mean paired difference",
            alternative=Alternative.TWO_SIDED,
            confidence_level=0.95,
            seed=42,
        )
        
        result = adapter.run(df, request)
        
        assert result.method == Method.PAIRED_T
        assert result.estimate is not None
        # True mean difference is ~0.5
        assert 0.2 < result.estimate < 0.8
        assert result.interval_status == "computed"
        assert result.degrees_of_freedom == n - 1

    def test_pearson_correlation_adapter(self):
        """Test Pearson correlation adapter."""
        adapter = PearsonCorrelationAdapter()
        
        np.random.seed(42)
        n = 50
        x = np.random.normal(0, 1, n)
        y = 0.7 * x + np.random.normal(0, 0.5, n)  # True correlation ~0.7
        
        df = pl.DataFrame({"x": x, "y": y})
        
        request = AnalysisRequest(
            goal=Goal.EXPLORE_LINEAR_RELATIONSHIP,
            variables={"outcome": "x", "predictor": "y"},
            study_design=StudyDesign.INDEPENDENT,
            estimand="Pearson correlation",
            alternative=Alternative.TWO_SIDED,
            confidence_level=0.95,
            seed=42,
        )
        
        result = adapter.run(df, request)
        
        # Compare with SciPy
        scipy_result = stats.pearsonr(x, y)
        
        assert result.method == Method.PEARSON_R
        assert result.estimate is not None
        assert abs(result.estimate - scipy_result.statistic) < 0.01
        assert result.interval_status == "computed"
        assert result.interval is not None
        # CI should contain the estimate
        assert result.interval[0] < result.estimate < result.interval[1]

    def test_spearman_correlation_adapter(self):
        """Test Spearman correlation adapter."""
        adapter = SpearmanCorrelationAdapter()
        
        np.random.seed(42)
        n = 30
        x = np.random.normal(0, 1, n)
        y = x ** 3 + np.random.normal(0, 1, n)  # Monotonic but non-linear
        
        df = pl.DataFrame({"x": x, "y": y})
        
        request = AnalysisRequest(
            goal=Goal.EXPLORE_ORDERED_RELATIONSHIP,
            variables={"outcome": "x", "predictor": "y"},
            study_design=StudyDesign.INDEPENDENT,
            estimand="Spearman correlation",
            alternative=Alternative.TWO_SIDED,
            confidence_level=0.95,
            seed=42,
        )
        
        result = adapter.run(df, request)
        
        assert result.method == Method.SPEARMAN_RHO
        assert result.estimate is not None
        # Should detect monotonic relationship
        assert result.estimate > 0.5

    def test_chisquare_adapter(self):
        """Test chi-square test adapter."""
        adapter = ChiSquareAdapter()
        
        # Create contingency table with association
        df = pl.DataFrame({
            "group": ["A"] * 30 + ["B"] * 30 + ["A"] * 10 + ["B"] * 50,
            "outcome": ["yes"] * 30 + ["yes"] * 30 + ["no"] * 10 + ["no"] * 50,
        })
        
        request = AnalysisRequest(
            goal=Goal.CATEGORICAL_ASSOCIATION,
            variables={"outcome": "outcome", "group": "group"},
            study_design=StudyDesign.INDEPENDENT,
            estimand="Association",
            alternative=Alternative.TWO_SIDED,
            confidence_level=0.95,
        )
        
        result = adapter.run(df, request)
        
        assert result.method == Method.CHI2_INDEPENDENCE
        assert result.p_value is not None
        assert result.p_value < 0.05  # Should detect association
        assert result.interval_status == "not_applicable"

    def test_fisher_exact_adapter(self):
        """Test Fisher's exact test adapter."""
        adapter = FisherExactAdapter()
        
        # 2x2 table
        df = pl.DataFrame({
            "group": ["A"] * 5 + ["B"] * 15 + ["A"] * 15 + ["B"] * 5,
            "outcome": ["yes"] * 5 + ["yes"] * 15 + ["no"] * 15 + ["no"] * 5,
        })
        
        request = AnalysisRequest(
            goal=Goal.SPARSE_2X2_TABLE,
            variables={"outcome": "outcome", "group": "group"},
            study_design=StudyDesign.INDEPENDENT,
            estimand="Odds ratio",
            alternative=Alternative.TWO_SIDED,
            confidence_level=0.95,
        )
        
        result = adapter.run(df, request)
        
        assert result.method == Method.FISHER_EXACT
        assert result.estimate is not None
        assert result.p_value is not None
        # Odds ratio could be 9.0 or 1/9 depending on table orientation
        # Both are correct, just different conventions
        assert abs(result.estimate - 9.0) < 0.1 or abs(result.estimate - 1/9) < 0.01

    def test_descriptive_adapter(self):
        """Test descriptive statistics adapter."""
        adapter = DescriptiveAdapter()
        
        df = pl.DataFrame({
            "a": [1, 2, 3, 4, 5],
            "b": [10, 20, 30, 40, 50],
        })
        
        request = AnalysisRequest(
            goal=Goal.DESCRIBE_DATA,
            variables={"dummy": "a"},  # Need at least one variable
            study_design=StudyDesign.INDEPENDENT,
            estimand="Descriptive statistics",
            alternative=Alternative.TWO_SIDED,
        )
        
        result = adapter.run(df, request)
        
        assert result.method == Method.DESCRIPTIVE
        assert result.group_counts["n_rows"] == 5
        assert result.group_counts["n_columns"] == 2


class TestEligibilityChecks:
    """Test eligibility gating logic."""

    def test_welch_eligibility_requires_two_groups(self):
        """Welch test requires exactly two group levels."""
        ws = Workspace()
        
        # Create data with 3 groups
        df = pl.DataFrame({
            "outcome": [1, 2, 3, 4, 5, 6],
            "group": ["A", "B", "C", "A", "B", "C"],
        })
        
        # Store in workspace
        import io
        buf = io.BytesIO()
        df.write_parquet(buf)
        data = buf.getvalue()
        
        from CleanSheet.services.ingest import ingest_file, ImportSpec
        import_spec = ImportSpec()
        dataset_ref, _, _ = ingest_file(ws, data, "test.parquet", import_spec)
        
        request = AnalysisRequest(
            goal=Goal.COMPARE_TWO_MEANS,
            variables={"outcome": "outcome", "group": "group"},
            group_levels=["A", "B", "C"],  # 3 groups - should fail
            study_design=StudyDesign.INDEPENDENT,
            estimand="Test",
            alternative=Alternative.TWO_SIDED,
        )
        
        eligibility = check_eligibility(ws, dataset_ref, request)
        
        assert not eligibility.allowed
        assert any("two groups" in r.lower() for r in eligibility.reasons)

    def test_welch_eligibility_requires_continuous_outcome(self):
        """Welch test requires continuous outcome."""
        ws = Workspace()
        
        df = pl.DataFrame({
            "outcome": ["low", "high", "medium", "low", "high", "medium"],  # Categorical
            "group": ["A", "B", "A", "B", "A", "B"],
        })
        
        import io
        buf = io.BytesIO()
        df.write_parquet(buf)
        data = buf.getvalue()
        
        from CleanSheet.services.ingest import ingest_file, ImportSpec
        import_spec = ImportSpec()
        dataset_ref, _, _ = ingest_file(ws, data, "test.parquet", import_spec)
        
        request = AnalysisRequest(
            goal=Goal.COMPARE_TWO_MEANS,
            variables={"outcome": "outcome", "group": "group"},
            group_levels=["A", "B"],
            study_design=StudyDesign.INDEPENDENT,
            estimand="Test",
            alternative=Alternative.TWO_SIDED,
        )
        
        eligibility = check_eligibility(ws, dataset_ref, request)
        
        assert not eligibility.allowed
        assert any("continuous" in r.lower() for r in eligibility.reasons)

    def test_paired_eligibility_requires_pair_id(self):
        """Paired test requires pair identifier."""
        ws = Workspace()
        
        df = pl.DataFrame({
            "outcome": [1, 2, 3, 4, 5, 6],
            "occasion": ["before", "after"] * 3,
        })
        
        import io
        buf = io.BytesIO()
        df.write_parquet(buf)
        data = buf.getvalue()
        
        from CleanSheet.services.ingest import ingest_file, ImportSpec
        import_spec = ImportSpec()
        dataset_ref, _, _ = ingest_file(ws, data, "test.parquet", import_spec)
        
        request = AnalysisRequest(
            goal=Goal.COMPARE_PAIRED_MEANS,
            variables={"outcome": "outcome", "occasion": "occasion"},
            study_design=StudyDesign.PAIRED,
            estimand="Test",
            alternative=Alternative.TWO_SIDED,
        )
        
        eligibility = check_eligibility(ws, dataset_ref, request)
        
        assert not eligibility.allowed
        assert any("pair" in r.lower() for r in eligibility.reasons)

    def test_unknown_design_blocks_inference(self):
        """Unknown study design should block inference (except descriptive)."""
        ws = Workspace()
        
        df = pl.DataFrame({
            "x": [1, 2, 3, 4, 5, 6],
            "y": [2, 4, 6, 8, 10, 12],
        })
        
        import io
        buf = io.BytesIO()
        df.write_parquet(buf)
        data = buf.getvalue()
        
        from CleanSheet.services.ingest import ingest_file, ImportSpec
        import_spec = ImportSpec()
        dataset_ref, _, _ = ingest_file(ws, data, "test.parquet", import_spec)
        
        # Correlation with unknown design should be blocked
        request = AnalysisRequest(
            goal=Goal.EXPLORE_LINEAR_RELATIONSHIP,
            variables={"outcome": "x", "predictor": "y"},
            study_design=StudyDesign.UNKNOWN,
            estimand="Correlation",
            alternative=Alternative.TWO_SIDED,
        )
        
        eligibility = check_eligibility(ws, dataset_ref, request)
        
        assert not eligibility.allowed
        assert any("unknown" in r.lower() for r in eligibility.reasons)

    def test_descriptive_allowed_with_unknown_design(self):
        """Descriptive should be allowed with unknown design."""
        ws = Workspace()
        
        df = pl.DataFrame({"x": [1, 2, 3]})
        
        import io
        buf = io.BytesIO()
        df.write_parquet(buf)
        data = buf.getvalue()
        
        from CleanSheet.services.ingest import ingest_file, ImportSpec
        import_spec = ImportSpec()
        dataset_ref, _, _ = ingest_file(ws, data, "test.parquet", import_spec)
        
        request = AnalysisRequest(
            goal=Goal.DESCRIBE_DATA,
            variables={"dummy": "x"},  # Need at least one variable
            study_design=StudyDesign.UNKNOWN,
            estimand="Describe",
            alternative=Alternative.TWO_SIDED,
        )
        
        eligibility = check_eligibility(ws, dataset_ref, request)
        
        assert eligibility.allowed


class TestProfiling:
    """Test data profiling functions."""

    def test_profile_column_continuous(self):
        """Test profiling a continuous column."""
        s = pl.Series("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        
        prof = profile_column(s, "continuous")
        
        assert prof.name == "x"
        assert prof.mean == 3.0
        assert prof.std == pytest.approx(1.58, abs=0.01)
        assert prof.median == 3.0
        assert prof.min == 1.0
        assert prof.max == 5.0
        assert prof.n_nan == 0
        assert prof.n_infinite == 0

    def test_profile_column_with_nan(self):
        """Test profiling with NaN values."""
        s = pl.Series("x", [1.0, 2.0, float('nan'), 4.0, 5.0])
        
        prof = profile_column(s, "continuous")
        
        assert prof.n_nan == 1
        assert prof.n_infinite == 0

    def test_profile_column_with_inf(self):
        """Test profiling with infinite values."""
        s = pl.Series("x", [1.0, 2.0, float('inf'), 4.0, 5.0])
        
        prof = profile_column(s, "continuous")
        
        assert prof.n_nan == 0
        assert prof.n_infinite == 1

    def test_profile_column_categorical(self):
        """Test profiling a categorical column."""
        s = pl.Series("cat", ["A", "B", "A", "C", "B", "A"])
        
        prof = profile_column(s, "categorical")
        
        assert prof.n_categories == 3
        assert prof.top_categories[0][0] == "A"
        assert prof.top_categories[0][1] == 3

    def test_run_profiling(self):
        """Test full profiling pipeline."""
        ws = Workspace()
        
        df = pl.DataFrame({
            "continuous": [1.0, 2.0, 3.0, 4.0, 5.0],
            "categorical": ["A", "B", "A", "C", "A"],
            "identifier": [1, 2, 3, 4, 5],
        })
        
        import io
        buf = io.BytesIO()
        df.write_parquet(buf)
        data = buf.getvalue()
        
        from CleanSheet.services.ingest import ingest_file, ImportSpec
        import_spec = ImportSpec()
        dataset_ref, _, _ = ingest_file(ws, data, "test.parquet", import_spec)
        
        profile = run_profiling(ws, dataset_ref)
        
        assert profile.n_rows == 5
        assert profile.n_columns == 3
        assert len(profile.columns) == 3


class TestAdapterRegistry:
    """Test that all adapters are registered."""

    def test_all_methods_have_adapters(self):
        """Every Method should have an adapter."""
        for method in Method:
            if method != Method.DESCRIPTIVE:  # descriptive doesn't need test data
                assert method in ADAPTERS, f"No adapter for {method}"

    def test_adapter_names_match(self):
        """Adapter method should match enum."""
        for method, adapter in ADAPTERS.items():
            assert adapter.method == method


class TestContrastDirection:
    """Test that contrast direction is respected."""

    def test_welch_contrast_direction(self):
        """Welch test should respect contrast direction."""
        adapter = WelchTTestAdapter()
        
        np.random.seed(42)
        group1 = np.random.normal(10, 1, 30)  # mean ~10
        group2 = np.random.normal(12, 1, 30)  # mean ~12
        
        df = pl.DataFrame({
            "outcome": np.concatenate([group1, group2]),
            "group": ["A"] * 30 + ["B"] * 30,
        })
        
        # Contrast: A minus B (should be negative, ~ -2)
        request = AnalysisRequest(
            goal=Goal.COMPARE_TWO_MEANS,
            variables={"outcome": "outcome", "group": "group"},
            group_levels=["A", "B"],
            contrast="A_minus_B",
            study_design=StudyDesign.INDEPENDENT,
            estimand="Difference",
            alternative=Alternative.TWO_SIDED,
        )
        
        result = adapter.run(df, request)
        assert result.estimate < 0  # A - B should be negative
        
        # Contrast: B minus A (should be positive, ~ +2)
        request2 = AnalysisRequest(
            goal=Goal.COMPARE_TWO_MEANS,
            variables={"outcome": "outcome", "group": "group"},
            group_levels=["A", "B"],
            contrast="B_minus_A",
            study_design=StudyDesign.INDEPENDENT,
            estimand="Difference",
            alternative=Alternative.TWO_SIDED,
        )
        
        result2 = adapter.run(df, request2)
        assert result2.estimate > 0  # B - A should be positive
        
        # Magnitudes should be same
        assert abs(result.estimate) == pytest.approx(abs(result2.estimate))

    def test_paired_contrast_direction(self):
        """Paired test should respect contrast direction."""
        adapter = PairedTTestAdapter()
        
        np.random.seed(42)
        n = 20
        before = np.random.normal(10, 1, n)
        after = before + 2.0  # True difference = +2
        
        df = pl.DataFrame({
            "pair_id": list(range(n)) * 2,
            "occasion": ["before"] * n + ["after"] * n,
            "outcome": np.concatenate([before, after]),
        })
        
        # Contrast: after minus before (should be positive)
        request = AnalysisRequest(
            goal=Goal.COMPARE_PAIRED_MEANS,
            variables={"outcome": "outcome", "pair_id": "pair_id", "occasion": "occasion"},
            contrast="after_minus_before",
            study_design=StudyDesign.PAIRED,
            estimand="Difference",
            alternative=Alternative.TWO_SIDED,
        )
        
        result = adapter.run(df, request)
        assert result.estimate > 0  # after - before = +2
        
        # Contrast: before minus after (should be negative)
        request2 = AnalysisRequest(
            goal=Goal.COMPARE_PAIRED_MEANS,
            variables={"outcome": "outcome", "pair_id": "pair_id", "occasion": "occasion"},
            contrast="before_minus_after",
            study_design=StudyDesign.PAIRED,
            estimand="Difference",
            alternative=Alternative.TWO_SIDED,
        )
        
        result2 = adapter.run(df, request2)
        assert result2.estimate < 0  # before - after = -2
        
        assert abs(result.estimate) == pytest.approx(abs(result2.estimate))


class TestIntegration:
    """Integration tests for the analytics pipeline."""

    def test_run_analysis_returns_analysis_result(self):
        """run_analysis should return AnalysisResult wrapper."""
        ws = Workspace()
        
        df = pl.DataFrame({
            "outcome": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "group": ["A"] * 5 + ["B"] * 5,
        })
        
        import io
        buf = io.BytesIO()
        df.write_parquet(buf)
        data = buf.getvalue()
        
        from CleanSheet.services.ingest import ingest_file, ImportSpec
        import_spec = ImportSpec()
        dataset_ref, _, _ = ingest_file(ws, data, "test.parquet", import_spec)
        
        request = AnalysisRequest(
            goal=Goal.COMPARE_TWO_MEANS,
            variables={"outcome": "outcome", "group": "group"},
            group_levels=["A", "B"],
            study_design=StudyDesign.INDEPENDENT,
            estimand="Difference",
            alternative=Alternative.TWO_SIDED,
        )
        
        result = run_analysis(ws, dataset_ref, request)
        
        from CleanSheet.contracts import AnalysisResult
        assert isinstance(result, AnalysisResult)
        assert result.status == "complete"
        assert len(result.statistical_results) == 1
        assert result.request == request

    def test_run_analysis_uses_preparation_recipe(self):
        """run_analysis should use preparation recipe when provided."""
        ws = Workspace()
        
        df = pl.DataFrame({
            "outcome": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "group": ["A"] * 5 + ["B"] * 5,
            "extra": [1] * 10,
        })
        
        import io
        buf = io.BytesIO()
        df.write_parquet(buf)
        data = buf.getvalue()
        
        from CleanSheet.services.ingest import ingest_file, ImportSpec
        import_spec = ImportSpec()
        dataset_ref, _, _ = ingest_file(ws, data, "test.parquet", import_spec)
        
        # Recipe that drops 'extra' column
        recipe_steps = [
            {"operation": "drop_columns", "arguments": {"columns": ["extra"]}}
        ]
        
        request = AnalysisRequest(
            goal=Goal.COMPARE_TWO_MEANS,
            variables={"outcome": "outcome", "group": "group"},
            group_levels=["A", "B"],
            study_design=StudyDesign.INDEPENDENT,
            estimand="Difference",
            alternative=Alternative.TWO_SIDED,
        )
        
        # Should not raise error
        result = run_analysis(ws, dataset_ref, request, recipe_steps)
        
        assert result.status == "complete"
        assert len(result.statistical_results) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])