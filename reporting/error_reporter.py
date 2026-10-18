"""Error reporting — output validation results to various formats."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from engine.models import Severity, ValidationError


def errors_to_dataframe(errors: list[ValidationError]) -> pd.DataFrame:
    """Convert a list of errors to a pandas DataFrame."""
    if not errors:
        return pd.DataFrame(
            columns=["file", "sheet", "row", "field", "rule_id",
                     "severity", "message", "actual_value", "expected"]
        )
    return pd.DataFrame([e.to_dict() for e in errors])


def print_summary(errors: list[ValidationError]) -> None:
    """Print a human-readable summary to stdout."""
    if not errors:
        print("\n✅  No validation errors found.")
        return

    severity_counts = {}
    for e in errors:
        severity_counts[e.severity.value] = severity_counts.get(e.severity.value, 0) + 1

    print(f"\n{'='*60}")
    print(f"  VALIDATION REPORT — {len(errors)} issue(s) found")
    print(f"{'='*60}")
    for sev, count in sorted(severity_counts.items()):
        print(f"  {sev}: {count}")
    print(f"{'='*60}\n")

    for e in errors:
        icon = "❌" if e.severity == Severity.ERROR else "⚠️" if e.severity == Severity.WARNING else "ℹ️"
        print(f"  {icon}  Row {e.row} | {e.field_name} | [{e.rule_id}]")
        print(f"      {e.message}")
        if e.actual_value is not None:
            print(f"      Got: {e.actual_value}")
        if e.expected:
            print(f"      Expected: {e.expected}")
        print()


def save_to_excel(errors: list[ValidationError], output_path: Path) -> None:
    """Save validation errors to an Excel file.

    Args:
        errors: List of validation errors.
        output_path: Path for the output Excel file.
    """
    df = errors_to_dataframe(errors)
    df.to_excel(output_path, index=False, sheet_name="Validation Errors")
    print(f"\n📄  Error report saved to: {output_path}")


def save_to_json(errors: list[ValidationError], output_path: Path) -> None:
    """Save validation errors to a JSON file.

    Args:
        errors: List of validation errors.
        output_path: Path for the output JSON file.
    """
    data = [e.to_dict() for e in errors]
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"\n📄  Error report saved to: {output_path}")
