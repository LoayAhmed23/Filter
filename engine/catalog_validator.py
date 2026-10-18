"""Catalog / lookup-table validation."""
from __future__ import annotations

from typing import Any

import pandas as pd

from engine.models import FieldSchema, Severity, ValidationError


def validate_catalog(
    value: Any,
    field: FieldSchema,
    catalog_values: set[str],
    *,
    file_name: str,
    sheet: str,
    row: int,
) -> ValidationError | None:
    """Check that a non-empty value exists in the catalog.

    Args:
        value: The cell value.
        field: Field schema (must have a catalog defined).
        catalog_values: The set of allowed values for this catalog.
        file_name: Source file name (for error reporting).
        sheet: Sheet name (for error reporting).
        row: 1-indexed row number (for error reporting).

    Returns:
        A ValidationError if the value is not in the catalog, else None.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None  # empty values handled by field_validator

    str_value = str(value).strip()
    if str_value == "":
        return None

    if str_value not in catalog_values:
        # Build a preview of allowed values for the error message
        preview = sorted(catalog_values)[:10]
        suffix = "..." if len(catalog_values) > 10 else ""
        return ValidationError(
            file_name=file_name,
            sheet=sheet,
            row=row,
            field_name=field.name,
            rule_id=f"CATALOG_{field.catalog}",
            severity=Severity.ERROR,
            message=(
                f"Field '{field.name}' value '{str_value}' is not in "
                f"catalog '{field.catalog}'."
            ),
            actual_value=str_value,
            expected=f"one of {preview}{suffix}",
        )
    return None
