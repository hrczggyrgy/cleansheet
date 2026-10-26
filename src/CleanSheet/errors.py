"""Custom exceptions for CleanSheet."""

from __future__ import annotations

from typing import Any


class CleanSheetError(Exception):
    """Base exception for CleanSheet errors."""

    def __init__(
        self,
        message: str,
        code: str = "CLEANSHEET_ERROR",
        details: dict[str, Any] | None = None,
        user_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.user_message = user_message or message


class ValidationError(CleanSheetError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="VALIDATION_ERROR",
            details={**(details or {}), "field": field, "value": str(value) if value is not None else None},
            user_message=f"Invalid input: {message}",
        )
        self.field = field
        self.value = value


class ParsingError(CleanSheetError):
    """Raised when file parsing fails."""

    def __init__(
        self,
        message: str,
        format: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="PARSING_ERROR",
            details={**(details or {}), "format": format},
            user_message="Could not parse the file. Please check the format and try again.",
        )
        self.format = format


class SchemaError(CleanSheetError):
    """Raised when schema validation fails."""

    def __init__(
        self,
        message: str,
        expected: dict[str, Any] | None = None,
        actual: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="SCHEMA_ERROR",
            details={**(details or {}), "expected": expected, "actual": actual},
            user_message="The data structure doesn't match expectations. Please review the data.",
        )
        self.expected = expected
        self.actual = actual


class EligibilityError(CleanSheetError):
    """Raised when an analysis is not eligible for the given data/design."""

    def __init__(
        self,
        message: str,
        rule_id: str | None = None,
        reasons: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="ELIGIBILITY_ERROR",
            details={**(details or {}), "rule_id": rule_id, "reasons": reasons or []},
            user_message=message,
        )
        self.rule_id = rule_id
        self.reasons = reasons or []


class ResourceLimitError(CleanSheetError):
    """Raised when a resource limit is exceeded."""

    def __init__(
        self,
        message: str,
        limit_type: str,
        limit_value: Any,
        actual_value: Any,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="RESOURCE_LIMIT_ERROR",
            details={**(details or {}), "limit_type": limit_type, "limit_value": limit_value, "actual_value": actual_value},
            user_message=f"Resource limit exceeded: {limit_type} (limit: {limit_value}, actual: {actual_value})",
        )
        self.limit_type = limit_type
        self.limit_value = limit_value
        self.actual_value = actual_value


class JobError(CleanSheetError):
    """Raised when a background job fails."""

    def __init__(
        self,
        message: str,
        job_id: str | None = None,
        stage: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="JOB_ERROR",
            details={**(details or {}), "job_id": job_id, "stage": stage},
            user_message="The analysis job failed. Please check the data and try again.",
        )
        self.job_id = job_id
        self.stage = stage


class CancellationError(CleanSheetError):
    """Raised when a job is cancelled."""

    def __init__(self, message: str = "Job cancelled", job_id: str | None = None) -> None:
        super().__init__(
            message,
            code="CANCELLATION_ERROR",
            details={"job_id": job_id},
            user_message="The operation was cancelled.",
        )
        self.job_id = job_id


class TimeoutError(CleanSheetError):
    """Raised when a job times out."""

    def __init__(
        self,
        message: str = "Job timed out",
        job_id: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        super().__init__(
            message,
            code="TIMEOUT_ERROR",
            details={"job_id": job_id, "timeout_seconds": timeout_seconds},
            user_message=f"The operation took too long and was stopped (limit: {timeout_seconds}s).",
        )
        self.job_id = job_id
        self.timeout_seconds = timeout_seconds


class WorkspaceError(CleanSheetError):
    """Raised when workspace operations fail."""

    def __init__(
        self,
        message: str,
        workspace_id: str | None = None,
        operation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="WORKSPACE_ERROR",
            details={**(details or {}), "workspace_id": workspace_id, "operation": operation},
            user_message="A workspace error occurred. Please try again or start a new session.",
        )
        self.workspace_id = workspace_id
        self.operation = operation


class ExportError(CleanSheetError):
    """Raised when export fails."""

    def __init__(
        self,
        message: str,
        format: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="EXPORT_ERROR",
            details={**(details or {}), "format": format},
            user_message="Could not generate the export. Please try again.",
        )
        self.format = format


class SecurityError(CleanSheetError):
    """Raised when a security violation is detected."""

    def __init__(
        self,
        message: str,
        violation_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="SECURITY_ERROR",
            details={**(details or {}), "violation_type": violation_type},
            user_message="A security policy was violated. The operation was blocked.",
        )
        self.violation_type = violation_type


class NotSupportedError(CleanSheetError):
    """Raised when a feature is not supported."""

    def __init__(
        self,
        message: str,
        feature: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="NOT_SUPPORTED_ERROR",
            details={**(details or {}), "feature": feature},
            user_message=f"This feature is not supported: {feature}",
        )
        self.feature = feature
