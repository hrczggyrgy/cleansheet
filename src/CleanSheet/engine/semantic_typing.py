"""Semantic variable type inference with confidence flags.

Deterministic classification of Polars columns into statistical measurement scales.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import polars as pl

from CleanSheet.contracts import ColumnRole, PhysicalDtype, SemanticRole

# Known ordinal lexicons
ORDINAL_LEXICONS: dict[str, list[str]] = {
    "likert_5": ["1", "2", "3", "4", "5"],
    "likert_5_labels": ["strongly disagree", "disagree", "neutral", "agree", "strongly agree"],
    "likert_7": ["1", "2", "3", "4", "5", "6", "7"],
    "agreement_4": ["strongly disagree", "disagree", "agree", "strongly agree"],
    "frequency_5": ["never", "rarely", "sometimes", "often", "always"],
    "frequency_4": ["never", "sometimes", "often", "always"],
    "satisfaction_5": ["very dissatisfied", "dissatisfied", "neutral", "satisfied", "very satisfied"],
    "quality_4": ["poor", "fair", "good", "excellent"],
    "quality_5": ["very poor", "poor", "fair", "good", "excellent"],
    "severity_3": ["low", "medium", "high"],
    "severity_4": ["mild", "moderate", "severe", "critical"],
    "priority_3": ["low", "medium", "high"],
    "priority_4": ["low", "medium", "high", "critical"],
    "education_6": ["less than high school", "high school", "some college", "bachelor", "master", "doctorate"],
    "income_5": ["very low", "low", "medium", "high", "very high"],
    "q1_q4": ["q1", "q2", "q3", "q4"],
    "tier_3": ["tier 1", "tier 2", "tier 3"],
    "tier_4": ["tier 1", "tier 2", "tier 3", "tier 4"],
    "stage_4": ["stage i", "stage ii", "stage iii", "stage iv"],
    "grade_4": ["grade 1", "grade 2", "grade 3", "grade 4"],
}

# Identifier patterns
ID_PATTERNS = [
    r"^id$",
    r"_id$",
    r"^uuid$",
    r"^guid$",
    r"^code$",
    r"_code$",
    r"^ssn$",
    r"^phone$",
    r"^email$",
    r"^ref$",
    r"_ref$",
    r"^key$",
    r"_key$",
    r"^number$",
    r"_number$",
    r"^num$",
    r"_num$",
]


@dataclass
class TypeInferenceResult:
    """Result of semantic type inference for a column."""

    semantic_role: SemanticRole
    confidence: Literal[high, medium, low]
    ambiguity_reason: str | None
    ordinal_order: list[str] | None
    is_excluded: bool


def _is_monotonic_integer(series: pl.Series) -> bool:
    """Check if integer series is monotonically increasing (likely an index/ID)."""
    if series.dtype not in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
        return False
    # Check if values are sequential or near-sequential
    vals = series.drop_nulls().sort()
    if len(vals) < 3:
        return False
    diffs = vals.diff().drop_nulls()
    # If all diffs are 1 (or mostly 1), it's likely an index
    return (diffs == 1).all() or (diffs == 1).mean() > 0.9


def _matches_id_pattern(col_name: str) -> bool:
    """Check if column name matches common identifier patterns."""
    col_lower = col_name.lower()
    for pattern in ID_PATTERNS:
        if re.search(pattern, col_lower):
            return True
    return False


def _matches_ordinal_lexicon(values: list[str]) -> tuple[bool, list[str] | None]:
    """Check if string values match a known ordinal lexicon."""
    # Normalize values
    normalized = [v.strip().lower() for v in values if v is not None]
    if not normalized:
        return False, None

    # Try exact match against known lexicons
    for lexicon_name, lexicon_values in ORDINAL_LEXICONS.items():
        lexicon_normalized = [v.lower() for v in lexicon_values]
        if set(normalized).issubset(set(lexicon_normalized)) and len(normalized) >= 2:
            # Return the canonical ordering from the lexicon
            matched_order = [v for v in lexicon_values if v.lower() in set(normalized)]
            if len(matched_order) >= 2:
                return True, matched_order

    return False, None


def _looks_like_likert_integers(values: list[int], min_val: int = 1, max_val: int = 7) -> bool:
    """Check if integer values look like a Likert scale."""
    if not values:
        return False
    unique_vals = set(values)
    # All values within expected range
    if min(unique_vals) < min_val or max(unique_vals) > max_val:
        return False
    # Consecutive integers
    expected = set(range(min_val, max_val + 1))
    if unique_vals.issubset(expected):
        return True
    return False


def _check_sequential_integers(series: pl.Series) -> bool:
    """Check if integer column has sequential values 1..k."""
    if series.dtype not in (pl.Int8, pl.Int16, pl.Int32, pl.Int64):
        return False
    vals = series.drop_nulls().unique().sort()
    if len(vals) < 3 or len(vals) > 10:
        return False
    # Check if it's 1, 2, 3... or 0, 1, 2...
    if list(vals) == list(range(1, len(vals) + 1)) or list(vals) == list(range(len(vals))):
        return True
    return False


def infer_semantic_role(series: pl.Series) -> TypeInferenceResult:
    """Infer the semantic role of a Polars column.

    Returns a TypeInferenceResult with the inferred role, confidence,
    ambiguity reason, and any ordinal ordering.
    """
    col_name = series.name
    dtype = series.dtype
    n_rows = len(series)
    n_null = series.null_count()
    n_unique = series.n_unique()
    null_pct = (n_null / n_rows * 100) if n_rows > 0 else 0

    # Constant or empty columns
    if n_unique <= 1:
        return TypeInferenceResult(
            semantic_role=SemanticRole.NOMINAL,
            confidence="high",
            ambiguity_reason="Constant or single-value column",
            ordinal_order=None,
            is_excluded=True,
        )

    # High missingness
    if null_pct > 50:
        return TypeInferenceResult(
            semantic_role=SemanticRole.FREE_TEXT,
            confidence="low",
            ambiguity_reason=f"High missingness ({null_pct:.1f}%)",
            ordinal_order=None,
            is_excluded=True,
        )

    # Temporal types
    if dtype == pl.Date:
        return TypeInferenceResult(
            semantic_role=SemanticRole.DATE,
            confidence="high",
            ambiguity_reason=None,
            ordinal_order=None,
            is_excluded=False,
        )

    if dtype == pl.Datetime:
        return TypeInferenceResult(
            semantic_role=SemanticRole.DATETIME,
            confidence="high",
            ambiguity_reason=None,
            ordinal_order=None,
            is_excluded=False,
        )

    # Boolean
    if dtype == pl.Boolean:
        return TypeInferenceResult(
            semantic_role=SemanticRole.BINARY,
            confidence="high",
            ambiguity_reason=None,
            ordinal_order=None,
            is_excluded=False,
        )

    # String / Categorical
    if dtype in (pl.String, pl.Categorical):
        # Get unique non-null values as strings
        unique_vals = series.drop_nulls().unique().to_list()
        unique_vals_str = [str(v) for v in unique_vals]

        # Check for identifier patterns
        if _matches_id_pattern(col_name):
            if n_unique == n_rows or n_unique / n_rows > 0.95:
                return TypeInferenceResult(
                    semantic_role=SemanticRole.IDENTIFIER,
                    confidence="high",
                    ambiguity_reason="Column name matches identifier pattern with high uniqueness",
                    ordinal_order=None,
                    is_excluded=True,
                )

        # Check for high cardinality free text
        if n_unique / n_rows > 0.5 and n_unique > 20:
            # Check median string length
            lengths = series.drop_nulls().str.len_chars()
            median_len = lengths.median() if len(lengths) > 0 else 0
            if median_len > 35:
                return TypeInferenceResult(
                    semantic_role=SemanticRole.FREE_TEXT,
                    confidence="medium",
                    ambiguity_reason="High cardinality with long text values",
                    ordinal_order=None,
                    is_excluded=True,
                )

        # Check for ordinal lexicons
        matched, order = _matches_ordinal_lexicon(unique_vals_str)
        if matched:
            return TypeInferenceResult(
                semantic_role=SemanticRole.ORDINAL,
                confidence="high",
                ambiguity_reason=f"Matched ordinal lexicon: {order}",
                ordinal_order=order,
                is_excluded=False,
            )

        # Check if binary
        if n_unique == 2:
            return TypeInferenceResult(
                semantic_role=SemanticRole.BINARY,
                confidence="high",
                ambiguity_reason=None,
                ordinal_order=None,
                is_excluded=False,
            )

        # Check if it could be ordinal (low cardinality, not free text)
        if n_unique <= 12 and n_unique / n_rows < 0.1:
            # Ambiguous: could be nominal or ordinal
            return TypeInferenceResult(
                semantic_role=SemanticRole.NOMINAL,
                confidence="medium",
                ambiguity_reason=f"Low cardinality ({n_unique} categories) — could be nominal or ordinal",
                ordinal_order=None,
                is_excluded=False,
            )

        # Default to nominal for low-medium cardinality
        if n_unique <= 50:
            return TypeInferenceResult(
                semantic_role=SemanticRole.NOMINAL,
                confidence="high",
                ambiguity_reason=None,
                ordinal_order=None,
                is_excluded=False,
            )

        # High cardinality string
        return TypeInferenceResult(
            semantic_role=SemanticRole.FREE_TEXT,
            confidence="medium",
            ambiguity_reason=f"High cardinality ({n_unique} unique values)",
            ordinal_order=None,
            is_excluded=True,
        )

    # Numeric types
    if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
        unique_vals = series.drop_nulls().unique().to_list()

        # Check for identifier patterns
        if _matches_id_pattern(col_name):
            if n_unique == n_rows or _is_monotonic_integer(series):
                return TypeInferenceResult(
                    semantic_role=SemanticRole.IDENTIFIER,
                    confidence="high",
                    ambiguity_reason="Column name matches identifier pattern with high uniqueness or monotonic sequence",
                    ordinal_order=None,
                    is_excluded=True,
                )

        # Check for sequential integers (likely ordinal/categorical codes)
        if _check_sequential_integers(series):
            # Could be Likert or categorical codes
            if n_unique <= 7:
                return TypeInferenceResult(
                    semantic_role=SemanticRole.ORDINAL,
                    confidence="medium",
                    ambiguity_reason=f"Sequential integers 1..{n_unique} — could be ordinal scale or categorical codes",
                    ordinal_order=[str(v) for v in sorted(unique_vals)],
                    is_excluded=False,
                )

        # Check for Likert-like integers
        if _looks_like_likert_integers(unique_vals):
            return TypeInferenceResult(
                semantic_role=SemanticRole.ORDINAL,
                confidence="medium",
                ambiguity_reason="Integers in Likert-like range — likely ordinal scale",
                ordinal_order=[str(v) for v in sorted(unique_vals)],
                is_excluded=False,
            )

        # Low cardinality integers -> discrete count or categorical
        if n_unique <= 20 and n_unique / n_rows < 0.05:
            # Check if non-negative (counts)
            min_val = series.min()
            if min_val is not None and min_val >= 0:
                return TypeInferenceResult(
                    semantic_role=SemanticRole.DISCRETE,
                    confidence="medium",
                    ambiguity_reason="Low cardinality non-negative integers — could be counts or categories",
                    ordinal_order=None,
                    is_excluded=False,
                )
            return TypeInferenceResult(
                semantic_role=SemanticRole.NOMINAL,
                confidence="medium",
                ambiguity_reason="Low cardinality integers with negatives — likely categorical codes",
                ordinal_order=None,
                is_excluded=False,
            )

        # Default: continuous
        return TypeInferenceResult(
            semantic_role=SemanticRole.CONTINUOUS,
            confidence="high",
            ambiguity_reason=None,
            ordinal_order=None,
            is_excluded=False,
        )

    # Float types
    if dtype in (pl.Float32, pl.Float64):
        return TypeInferenceResult(
            semantic_role=SemanticRole.CONTINUOUS,
            confidence="high",
            ambiguity_reason=None,
            ordinal_order=None,
            is_excluded=False,
        )

    # Fallback
    return TypeInferenceResult(
        semantic_role=SemanticRole.FREE_TEXT,
        confidence="low",
        ambiguity_reason=f"Unhandled dtype: {dtype}",
        ordinal_order=None,
        is_excluded=True,
    )


def infer_column_roles(df: pl.DataFrame) -> dict[str, dict[str, Any]]:
    """Infer semantic roles for all columns in a DataFrame.

    Returns dict compatible with existing API.
    """
    roles = {}

    for col in df.columns:
        s = df[col]
        result = infer_semantic_role(s)

        # Map to physical dtype
        dtype = s.dtype
        if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
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

        roles[col] = {
            "physical_dtype": phys,
            "semantic_role": result.semantic_role,
            "ordinal_order": result.ordinal_order,
            "confidence": result.confidence,
            "ambiguity_reason": result.ambiguity_reason,
            "is_excluded": result.is_excluded,
            "n_unique": s.n_unique(),
            "n_null": s.null_count(),
            "null_pct": (s.null_count() / len(s) * 100) if len(s) > 0 else 0,
            "is_constant": s.n_unique() <= 1,
        }

    return roles


def get_ambiguous_columns(roles: dict[str, dict[str, Any]]) -> list[str]:
    """Get list of columns that need user confirmation."""
    ambiguous = []
    for col, info in roles.items():
        if info.get("confidence") in ("medium", "low") and not info.get("is_excluded", False):
            ambiguous.append(col)
    return ambiguous


def confirm_column_role(
    current_role: SemanticRole,
    new_role: SemanticRole,
    ordinal_order: list[str] | None = None,
) -> ColumnRole:
    """Create a confirmed ColumnRole from user input."""
    return ColumnRole(
        column="",  # Set by caller
        physical_dtype=PhysicalDtype.STRING,  # Set by caller
        semantic_role=new_role,
        ordinal_order=ordinal_order,
        confirmed=True,
        suggested_by="user",
        confidence="high",
        ambiguity_reason=None,
        is_excluded=new_role in (SemanticRole.IDENTIFIER, SemanticRole.FREE_TEXT),
    )
