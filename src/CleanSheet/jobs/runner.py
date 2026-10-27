"""Job runner for background analysis execution with resource limits."""

from __future__ import annotations

import multiprocessing as mp
import os
import signal
import uuid
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from CleanSheet.config import get_settings
from CleanSheet.contracts import AnalysisRequest, AnalysisResult, DatasetRef, JobStatus
from CleanSheet.errors import CancellationError, JobError, TimeoutError
from CleanSheet.jobs.workspace import Workspace, get_workspace_manager


class JobPriority(int, Enum):
    LOW = 0
    NORMAL = 50
    HIGH = 100


@dataclass
class JobSpec:
    """Specification for a background job."""

    job_id: str
    job_type: str
    workspace_id: str
    dataset_ref: DatasetRef
    payload: dict[str, Any]
    priority: JobPriority = JobPriority.NORMAL
    timeout_seconds: int = 30
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: JobStatus = JobStatus.QUEUED
    result: Any = None
    error: str | None = None
    resource_usage: dict[str, Any] = field(default_factory=dict)


class JobRunner:
    """Manages job queue and worker processes."""

    def __init__(self, max_workers: int | None = None) -> None:
        self.settings = get_settings()
        self.max_workers = max_workers or self.settings.max_concurrent_jobs
        self._executor: ProcessPoolExecutor | None = None
        self._jobs: dict[str, JobSpec] = {}
        self._futures: dict[str, Any] = {}
        self._workspace_manager = get_workspace_manager()

    def start(self) -> None:
        """Start the job runner."""
        if self._executor is None:
            self._executor = ProcessPoolExecutor(
                max_workers=self.max_workers,
                mp_context=mp.get_context("spawn"),
            )

    def stop(self, wait: bool = True) -> None:
        """Stop the job runner."""
        if self._executor:
            self._executor.shutdown(wait=wait, cancel_futures=not wait)
            self._executor = None

    def submit(
        self,
        job_type: str,
        workspace_id: str,
        dataset_ref: DatasetRef,
        payload: dict[str, Any],
        timeout_seconds: int | None = None,
        priority: JobPriority = JobPriority.NORMAL,
    ) -> str:
        """Submit a job for execution."""
        if self._executor is None:
            self.start()

        job_id = uuid.uuid4().hex[:12]
        timeout = timeout_seconds or self.settings.analysis_job_timeout_seconds

        spec = JobSpec(
            job_id=job_id,
            job_type=job_type,
            workspace_id=workspace_id,
            dataset_ref=dataset_ref,
            payload=payload,
            priority=priority,
            timeout_seconds=timeout,
        )

        self._jobs[job_id] = spec

        # Submit to executor
        future = self._executor.submit(_execute_job, spec)
        self._futures[job_id] = future

        return job_id

    def get_status(self, job_id: str) -> JobSpec | None:
        """Get job status."""
        spec = self._jobs.get(job_id)
        if spec is None:
            return None

        future = self._futures.get(job_id)
        if future and future.done():
            try:
                result = future.result(timeout=0)
                spec.status = JobStatus.COMPLETE
                spec.result = result
                spec.completed_at = datetime.utcnow()
            except FuturesTimeoutError:
                pass
            except Exception as e:
                spec.status = JobStatus.FAILED
                spec.error = str(e)
                spec.completed_at = datetime.utcnow()

        return spec

    def cancel(self, job_id: str) -> bool:
        """Cancel a running job."""
        future = self._futures.get(job_id)
        spec = self._jobs.get(job_id)

        if future and not future.done():
            cancelled = future.cancel()
            if cancelled and spec:
                spec.status = JobStatus.CANCELLED
                spec.completed_at = datetime.utcnow()
            return cancelled

        return False

    def wait_for(self, job_id: str, timeout: float | None = None) -> JobSpec | None:
        """Wait for job completion."""
        future = self._futures.get(job_id)
        if future is None:
            return self._jobs.get(job_id)

        try:
            future.result(timeout=timeout)
        except FuturesTimeoutError:
            pass
        except Exception:
            pass

        return self.get_status(job_id)

    def list_jobs(self, workspace_id: str | None = None) -> list[JobSpec]:
        """List jobs, optionally filtered by workspace."""
        jobs = list(self._jobs.values())
        if workspace_id:
            jobs = [j for j in jobs if j.workspace_id == workspace_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)


# Global job runner
_job_runner: JobRunner | None = None


def get_job_runner() -> JobRunner:
    """Get global job runner."""
    global _job_runner
    if _job_runner is None:
        _job_runner = JobRunner()
    return _job_runner


# Worker functions (must be at module level for pickling)

def _execute_job(spec: JobSpec) -> Any:
    """Execute a job in a worker process."""
    spec.started_at = datetime.utcnow()

    # Set resource limits in worker
    _set_worker_limits(spec.timeout_seconds)

    try:
        # Route to appropriate handler
        if spec.job_type == "analyze":
            return _run_analysis(spec)
        if spec.job_type == "profile":
            return _run_profiling(spec)
        if spec.job_type == "plot":
            return _run_plotting(spec)
        if spec.job_type == "export":
            return _run_export(spec)
        if spec.job_type == "discovery":
            return _run_discovery(spec)
        raise JobError(f"Unknown job type: {spec.job_type}", job_id=spec.job_id)

    except CancellationError:
        raise
    except TimeoutError:
        raise
    except Exception as e:
        raise JobError(f"Job failed: {e}", job_id=spec.job_id, stage=spec.job_type) from e


def _set_worker_limits(timeout_seconds: int) -> None:
    """Set resource limits for worker process."""
    # Set CPU time limit (soft)
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds, timeout_seconds + 5))

    # Set memory limit if possible (Linux)
    try:
        mem_limit = 2 * 1024 * 1024 * 1024  # 2GB
        resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
    except (ValueError, OSError):
        pass  # Not supported on this platform


def _run_analysis(spec: JobSpec) -> AnalysisResult:
    """Run statistical analysis."""
    from CleanSheet.services.statistics import run_analysis

    ws = Workspace(spec.workspace_id)
    request = AnalysisRequest.model_validate(spec.payload["request"])

    result = run_analysis(ws, spec.dataset_ref, request)

    # Store result artifact
    result_json = result.model_dump_json(indent=2)
    ws.store_artifact(f"result_{spec.job_id}.json", result_json.encode())

    return result


def _run_profiling(spec: JobSpec) -> dict[str, Any]:
    """Run data profiling."""
    from CleanSheet.services.profile import run_profiling

    ws = Workspace(spec.workspace_id)
    result = run_profiling(ws, spec.dataset_ref)

    ws.store_artifact(f"profile_{spec.job_id}.json", result.model_dump_json(indent=2).encode())

    return result


def _run_plotting(spec: JobSpec) -> dict[str, Any]:
    """Run plot generation."""
    from CleanSheet.services.visualize import generate_plots

    ws = Workspace(spec.workspace_id)
    plot_specs = [__import__("CleanSheet.contracts", fromlist=["PlotSpec"]).PlotSpec.model_validate(s) for s in spec.payload["plots"]]

    artifacts = generate_plots(ws, spec.dataset_ref, plot_specs)

    return {"plots": artifacts}


def _run_export(spec: JobSpec) -> dict[str, Any]:
    """Run export job."""
    from CleanSheet.services.reports import generate_export

    ws = Workspace(spec.workspace_id)
    result = generate_export(ws, spec.payload)

    return {"export_path": result}


def _run_discovery(spec: JobSpec) -> list[dict]:
    """Run autonomous discovery job in background."""
    from CleanSheet.engine.profiling import run_progressive_discovery
    from CleanSheet.contracts import ColumnRole

    ws = Workspace(spec.workspace_id)
    
    # Reconstruct column roles
    column_roles = [ColumnRole(**cr) for cr in spec.payload.get("column_roles", [])]
    recipe_steps = spec.payload.get("recipe_steps")
    target_column = spec.payload.get("target_column")
    
    # Run discovery (no progress callback in background job)
    candidates = run_progressive_discovery(
        workspace=ws,
        dataset_ref=spec.dataset_ref,
        column_roles=column_roles,
        recipe_steps=recipe_steps,
        target_column=target_column,
        progress_callback=None,
        cancellation_token=None,
    )
    
    # Convert to serializable format
    return [c.model_dump() for c in candidates]


def run_in_process(
    func: Callable[..., Any],
    *args: Any,
    timeout_seconds: int = 30,
    **kwargs: Any,
) -> Any:
    """Run a function in a separate process with timeout."""
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError:
            # Force terminate
            for pid in list(executor._processes.keys()) if hasattr(executor, "_processes") else []:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
            raise TimeoutError(f"Process timed out after {timeout_seconds}s", timeout_seconds=timeout_seconds)
