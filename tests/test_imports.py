"""Basic import tests to verify package structure."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_imports():
    """Test that all modules can be imported."""
    from CleanSheet import config, contracts, errors
    from CleanSheet.engine import expressions, execution, sampling
    from CleanSheet.jobs import runner, workspace
    from CleanSheet.services import ingest, profile, prepare, recommend, statistics, visualize, reports
    from CleanSheet.ui import start, import_review, preparation, question, results, export
    from CleanSheet import cli

    assert config is not None
    assert contracts is not None
    assert errors is not None
    assert expressions is not None
    assert execution is not None
    assert sampling is not None
    assert runner is not None
    assert workspace is not None
    assert ingest is not None
    assert profile is not None
    assert prepare is not None
    assert recommend is not None
    assert statistics is not None
    assert visualize is not None
    assert reports is not None
    assert start is not None
    assert import_review is not None
    assert preparation is not None
    assert question is not None
    assert results is not None
    assert export is not None
    assert cli is not None


def test_contracts():
    """Test contract models."""
    from CleanSheet.contracts import (
        DatasetRef, ImportSpec, ColumnRole, AnalysisRequest,
        SemanticRole, Goal, Method, StudyDesign, JobStatus,
        compute_recipe_hash, compute_spec_hash,
    )
    from datetime import datetime

    # Test DatasetRef
    ref = DatasetRef(
        dataset_id="test123",
        workspace_id="ws123",
        source_sha256="a" * 64,
        format="csv",
        schema_hash="abc123",
        row_count=100,
        column_count=10,
    )
    assert ref.dataset_id == "test123"

    # Test ImportSpec
    spec = ImportSpec(encoding="utf-8", delimiter=",", decimal_comma=False)
    assert spec.encoding == "utf-8"

    # Test ColumnRole
    role = ColumnRole(
        column="age",
        physical_dtype="Int64",
        semantic_role=SemanticRole.CONTINUOUS,
    )
    assert role.semantic_role == SemanticRole.CONTINUOUS

    # Test AnalysisRequest
    req = AnalysisRequest(
        goal=Goal.COMPARE_TWO_MEANS,
        variables={"outcome": "age", "group": "treatment"},
        group_levels=["A", "B"],
        study_design=StudyDesign.INDEPENDENT,
        estimand="Difference in mean age",
    )
    assert req.goal == Goal.COMPARE_TWO_MEANS

    # Test hashes
    hash1 = compute_spec_hash(spec)
    hash2 = compute_spec_hash(spec)
    assert hash1 == hash2
    assert len(hash1) == 16


def test_config():
    """Test configuration loading."""
    from CleanSheet.config import get_settings, get_resource_limits

    settings = get_settings()
    assert settings.app_name == "CleanSheet"
    assert settings.max_upload_size_mb == 50

    limits = get_resource_limits()
    assert "max_upload_size_mb" in limits
    assert limits["max_upload_size_mb"] == 50


def test_expressions():
    """Test expression builders."""
    from CleanSheet.engine.expressions import (
        strip_strings, parse_dates, compute_revenue, filter_expression,
    )
    import polars as pl

    df = pl.DataFrame({
        "name": [" Alice ", "Bob", "Charlie"],
        "date_str": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "qty": [1, 2, 3],
        "price": [10.0, 20.0, 30.0],
    })

    # Test strip_strings
    exprs = strip_strings("name")
    result = df.with_columns(exprs)
    assert result["name"][0] == "Alice"

    # Test parse_dates
    exprs = parse_dates(["date_str"], format="%Y-%m-%d")
    result = df.with_columns(exprs)
    assert result["date_str"].dtype == pl.Date

    # Test compute_revenue
    expr = compute_revenue("qty", "price", "revenue")
    result = df.with_columns(expr)
    assert result["revenue"].to_list() == [10.0, 40.0, 90.0]

    # Test filter_expression
    filters = {"qty": {"min": 2}}
    expr = filter_expression(filters)
    result = df.filter(expr)
    assert result.height == 2


def test_sampling():
    """Test sampling utilities."""
    from CleanSheet.engine.sampling import stable_sample, SamplingPlan
    import polars as pl

    df = pl.DataFrame({"x": range(100), "y": range(100, 200)})

    # Test stable sample
    sample = stable_sample(df, 10, seed=42)
    assert sample.height == 10

    # Test reproducibility
    sample2 = stable_sample(df, 10, seed=42)
    assert sample["x"].to_list() == sample2["x"].to_list()

    # Test SamplingPlan
    plan = SamplingPlan("stable", 10, 42, 100)
    assert plan.method == "stable"
    assert plan.n == 10


if __name__ == "__main__":
    test_imports()
    test_contracts()
    test_config()
    test_expressions()
    test_sampling()
    print("All tests passed!")