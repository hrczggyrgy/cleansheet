"""Application configuration and resource budgets.

All limits are configurable via environment variables with conservative defaults.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "CleanSheet"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # Streamlit
    streamlit_port: int = 8501
    streamlit_address: str = "localhost"
    streamlit_headless: bool = True
    streamlit_browser_gather_usage_stats: bool = False

    # Resource budgets (conservative defaults from blueprint)
    max_upload_size_mb: int = Field(default=50, ge=1, le=500)
    max_scalar_columns: int = Field(default=200, ge=10, le=1000)
    max_profiling_columns: int = Field(default=50, ge=5, le=200)
    preview_rows: int = Field(default=100, ge=10, le=1000)
    max_plot_points: int = Field(default=20000, ge=1000, le=100000)
    max_display_categories: int = Field(default=20, ge=5, le=100)
    max_correlation_columns: int = Field(default=20, ge=5, le=100)
    inference_materialization_limit_mib: int = Field(default=256, ge=64, le=2048)
    analysis_job_timeout_seconds: int = Field(default=30, ge=5, le=300)
    export_job_timeout_seconds: int = Field(default=60, ge=10, le=300)
    session_scratch_limit_mib: int = Field(default=512, ge=64, le=4096)
    session_inactivity_minutes: int = Field(default=30, ge=5, le=1440)

    # Concurrency
    max_concurrent_jobs: int = Field(default=1, ge=1, le=4)
    worker_process_timeout_seconds: int = Field(default=35, ge=10, le=400)

    # Paths
    data_dir: Path = Field(default=Path("data"))
    workspace_root: Path = Field(default=Path(".cleansheet_workspaces"))
    examples_dir: Path = Field(default=Path("examples/public-data"))
    scratch_dir: Path = Field(default=Path(".cleansheet_scratch"))
    export_dir: Path = Field(default=Path("exports"))

    # Security
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8501"])
    enable_cors: bool = False
    max_file_size_bytes: int = Field(default=50 * 1024 * 1024, description="Max upload size in bytes")

    # Polars
    polars_streaming: bool = True
    polars_max_threads: int | None = Field(default=None, description="None = auto")
    polars_spill_dir: Path | None = Field(default=None)

    # Statistical defaults
    default_confidence_level: float = Field(default=0.95, gt=0.5, lt=1.0)
    default_seed: int = Field(default=42, ge=0)
    bootstrap_resamples: int = Field(default=2000, ge=100, le=50000)
    permutation_resamples: int = Field(default=5000, ge=100, le=100000)

    # Reporting
    report_template_dir: Path = Field(default=Path("src/CleanSheet/reporting/templates"))
    include_data_in_export: bool = False
    formula_injection_protection: bool = True

    # Demo mode
    demo_mode: bool = False
    demo_dataset: str = "palmer_penguins"

    def __post_init__(self) -> None:
        # Ensure paths exist
        for path in [
            self.data_dir,
            self.workspace_root,
            self.scratch_dir,
            self.export_dir,
            self.report_template_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_resource_limits() -> dict[str, Any]:
    """Get resource limits as a dict for manifest recording."""
    s = get_settings()
    return {
        "max_upload_size_mb": s.max_upload_size_mb,
        "max_scalar_columns": s.max_scalar_columns,
        "max_profiling_columns": s.max_profiling_columns,
        "preview_rows": s.preview_rows,
        "max_plot_points": s.max_plot_points,
        "max_display_categories": s.max_display_categories,
        "max_correlation_columns": s.max_correlation_columns,
        "inference_materialization_limit_mib": s.inference_materialization_limit_mib,
        "analysis_job_timeout_seconds": s.analysis_job_timeout_seconds,
        "export_job_timeout_seconds": s.export_job_timeout_seconds,
        "session_scratch_limit_mib": s.session_scratch_limit_mib,
        "session_inactivity_minutes": s.session_inactivity_minutes,
        "max_concurrent_jobs": s.max_concurrent_jobs,
        "worker_process_timeout_seconds": s.worker_process_timeout_seconds,
    }


def get_dependency_versions() -> dict[str, str]:
    """Record exact dependency versions for reproducibility."""
    import importlib.metadata

    packages = [
        "streamlit", "polars", "pyarrow", "seaborn",
        "scipy", "statsmodels", "matplotlib", "numpy", "pandas", "pydantic",
    ]
    versions = {}
    for pkg in packages:
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = "not_installed"
    return versions
