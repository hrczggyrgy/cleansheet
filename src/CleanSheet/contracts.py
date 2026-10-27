"""Typed contracts for CleanSheet service boundaries.

All service inputs/outputs use Pydantic models for validation.
Unknown fields are forbidden where appropriate to catch contract drift.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SemanticRole(str, Enum):
    CONTINUOUS = "continuous"
    DISCRETE = "discrete"
    ORDINAL = "ordinal"
    NOMINAL = "nominal"
    BINARY = "binary"
    DATE = "date"
    DATETIME = "datetime"
    IDENTIFIER = "identifier"
    FREE_TEXT = "free_text"


class PhysicalDtype(str, Enum):
    INT64 = "Int64"
    FLOAT64 = "Float64"
    STRING = "String"
    BOOLEAN = "Boolean"
    DATE = "Date"
    DATETIME = "Datetime"
    CATEGORICAL = "Categorical"
    NULL = "Null"


class StudyDesign(str, Enum):
    INDEPENDENT = "independent"
    PAIRED = "paired"
    UNKNOWN = "unknown"


class CollectionType(str, Enum):
    OBSERVATIONAL = "observational"
    EXPERIMENTAL = "experimental"


class Goal(str, Enum):
    COMPARE_TWO_MEANS = "compare_two_means"
    COMPARE_PAIRED_MEANS = "compare_paired_means"
    COMPARE_K_MEANS = "compare_k_means"
    EXPLORE_LINEAR_RELATIONSHIP = "explore_linear_relationship"
    EXPLORE_ORDERED_RELATIONSHIP = "explore_ordered_relationship"
    CATEGORICAL_ASSOCIATION = "categorical_association"
    SPARSE_2X2_TABLE = "sparse_2x2_table"
    DESCRIBE_DATA = "describe_data"


class Method(str, Enum):
    WELCH_T = "welch_t"
    PAIRED_T = "paired_t"
    PEARSON_R = "pearson_r"
    SPEARMAN_RHO = "spearman_rho"
    CHI2_INDEPENDENCE = "chi2_independence"
    FISHER_EXACT = "fisher_exact"
    MANN_WHITNEY_U = "mann_whitney_u"
    WILCOXON_SIGNED_RANK = "wilcoxon_signed_rank"
    KRUSKAL_WALLIS = "kruskal_wallis"
    DUNN_POSTHOC = "dunn_posthoc"
    GAMES_HOWELL_POSTHOC = "games_howell_posthoc"
    DESCRIPTIVE = "descriptive"


class IntervalMethod(str, Enum):
    PARAMETRIC = "parametric"
    BOOTSTRAP_PERCENTILE = "bootstrap_percentile"
    BOOTSTRAP_BCA = "bootstrap_bca"
    PERMUTATION = "permutation"
    HODGES_LEHMANN = "hodges_lehmann"
    NOT_COMPUTED = "not_computed"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"
    FAILED = "failed"


class MissingPolicy(str, Enum):
    REQUIRED_COLUMNS_COMPLETE_CASES = "required_columns_complete_cases"
    AVAILABLE_CASES = "available_cases"


class NonFinitePolicy(str, Enum):
    EXCLUDE_AND_REPORT = "exclude_and_report"
    ERROR = "error"


class Alternative(str, Enum):
    TWO_SIDED = "two-sided"
    LESS = "less"
    GREATER = "greater"


class MultiplicityMethod(str, Enum):
    NONE = "none"
    HOLM = "holm"
    FDR_BH = "fdr_bh"


class JobStatus(str, Enum):
    EMPTY = "empty"
    IMPORT_REVIEW = "import_review"
    DATA_READY = "data_ready"
    PLAN_READY = "plan_ready"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    INVALIDATED = "invalidated"
    EXPORT_READY = "export_ready"


class TransformOp(str, Enum):
    RENAME = "rename"
    FILTER = "filter"
    CAST = "cast"
    DEDUPLICATE = "deduplicate"
    IMPUTE = "impute"
    DROP_COLUMNS = "drop_columns"
    RECODE_CATEGORICAL = "recode_categorical"
    TRIM_WHITESPACE = "trim_whitespace"
    MERGE_CATEGORIES = "merge_categories"
    FLAG_OUTLIERS = "flag_outliers"


class PlotType(str, Enum):
    HISTOGRAM = "histogram"
    ECDF = "ecdf"
    BOXPLOT = "boxplot"
    SCATTERPLOT = "scatterplot"
    COUNT_CHART = "count_chart"
    CORRELATION_HEATMAP = "correlation_heatmap"
    MISSINGNESS_MATRIX = "missingness_matrix"
    ESTIMATE_INTERVAL = "estimate_interval"
    RAINCLOUD = "raincloud"
    STRIP_PLOT = "strip_plot"
    PAIRED_SLOPE = "paired_slope"
    SPAGHETTI = "spaghetti"


class ExportFormat(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    CSV = "csv"
    JSON = "json"
    PNG = "png"
    SVG = "svg"


class AnalysisMode(str, Enum):
    GUIDED = "guided"
    TARGET_SCAN = "target_scan"
    AUTONOMOUS_DISCOVERY = "autonomous_discovery"


class DatasetRef(BaseModel):
    """Immutable reference to a dataset in the workspace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str = Field(..., description="Opaque server-generated identifier")
    workspace_id: str = Field(..., description="Session workspace reference")
    source_sha256: str = Field(..., description="SHA-256 of original input bytes")
    format: Literal["csv", "parquet"] = Field(..., description="Source format")
    schema_hash: str = Field(..., description="Hash of column names + physical dtypes")
    row_count: int = Field(..., ge=0, description="Number of rows in source")
    column_count: int = Field(..., ge=0, description="Number of columns in source")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_bytes(cls, data: bytes, workspace_id: str, fmt: Literal["csv", "parquet"]) -> DatasetRef:
        sha = hashlib.sha256(data).hexdigest()
        return cls(
            dataset_id=sha[:16],
            workspace_id=workspace_id,
            source_sha256=sha,
            format=fmt,
            schema_hash="",
            row_count=0,
            column_count=0,
        )


class ImportSpec(BaseModel):
    """Validated import configuration."""

    model_config = ConfigDict(extra="forbid")

    encoding: str = Field(default="utf8", description="Text encoding")
    delimiter: str = Field(default=",", description="CSV delimiter")
    decimal_comma: bool = Field(default=False, description="European decimal comma")
    date_format: str | None = Field(default=None, description="Explicit date format (e.g. %Y-%m-%d)")
    null_tokens: list[str] = Field(
        default_factory=lambda: ["", "NA", "N/A", ".", "-999", "null", "NULL"],
        description="Strings to parse as null",
    )
    schema_overrides: dict[str, PhysicalDtype] = Field(
        default_factory=dict,
        description="Explicit column type overrides",
    )
    infer_schema_length: int = Field(default=1000, ge=100, le=100000)

    @field_validator("delimiter")
    @classmethod
    def _validate_delimiter(cls, v: str) -> str:
        if len(v) != 1:
            raise ValueError("Delimiter must be a single character")
        return v


class StudyContext(BaseModel):
    """Study design context captured at upload."""

    model_config = ConfigDict(extra="forbid")

    row_independence: Literal["independent", "paired", "unknown"] = Field(
        default="unknown",
        description="Whether each row represents a separate unit or repeated measures",
    )
    collection_type: Literal["observational", "experimental"] = Field(
        default="observational",
        description="How the data was collected",
    )
    subject_id_column: str | None = Field(default=None, description="Column identifying repeated measures units")
    confirmed_by_user: bool = Field(default=False)
    auto_detected: bool = Field(default=False)
    detection_notes: str | None = None


class ColumnRole(BaseModel):
    """Semantic role assignment for a column."""

    model_config = ConfigDict(extra="forbid")

    column: str
    physical_dtype: PhysicalDtype
    semantic_role: SemanticRole
    ordinal_order: list[str] | None = Field(default=None, description="Ordered categories if ordinal")
    confirmed: bool = Field(default=False, description="User confirmed this role")
    suggested_by: Literal["auto", "user"] = Field(default="auto")
    confidence: Literal["high", "medium", "low"] = Field(default="medium")
    ambiguity_reason: str | None = Field(default=None)
    is_excluded: bool = Field(default=False, description="Excluded from statistical analysis")


class CleaningStep(BaseModel):
    """Single reversible transformation step."""

    model_config = ConfigDict(extra="forbid")

    step_id: int
    operation: TransformOp
    arguments: dict[str, Any] = Field(default_factory=dict)
    input_schema: dict[str, str]
    output_schema: dict[str, str]
    affected_row_count: int
    affected_column_count: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reversible: bool = Field(default=True)
    description: str = Field(default="")


class AnalysisRequest(BaseModel):
    """Validated analysis request from UI."""

    model_config = ConfigDict(extra="forbid")

    goal: Goal
    variables: dict[str, str] = Field(..., description="Role -> column name mapping")
    group_levels: list[str] | None = Field(default=None, description="Selected levels for categorical group")
    contrast: str | None = Field(default=None, description="Contrast direction (e.g. 'A_minus_B')")
    study_design: StudyDesign
    design_confirmation_source: Literal["user", "inferred"] = Field(default="user")
    estimand: str = Field(..., description="Human-readable quantity of interest")
    missing_policy: MissingPolicy = Field(default=MissingPolicy.REQUIRED_COLUMNS_COMPLETE_CASES)
    nonfinite_policy: NonFinitePolicy = Field(default=NonFinitePolicy.EXCLUDE_AND_REPORT)
    method: Method | None = Field(default=None, description="Auto-selected if None")
    alternative: Alternative = Field(default=Alternative.TWO_SIDED)
    confidence_level: float = Field(default=0.95, gt=0.5, lt=1.0)
    analysis_purpose: Literal["exploratory", "confirmatory"] = Field(default="exploratory")
    multiplicity: dict = Field(default_factory=lambda: {"method": "none", "family_size": 1})
    seed: int = Field(default=42, ge=0)

    @field_validator("variables")
    @classmethod
    def _validate_variables(cls, v: dict[str, str]) -> dict[str, str]:
        if not v:
            raise ValueError("At least one variable must be specified")
        return v


class EligibilityResult(BaseModel):
    """Result of eligibility check for a proposed analysis."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    rule_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    user_confirmations: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    suggested_method: Method | None = None
    blocked_reason: str | None = None


class AssumptionCheck(BaseModel):
    """Single assumption diagnostic result."""

    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool | None = None
    value: float | None = None
    threshold: float | None = None
    message: str = ""
    severity: Literal["info", "warning", "error"] = "info"


class AssumptionReport(BaseModel):
    """Complete assumption diagnostic report."""

    model_config = ConfigDict(extra="forbid")

    checks: list[AssumptionCheck] = Field(default_factory=list)
    routing_explanation: str = ""
    recommended_method: Method | None = None
    fallback_method: Method | None = None
    auto_routed: bool = False

    @property
    def all_passed(self) -> bool:
        return all(c.passed is not False for c in self.checks if c.severity != "info")

    @property
    def has_errors(self) -> bool:
        return any(c.severity == "error" and c.passed is False for c in self.checks)


class StatisticalResult(BaseModel):
    """Complete statistical result from an analysis."""

    model_config = ConfigDict(extra="forbid")

    method: Method
    group_counts: dict[str, int] = Field(default_factory=dict)
    estimate: float | None = None
    interval: tuple[float, float] | None = None
    interval_method: IntervalMethod = IntervalMethod.NOT_COMPUTED
    interval_status: Literal["computed", "not_computed", "blocked", "failed", "not_applicable"] = "not_computed"
    statistic: float | None = None
    degrees_of_freedom: float | int | None = None
    p_value: float | None = None
    adjusted_p_value: float | None = None
    q_value: float | None = None
    m_comparisons: int = 1
    exclusions: dict[str, int] = Field(default_factory=dict)
    assumption_checks: dict[str, Any] = Field(default_factory=dict)
    effect_size: float | None = None
    effect_size_interpretation: str | None = None
    effect_size_ci: tuple[float, float] | None = None
    unstandardized_effect: float | None = None
    unstandardized_effect_ci: tuple[float, float] | None = None
    effect_magnitude_label: Literal["negligible", "small", "moderate", "large"] | None = None


class PlotSpec(BaseModel):
    """Validated plot specification for rendering."""

    model_config = ConfigDict(extra="forbid")

    plot_type: PlotType
    variables: dict[str, str] = Field(..., description="Role -> column mapping")
    category_order: dict[str, list[str]] = Field(default_factory=dict)
    transform: dict[str, Any] = Field(default_factory=dict)
    aggregation: dict[str, Any] = Field(default_factory=dict)
    sampling: dict[str, Any] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    max_categories: int = Field(default=20, ge=1, le=100)
    max_points: int = Field(default=20000, ge=100, le=1000000)
    seed: int = Field(default=42, ge=0)


class AnalysisResult(BaseModel):
    """Complete analysis result with artifacts."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["complete", "partial", "failed"]
    request: AnalysisRequest
    statistical_results: list[StatisticalResult] = Field(default_factory=list)
    plots: list[PlotSpec] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DiscoveryCandidate(BaseModel):
    """Candidate finding from autonomous discovery."""

    model_config = ConfigDict(extra="forbid")

    question: str
    goal: Goal
    variables: dict[str, str]
    raw_p_value: float | None = None
    q_value: float | None = None
    effect_size: float | None = None
    effect_magnitude: float | None = None
    validity_score: float | None = None
    relevance_score: float | None = None
    interpretability_score: float | None = None
    redundancy_penalty: float = 1.0
    composite_score: float | None = None
    eligibility: EligibilityResult | None = None
    assumption_report: AssumptionReport | None = None
    is_redundant: bool = False
    reason: str = ""


class RunManifest(BaseModel):
    """Reproducibility manifest for a completed run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    input_fingerprint: str
    import_spec_hash: str
    schema_hash: str
    roles_hash: str
    recipe_hash: str
    analysis_spec_hash: str
    rules_version: str = "1.0"
    dependency_versions: dict[str, str] = Field(default_factory=dict)
    seeds: dict[str, int] = Field(default_factory=dict)
    timestamps: dict[str, datetime] = Field(default_factory=dict)
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    outcomes: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, data: str) -> RunManifest:
        return cls.model_validate_json(data)


class SessionState(BaseModel):
    """Serializable session state for persistence."""

    model_config = ConfigDict(extra="ignore")

    session_id: str
    workspace_id: str
    dataset_ref: DatasetRef | None = None
    import_spec: ImportSpec | None = None
    study_context: StudyContext | None = None
    column_roles: list[ColumnRole] = Field(default_factory=list)
    recipe: list[CleaningStep] = Field(default_factory=list)
    recipe_hash: str | None = None
    current_stage: JobStatus = JobStatus.EMPTY
    analysis_plan: AnalysisRequest | None = None
    analysis_mode: AnalysisMode = AnalysisMode.GUIDED
    active_job_id: str | None = None
    result_refs: dict[str, str] = Field(default_factory=dict)
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stale_results: bool = Field(default=False)


def compute_recipe_hash(recipe: list[CleaningStep]) -> str:
    """Compute deterministic hash of a transformation recipe."""
    serialized = json.dumps(
        [step.model_dump(mode="json") for step in recipe],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def compute_spec_hash(spec: BaseModel) -> str:
    """Compute deterministic hash of a Pydantic model."""
    serialized = spec.model_dump_json()
    # Sort keys for deterministic output
    import json
    data = json.loads(serialized)
    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]
