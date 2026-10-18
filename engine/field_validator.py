"""Field-level validations: type, length, format, required, pattern."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd

from engine.models import FieldSchema, Severity, ValidationError


def _is_empty(value: Any) -> bool:
    """Check whether a cell value is considered empty."""
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def validate_field(
    value: Any,
    field: FieldSchema,
    *,
    file_name: str,
    sheet: str,
    row: int,
) -> list[ValidationError]:
    """Run all field-level checks on a single cell value.

    Args:
        value: The cell value read from Excel.
        field: The field schema to validate against.
        file_name: Source file name (for error reporting).
        sheet: Sheet name (for error reporting).
        row: 1-indexed row number (for error reporting).

    Returns:
        A list of ValidationError instances (empty if valid).
    """
    errors: list[ValidationError] = []

    # --- Required check ---
    if _is_empty(value):
        if field.is_required:
            errors.append(
                ValidationError(
                    file_name=file_name,
                    sheet=sheet,
                    row=row,
                    field_name=field.name,
                    rule_id="REQUIRED",
                    severity=Severity.ERROR,
                    message=f"Required field '{field.name}' is empty.",
                    actual_value=value,
                    expected="non-empty",
                )
            )
        # No further checks needed for empty optional/group fields
        return errors

    str_value = str(value).strip()

    # --- Data type check ---
    type_error = _check_type(value, field, file_name, sheet, row)
    if type_error:
        errors.append(type_error)
        return errors  # skip further checks if type is wrong

    # --- Length checks ---
    if field.max_length is not None and len(str_value) > field.max_length:
        errors.append(
            ValidationError(
                file_name=file_name,
                sheet=sheet,
                row=row,
                field_name=field.name,
                rule_id="MAX_LENGTH",
                severity=Severity.ERROR,
                message=(
                    f"Field '{field.name}' exceeds max length "
                    f"{field.max_length} (actual: {len(str_value)})."
                ),
                actual_value=str_value,
                expected=f"<= {field.max_length} characters",
            )
        )

    if field.min_length is not None and len(str_value) < field.min_length:
        errors.append(
            ValidationError(
                file_name=file_name,
                sheet=sheet,
                row=row,
                field_name=field.name,
                rule_id="MIN_LENGTH",
                severity=Severity.ERROR,
                message=(
                    f"Field '{field.name}' is shorter than min length "
                    f"{field.min_length} (actual: {len(str_value)})."
                ),
                actual_value=str_value,
                expected=f">= {field.min_length} characters",
            )
        )

    # --- Regex pattern check ---
    if field.pattern is not None:
        if not re.fullmatch(field.pattern, str_value):
            errors.append(
                ValidationError(
                    file_name=file_name,
                    sheet=sheet,
                    row=row,
                    field_name=field.name,
                    rule_id="PATTERN",
                    severity=Severity.ERROR,
                    message=(
                        f"Field '{field.name}' does not match "
                        f"pattern '{field.pattern}'."
                    ),
                    actual_value=str_value,
                    expected=f"matches /{field.pattern}/",
                )
            )

    # --- Numeric range checks ---
    if field.data_type in ("integer", "float"):
        try:
            num = float(str_value)
        except (ValueError, TypeError):
            num = None
        if num is not None:
            if field.min_value is not None and num < field.min_value:
                errors.append(
                    ValidationError(
                        file_name=file_name,
                        sheet=sheet,
                        row=row,
                        field_name=field.name,
                        rule_id="MIN_VALUE",
                        severity=Severity.ERROR,
                        message=(
                            f"Field '{field.name}' value {num} is below "
                            f"minimum {field.min_value}."
                        ),
                        actual_value=num,
                        expected=f">= {field.min_value}",
                    )
                )
            if field.max_value is not None and num > field.max_value:
                errors.append(
                    ValidationError(
                        file_name=file_name,
                        sheet=sheet,
                        row=row,
                        field_name=field.name,
                        rule_id="MAX_VALUE",
                        severity=Severity.ERROR,
                        message=(
                            f"Field '{field.name}' value {num} exceeds "
                            f"maximum {field.max_value}."
                        ),
                        actual_value=num,
                        expected=f"<= {field.max_value}",
                    )
                )

    return errors


def _check_type(
    value: Any,
    field: FieldSchema,
    file_name: str,
    sheet: str,
    row: int,
) -> ValidationError | None:
    """Validate the data type of a non-empty value."""
    dt = field.data_type

    if dt == "integer":
        try:
            if isinstance(value, float) and not value.is_integer():
                raise ValueError
            int(value)
        except (ValueError, TypeError):
            return ValidationError(
                file_name=file_name,
                sheet=sheet,
                row=row,
                field_name=field.name,
                rule_id="TYPE_INTEGER",
                severity=Severity.ERROR,
                message=f"Field '{field.name}' expected integer, got '{value}'.",
                actual_value=value,
                expected="integer",
            )

    elif dt == "float":
        try:
            float(value)
        except (ValueError, TypeError):
            return ValidationError(
                file_name=file_name,
                sheet=sheet,
                row=row,
                field_name=field.name,
                rule_id="TYPE_FLOAT",
                severity=Severity.ERROR,
                message=f"Field '{field.name}' expected number, got '{value}'.",
                actual_value=value,
                expected="float",
            )

    elif dt == "date":
        fmt = field.date_format or "%Y-%m-%d"
        str_val = str(value).strip()
        # If pandas already parsed it as Timestamp, accept it
        if not isinstance(value, (datetime, pd.Timestamp)):
            try:
                datetime.strptime(str_val, fmt)
            except ValueError:
                return ValidationError(
                    file_name=file_name,
                    sheet=sheet,
                    row=row,
                    field_name=field.name,
                    rule_id="TYPE_DATE",
                    severity=Severity.ERROR,
                    message=(
                        f"Field '{field.name}' expected date format "
                        f"'{fmt}', got '{str_val}'."
                    ),
                    actual_value=str_val,
                    expected=f"date in format {fmt}",
                )

    elif dt == "boolean":
        if str(value).strip().lower() not in (
            "true", "false", "1", "0", "yes", "no",
        ):
            return ValidationError(
                file_name=file_name,
                sheet=sheet,
                row=row,
                field_name=field.name,
                rule_id="TYPE_BOOLEAN",
                severity=Severity.ERROR,
                message=f"Field '{field.name}' expected boolean, got '{value}'.",
                actual_value=value,
                expected="true/false/1/0/yes/no",
            )

    # 'string' type always passes
    return None
