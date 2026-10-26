"""File ingestion and validation service."""

from __future__ import annotations

import hashlib
import io
import mimetypes
from pathlib import Path
from typing import Any

import polars as pl

from CleanSheet.config import get_settings
from CleanSheet.contracts import DatasetRef, ImportSpec
from CleanSheet.errors import ParsingError, ResourceLimitError, SecurityError
from CleanSheet.jobs.workspace import Workspace

# Allowed MIME types for upload
ALLOWED_MIME_TYPES = {
    "text/csv",
    "text/plain",
    "application/csv",
    "application/vnd.ms-excel",
    "application/octet-stream",  # Parquet
    "application/x-parquet",
    "application/parquet",
}

# Magic bytes for format detection
MAGIC_BYTES = {
    b"PAR1": "parquet",  # Parquet magic
    b"\x00\x00\x00\x00": "parquet",  # Alternative parquet
}


def detect_format(data: bytes, filename: str | None = None) -> str:
    """Detect file format from magic bytes and extension."""
    # Check magic bytes
    for magic, fmt in MAGIC_BYTES.items():
        if data.startswith(magic):
            return fmt

    # Check extension
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in [".csv", ".txt"]:
            return "csv"
        if ext in [".parquet", ".pq"]:
            return "parquet"

    # Default to CSV for text-like data
    try:
        data[:1024].decode("utf-8")
        return "csv"
    except UnicodeDecodeError:
        pass

    raise ParsingError("Unable to detect file format", format="unknown")


def validate_upload(data: bytes, filename: str | None = None) -> tuple[str, ImportSpec]:
    """Validate uploaded file and return format + import spec."""
    settings = get_settings()

    # Check size
    if len(data) > settings.max_file_size_bytes:
        raise ResourceLimitError(
            f"File size {len(data)} exceeds limit {settings.max_file_size_bytes}",
            limit_type="max_upload_size_mb",
            limit_value=settings.max_upload_size_mb,
            actual_value=len(data) / (1024 * 1024),
        )

    # Check MIME type if filename provided
    if filename:
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type and mime_type not in ALLOWED_MIME_TYPES:
            # Allow if extension matches
            ext = Path(filename).suffix.lower()
            if ext not in [".csv", ".parquet", ".pq", ".txt"]:
                raise SecurityError(
                    f"Disallowed file type: {mime_type}",
                    violation_type="disallowed_mime_type",
                    details={"mime_type": mime_type, "filename": filename},
                )

    # Detect format
    fmt = detect_format(data, filename)

    # Create import spec with defaults
    spec = ImportSpec()

    return fmt, spec


def parse_csv_preview(
    data: bytes,
    spec: ImportSpec,
    preview_rows: int = 100,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Parse CSV and return preview + parse metadata."""
    try:
        # Use BytesIO for parsing
        bio = io.BytesIO(data)

        # Extract only valid scan_csv arguments from ImportSpec
        csv_args = {
            "separator": spec.delimiter,
            "encoding": spec.encoding,
            "decimal_comma": spec.decimal_comma,
            "null_values": spec.null_tokens,
            "infer_schema_length": spec.infer_schema_length,
            "try_parse_dates": False,
        }

        # Parse with Polars
        lf = pl.scan_csv(bio, **csv_args)

        # Collect preview
        preview = lf.limit(preview_rows).collect()

        # Get full schema
        schema = lf.collect_schema()

        # Get row count (approximate for large files)
        try:
            row_count = lf.select(pl.len()).collect().item()
        except Exception:
            row_count = len(preview)

        metadata = {
            "format": "csv",
            "encoding": spec.encoding,
            "delimiter": spec.delimiter,
            "decimal_comma": spec.decimal_comma,
            "columns": list(schema.keys()),
            "dtypes": {k: str(v) for k, v in schema.items()},
            "row_count": row_count,
            "preview_rows": len(preview),
            "null_tokens": spec.null_tokens,
        }

        return preview, metadata

    except Exception as e:
        raise ParsingError(f"CSV parsing failed: {e}", format="csv") from e


def parse_parquet_preview(
    data: bytes,
    preview_rows: int = 100,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Parse Parquet and return preview + metadata."""
    try:
        bio = io.BytesIO(data)
        lf = pl.scan_parquet(bio)

        preview = lf.limit(preview_rows).collect()
        schema = lf.collect_schema()

        try:
            row_count = lf.select(pl.len()).collect().item()
        except Exception:
            row_count = len(preview)

        metadata = {
            "format": "parquet",
            "columns": list(schema.keys()),
            "dtypes": {k: str(v) for k, v in schema.items()},
            "row_count": row_count,
            "preview_rows": len(preview),
        }

        return preview, metadata

    except Exception as e:
        raise ParsingError(f"Parquet parsing failed: {e}", format="parquet") from e


def ingest_file(
    workspace: Workspace,
    data: bytes,
    filename: str | None = None,
    import_spec: ImportSpec | None = None,
) -> tuple[DatasetRef, pl.DataFrame, dict[str, Any]]:
    """Complete ingestion: validate, store, parse preview."""
    # Validate
    fmt, default_spec = validate_upload(data, filename)
    spec = import_spec or default_spec

    # Store and get reference
    dataset_ref = workspace.store_source(data, fmt, spec)

    # Parse preview
    if fmt == "csv":
        preview, metadata = parse_csv_preview(data, spec, get_settings().preview_rows)
    else:
        preview, metadata = parse_parquet_preview(data, get_settings().preview_rows)

    # Update dataset ref with actual schema hash
    schema = preview.schema
    schema_hash = hashlib.sha256(
        str(sorted(schema.items())).encode()
    ).hexdigest()[:16]

    # Create updated ref
    updated_ref = DatasetRef(
        dataset_id=dataset_ref.dataset_id,
        workspace_id=dataset_ref.workspace_id,
        source_sha256=dataset_ref.source_sha256,
        format=dataset_ref.format,
        schema_hash=schema_hash,
        row_count=metadata["row_count"],
        column_count=len(schema),
        created_at=dataset_ref.created_at,
    )

    return updated_ref, preview, metadata


def infer_column_roles(df: pl.DataFrame) -> dict[str, dict[str, Any]]:
    """Infer semantic roles for columns."""
    from CleanSheet.contracts import PhysicalDtype, SemanticRole

    roles = {}

    for col in df.columns:
        s = df[col]
        dtype = s.dtype
        n_unique = s.n_unique()
        n_null = s.null_count()
        total = len(s)

        # Determine physical dtype
        if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64) or dtype in (pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
            phys = PhysicalDtype.INT64
        elif dtype in (pl.Float32, pl.Float64):
            phys = PhysicalDtype.FLOAT64
        elif dtype == pl.Boolean:
            phys = PhysicalDtype.BOOLEAN
        elif dtype == pl.Date:
            phys = PhysicalDtype.DATE
        elif dtype == pl.Datetime:
            phys = PhysicalDtype.DATETIME
        elif dtype == pl.Categorical:
            phys = PhysicalDtype.CATEGORICAL
        elif dtype == pl.String:
            phys = PhysicalDtype.STRING
        else:
            phys = PhysicalDtype.STRING

        # Infer semantic role
        col_lower = col.lower()

        # Check for identifiers
        id_keywords = ["id", "key", "uuid", "guid", "code", "number", "num"]
        if any(kw in col_lower for kw in id_keywords) and n_unique == total:
            semantic = SemanticRole.IDENTIFIER
        elif dtype == pl.Date or dtype == pl.Datetime:
            semantic = SemanticRole.DATE
        elif phys in (PhysicalDtype.INT64, PhysicalDtype.FLOAT64):
            # Check if it's actually categorical (low cardinality numeric)
            if n_unique <= 20 and n_unique / total < 0.05:
                semantic = SemanticRole.CATEGORICAL
            else:
                semantic = SemanticRole.CONTINUOUS
        elif phys == PhysicalDtype.BOOLEAN:
            semantic = SemanticRole.CATEGORICAL
        elif phys in (PhysicalDtype.CATEGORICAL, PhysicalDtype.STRING):
            # Check cardinality
            if n_unique / total > 0.5:
                semantic = SemanticRole.FREE_TEXT
            else:
                semantic = SemanticRole.CATEGORICAL
        else:
            semantic = SemanticRole.FREE_TEXT

        roles[col] = {
            "physical_dtype": phys,
            "semantic_role": semantic,
            "n_unique": n_unique,
            "n_null": n_null,
            "null_pct": (n_null / total * 100) if total > 0 else 0,
            "is_constant": n_unique <= 1,
        }

    return roles


def validate_data_quality(df: pl.DataFrame) -> dict[str, Any]:
    """Run data quality checks."""
    issues = {
        "duplicates": [],
        "constant_columns": [],
        "high_cardinality": [],
        "missingness": [],
        "numeric_issues": [],
        "date_issues": [],
    }

    total_rows = len(df)

    for col in df.columns:
        s = df[col]
        n_null = s.null_count()
        n_unique = s.n_unique()

        # Missingness
        if n_null > 0:
            pct = n_null / total_rows * 100
            issues["missingness"].append({
                "column": col,
                "null_count": n_null,
                "null_pct": round(pct, 2),
                "severity": "high" if pct > 50 else "medium" if pct > 10 else "low",
            })

        # Constant columns
        if n_unique <= 1:
            issues["constant_columns"].append(col)

        # High cardinality
        if n_unique == total_rows and total_rows > 100:
            issues["high_cardinality"].append({
                "column": col,
                "unique_count": n_unique,
                "note": "Possible identifier column",
            })

        # Numeric issues
        if s.dtype.is_numeric():
            # Check for NaN
            if s.dtype.is_float():
                nan_count = s.filter(pl.col(col).is_nan()).height
                if nan_count > 0:
                    issues["numeric_issues"].append({
                        "column": col,
                        "issue": "NaN values",
                        "count": nan_count,
                    })

                # Check for infinity
                inf_count = s.filter(pl.col(col).is_infinite()).height
                if inf_count > 0:
                    issues["numeric_issues"].append({
                        "column": col,
                        "issue": "Infinite values",
                        "count": inf_count,
                    })

        # Date issues
        if s.dtype in (pl.Date, pl.Datetime):
            # Check for future dates, out of range, etc.
            pass

    # Check full-row duplicates
    dup_count = df.height - df.unique().height
    if dup_count > 0:
        issues["duplicates"].append({
            "type": "full_row",
            "count": dup_count,
        })

    return issues
