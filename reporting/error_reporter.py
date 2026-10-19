"""Error reporting — output validation results to various formats."""
from __future__ import annotations

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


def print_summary(errors: list[ValidationError], *, max_detail: int = 200) -> None:
    """Print a human-readable summary to stdout.

    Args:
        errors: List of validation errors.
        max_detail: Maximum number of individual errors to print in detail.
            For large files this prevents flooding the console.
    """
    if not errors:
        print("\n✅  No validation errors found.")
        return

    severity_counts: dict[str, int] = {}
    rule_counts: dict[str, int] = {}
    for e in errors:
        severity_counts[e.severity.value] = severity_counts.get(e.severity.value, 0) + 1
        rule_counts[e.rule_id] = rule_counts.get(e.rule_id, 0) + 1

    print(f"\n{'='*60}")
    print(f"  VALIDATION REPORT — {len(errors)} issue(s) found")
    print(f"{'='*60}")
    for sev, count in sorted(severity_counts.items()):
        print(f"  {sev}: {count}")
    print(f"{'='*60}")

    # Show breakdown by rule
    print(f"\n  {'Rule ID':<30} {'Count':>8}")
    print(f"  {'-'*30} {'-'*8}")
    for rule_id, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        print(f"  {rule_id:<30} {count:>8}")
    print()

    # Show individual errors (capped for large files)
    shown = min(len(errors), max_detail)
    if shown < len(errors):
        print(f"  Showing first {shown} of {len(errors)} errors:\n")

    for e in errors[:shown]:
        icon = "❌" if e.severity == Severity.ERROR else "⚠️" if e.severity == Severity.WARNING else "ℹ️"
        print(f"  {icon}  Row {e.row} | {e.field_name} | [{e.rule_id}]")
        print(f"      {e.message}")
        if e.actual_value is not None:
            print(f"      Got: {e.actual_value}")
        if e.expected:
            print(f"      Expected: {e.expected}")
        print()

    if shown < len(errors):
        print(f"  ... and {len(errors) - shown} more. Use -o to export all errors.\n")


def save_to_excel(errors: list[ValidationError], output_path: Path) -> None:
    """Save validation errors to an Excel file.

    Args:
        errors: List of validation errors.
        output_path: Path for the output Excel file.
    """
    df = errors_to_dataframe(errors)
    df.to_excel(output_path, index=False, sheet_name="Validation Errors")
    print(f"\n📄  Error report saved to: {output_path}")
