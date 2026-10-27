"""Workspace management for session-isolated file operations."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from CleanSheet.config import get_settings
from CleanSheet.contracts import DatasetRef, ImportSpec
from CleanSheet.errors import ResourceLimitError, WorkspaceError


class Workspace:
    """Manages a session's private workspace with resource limits."""

    def __init__(self, workspace_id: str | None = None) -> None:
        self.settings = get_settings()
        self.workspace_id = workspace_id or uuid.uuid4().hex[:12]
        self.root = self.settings.workspace_root / self.workspace_id
        self.scratch = self.settings.scratch_dir / self.workspace_id
        self._created = datetime.now(UTC)
        self._size_bytes = 0
        self._setup()

    def _setup(self) -> None:
        """Create workspace directories with restrictive permissions."""
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Create a marker file for identification
        (self.root / ".workspace_id").write_text(self.workspace_id)

    @property
    def size_bytes(self) -> int:
        """Calculate current workspace size."""
        if self._size_bytes == 0:
            self._recalculate_size()
        return self._size_bytes

    def _recalculate_size(self) -> None:
        """Recalculate total workspace size."""
        total = 0
        for root in [self.root, self.scratch]:
            if root.exists():
                for f in root.rglob("*"):
                    if f.is_file():
                        try:
                            total += f.stat().st_size
                        except OSError:
                            pass
        self._size_bytes = total

    def check_space(self, additional_bytes: int = 0) -> None:
        """Verify workspace has space for additional data."""
        limit = self.settings.session_scratch_limit_mib * 1024 * 1024
        if self.size_bytes + additional_bytes > limit:
            raise ResourceLimitError(
                f"Workspace size limit exceeded: {self.size_bytes + additional_bytes} > {limit}",
                limit_type="session_scratch_limit_mib",
                limit_value=self.settings.session_scratch_limit_mib,
                actual_value=(self.size_bytes + additional_bytes) / (1024 * 1024),
            )

    def store_source(self, data: bytes, fmt: str, import_spec: ImportSpec) -> DatasetRef:
        """Store original source bytes and return DatasetRef."""
        self.check_space(len(data))

        sha256 = hashlib.sha256(data).hexdigest()
        dataset_id = sha256[:16]

        # Store original bytes
        source_path = self.root / f"{dataset_id}.source.{fmt}"
        source_path.write_bytes(data)

        # Store import spec
        spec_path = self.root / f"{dataset_id}.import_spec.json"
        spec_path.write_text(import_spec.model_dump_json(indent=2))

        # Read schema from source
        if fmt == "csv":
            import io
            # Extract only valid scan_csv arguments from ImportSpec
            csv_args = {
                "separator": import_spec.delimiter,
                "encoding": import_spec.encoding,
                "decimal_comma": import_spec.decimal_comma,
                "null_values": import_spec.null_tokens,
                "infer_schema_length": import_spec.infer_schema_length,
                "try_parse_dates": False,
            }
            lf = pl.scan_csv(io.BytesIO(data), **csv_args)
        else:
            import io
            lf = pl.scan_parquet(io.BytesIO(data))

        schema = lf.collect_schema()
        # Convert Polars dtypes to strings for JSON serialization
        schema_serializable = {k: str(v) for k, v in schema.items()}
        schema_hash = hashlib.sha256(
            json.dumps(sorted(schema_serializable.items())).encode()
        ).hexdigest()[:16]

        # Get dimensions
        try:
            preview = lf.limit(1).collect()
            row_count = lf.select(pl.len()).collect().item()
            column_count = len(schema)
        except Exception:
            row_count = 0
            column_count = len(schema)

        self._recalculate_size()

        return DatasetRef(
            dataset_id=dataset_id,
            workspace_id=self.workspace_id,
            source_sha256=sha256,
            format=fmt,
            schema_hash=schema_hash,
            row_count=row_count,
            column_count=column_count,
        )

    def get_source_path(self, dataset_ref: DatasetRef) -> Path:
        """Get path to stored source file."""
        path = self.root / f"{dataset_ref.dataset_id}.source.{dataset_ref.format}"
        if not path.exists():
            raise WorkspaceError(
                f"Source file not found: {path}",
                workspace_id=self.workspace_id,
                operation="get_source_path",
            )
        return path

    def get_import_spec(self, dataset_ref: DatasetRef) -> ImportSpec:
        """Retrieve stored import spec."""
        path = self.root / f"{dataset_ref.dataset_id}.import_spec.json"
        if not path.exists():
            raise WorkspaceError(
                f"Import spec not found: {path}",
                workspace_id=self.workspace_id,
                operation="get_import_spec",
            )
        return ImportSpec.model_validate_json(path.read_text())

    def store_prepared(self, df: pl.DataFrame, recipe_hash: str) -> Path:
        """Store prepared dataset as Parquet."""
        self.check_space(df.estimated_size())

        path = self.root / f"prepared_{recipe_hash}.parquet"
        df.write_parquet(path)
        self._recalculate_size()
        return path

    def get_prepared_path(self, recipe_hash: str) -> Path | None:
        """Get path to prepared dataset if it exists."""
        path = self.root / f"prepared_{recipe_hash}.parquet"
        return path if path.exists() else None

    def store_artifact(self, name: str, data: bytes, subdir: str = "artifacts") -> Path:
        """Store an artifact (plot, report, etc.)."""
        self.check_space(len(data))

        artifact_dir = self.root / subdir
        artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        path = artifact_dir / name
        path.write_bytes(data)
        self._recalculate_size()
        return path

    def get_artifact_path(self, name: str, subdir: str = "artifacts") -> Path | None:
        """Get artifact path if it exists."""
        path = self.root / subdir / name
        return path if path.exists() else None

    def store_plot(self, name: str, png_bytes: bytes) -> Path:
        """Store a plot PNG."""
        return self.store_artifact(name, png_bytes, "plots")

    def store_report(self, name: str, content: str) -> Path:
        """Store a report file."""
        return self.store_artifact(name, content.encode("utf-8"), "reports")

    def cleanup(self, force: bool = False) -> None:
        """Remove workspace directories."""
        if force or self._should_cleanup():
            for path in [self.root, self.scratch]:
                if path.exists():
                    shutil.rmtree(path, ignore_errors=True)

    def _should_cleanup(self) -> bool:
        """Check if workspace should be cleaned up due to inactivity."""
        if self.settings.environment == "production":
            inactive_threshold = datetime.now(UTC) - timedelta(minutes=self.settings.session_inactivity_minutes)
            return self._created < inactive_threshold
        return False

    @contextmanager
    def temp_file(self, suffix: str = ".tmp") -> Any:
        """Create a temporary file in workspace scratch."""
        self.check_space(1024 * 1024)  # Reserve 1MB
        fd, path = tempfile.mkstemp(suffix=suffix, dir=self.scratch)
        os.close(fd)
        try:
            yield Path(path)
        finally:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    def list_artifacts(self) -> list[Path]:
        """List all artifacts in workspace."""
        artifacts = []
        for subdir in ["artifacts", "plots", "reports"]:
            d = self.root / subdir
            if d.exists():
                artifacts.extend(d.iterdir())
        return artifacts

    def __repr__(self) -> str:
        return f"Workspace(id={self.workspace_id}, root={self.root}, size_mb={self.size_bytes/1024/1024:.1f})"


class WorkspaceManager:
    """Manages multiple workspaces with janitor cleanup."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._active: dict[str, Workspace] = {}

    def create(self, workspace_id: str | None = None) -> Workspace:
        """Create a new workspace."""
        ws = Workspace(workspace_id)
        self._active[ws.workspace_id] = ws
        return ws

    def get(self, workspace_id: str) -> Workspace | None:
        """Get existing workspace or create if not tracked."""
        if workspace_id in self._active:
            return self._active[workspace_id]

        # Check if workspace exists on disk
        root = self.settings.workspace_root / workspace_id
        if root.exists():
            ws = Workspace(workspace_id)
            self._active[workspace_id] = ws
            return ws

        return None

    def remove(self, workspace_id: str, force: bool = False) -> bool:
        """Remove a workspace."""
        ws = self.get(workspace_id)
        if ws:
            ws.cleanup(force=force)
            self._active.pop(workspace_id, None)
            return True
        return False

    def cleanup_all(self, force: bool = False) -> int:
        """Clean up all tracked workspaces."""
        count = 0
        for ws_id in list(self._active.keys()):
            if self.remove(ws_id, force=force):
                count += 1
        return count

    def janitor(self, max_age_minutes: int | None = None) -> int:
        """Clean up abandoned workspaces older than max_age_minutes."""
        if max_age_minutes is None:
            max_age_minutes = self.settings.session_inactivity_minutes * 2

        count = 0
        cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)

        if not self.settings.workspace_root.exists():
            return 0

        for ws_dir in self.settings.workspace_root.iterdir():
            if not ws_dir.is_dir():
                continue

            marker = ws_dir / ".workspace_id"
            if not marker.exists():
                continue

            try:
                created_str = marker.read_text().strip()
                # Check directory mtime as fallback
                mtime = datetime.fromtimestamp(ws_dir.stat().st_mtime)
                if mtime < cutoff:
                    shutil.rmtree(ws_dir, ignore_errors=True)
                    count += 1
            except Exception:
                continue

        return count


# Global workspace manager instance
_workspace_manager: WorkspaceManager | None = None


def get_or_create_workspace(workspace_id: str | None = None) -> Workspace:
    """Get or create workspace by ID (for non-Streamlit contexts).
    
    In Streamlit contexts, use app.get_or_create_workspace() which uses session_state.
    """
    ws_manager = get_workspace_manager()

    if workspace_id is None:
        ws = ws_manager.create()
        return ws

    ws = ws_manager.get(workspace_id)
    if ws is None:
        ws = ws_manager.create(workspace_id)
    return ws


def get_workspace_manager() -> WorkspaceManager:
    """Get global workspace manager."""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager()
    return _workspace_manager
