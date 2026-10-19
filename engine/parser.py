"""Excel file parser — reads Excel files into DataFrames with structural checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from engine.models import FileSchema, Severity, ValidationError


def parse_excel(
    file_path: Path,
    schema: FileSchema,
) -> tuple[pd.DataFrame, list[ValidationError]]:
    """Read an Excel file and run structural validation.

    Args:
        file_path: Path to the Excel (.xlsx) file.
        schema: The file schema specifying sheet, headers, etc.

    Returns:
        A tuple of (DataFrame, list of structural errors).
        The DataFrame may be empty if structural errors prevent reading.
    """
    errors: list[ValidationError] = []
    file_name = file_path.name

    # --- Check file exists ---
    if not file_path.exists():
        errors.append(
            ValidationError(
                file_name=file_name,
                sheet="",
                row=0,
                field_name="",
                rule_id="FILE_NOT_FOUND",
                severity=Severity.ERROR,
                message=f"File not found: {file_path}",
            )
        )
        return pd.DataFrame(), errors

    # --- Try reading the workbook ---
    try:
        # header_row is 1-indexed in schema, pandas uses 0-indexed
        df = pd.read_excel(
            file_path,
            sheet_name=schema.sheet_name,
            header=schema.header_row - 1,
            dtype=str,  # read everything as string to preserve raw data
        )
    except ValueError as exc:
        errors.append(
            ValidationError(
                file_name=file_name,
                sheet=schema.sheet_name,
                row=0,
                field_name="",
                rule_id="SHEET_NOT_FOUND",
                severity=Severity.ERROR,
                message=f"Sheet '{schema.sheet_name}' not found: {exc}",
            )
        )
        return pd.DataFrame(), errors
    except Exception as exc:
        errors.append(
            ValidationError(
                file_name=file_name,
                sheet=schema.sheet_name,
                row=0,
                field_name="",
                rule_id="READ_ERROR",
                severity=Severity.ERROR,
                message=f"Failed to read Excel file: {exc}",
            )
        )
        return pd.DataFrame(), errors

    # --- Validate expected columns exist ---
    actual_columns = set(df.columns.str.strip())
    for field in schema.fields:
        if field.column not in actual_columns:
            errors.append(
                ValidationError(
                    file_name=file_name,
                    sheet=schema.sheet_name,
                    row=schema.header_row,
                    field_name=field.name,
                    rule_id="MISSING_COLUMN",
                    severity=Severity.ERROR,
                    message=(
                        f"Expected column '{field.column}' for field "
                        f"'{field.name}' not found in sheet."
                    ),
                )
            )

    # --- Check file is not empty ---
    if df.empty:
        errors.append(
            ValidationError(
                file_name=file_name,
                sheet=schema.sheet_name,
                row=0,
                field_name="",
                rule_id="EMPTY_FILE",
                severity=Severity.WARNING,
                message="File contains no data rows.",
            )
        )

    return df, errors
