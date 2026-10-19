"""Cross-field (inter-field) correlation validation.

Evaluates Python expressions defined in the rules YAML against each row.
"""
from __future__ import annotations

import operator
from datetime import datetime
from typing import Any

import pandas as pd

from engine.models import CrossFieldRule, Severity, ValidationError

# Safe builtins exposed to rule expressions
_SAFE_BUILTINS = {
    "len": len,
    "int": int,
    "float": float,
    "str": str,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "datetime": datetime,
    "True": True,
    "False": False,
    "None": None,
}


def _make_eval_context(row_data: dict[str, Any]) -> dict[str, Any]:
    """Build a safe evaluation namespace from row data."""
    import re

    ctx = dict(_SAFE_BUILTINS)
    # Expose each field as a variable (replace spaces/dashes/slashes with underscores)
    for key, val in row_data.items():
        safe_key = key.replace(" ", "_").replace("-", "_").replace("/", "_")
        # Convert NaN or empty string to None for cleaner expressions
        if (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and val.strip() == ""):
            val = None
        ctx[safe_key] = val
        # Strip leading numbers/dots e.g. "17._Liability_Indicator" -> "Liability_Indicator"
        clean_key = re.sub(r"^\d+[\._\s]*", "", safe_key)
        if clean_key:
            ctx[clean_key] = val
    return ctx


def validate_cross_field(
    row_data: dict[str, Any],
    rule: CrossFieldRule,
    *,
    file_name: str,
    sheet: str,
    row: int,
) -> ValidationError | None:
    """Evaluate a single cross-field rule against one row of data.

    Args:
        row_data: Dict mapping field name -> cell value for this row.
        rule: The cross-field rule to evaluate.
        file_name: Source file name (for error reporting).
        sheet: Sheet name (for error reporting).
        row: 1-indexed row number (for error reporting).

    Returns:
        A ValidationError if the assertion fails, else None.
    """
    ctx = _make_eval_context(row_data)

    try:
        # Check condition first (if provided)
        if rule.condition:
            condition_met = eval(rule.condition, {"__builtins__": {}}, ctx)
            if not condition_met:
                return None  # condition not met, skip assertion

        # Evaluate assertion
        result = eval(rule.assertion, {"__builtins__": {}}, ctx)
        if result:
            return None  # assertion passed

    except Exception as exc:
        return ValidationError(
            file_name=file_name,
            sheet=sheet,
            row=row,
            field_name="(cross-field)",
            rule_id=rule.rule_id,
            severity=Severity.WARNING,
            message=(
                f"Rule '{rule.rule_id}' could not be evaluated: {exc}. "
                f"Condition: {rule.condition!r}, Assertion: {rule.assertion!r}"
            ),
        )

    # Assertion failed
    return ValidationError(
        file_name=file_name,
        sheet=sheet,
        row=row,
        field_name="(cross-field)",
        rule_id=rule.rule_id,
        severity=Severity(rule.severity),
        message=(
            f"Cross-field rule '{rule.rule_id}' failed: {rule.description}. "
            f"Assertion: {rule.assertion}"
        ),
        expected=rule.assertion,
    )
