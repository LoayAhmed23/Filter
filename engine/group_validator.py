"""Group / conditional-mandatory validation.

If ANY field in a group is populated, then ALL fields in that group
become mandatory.
"""
from __future__ import annotations

from typing import Any

from engine.models import FieldSchema, Severity, ValidationError


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def validate_group(
    row_data: dict[str, Any],
    group_name: str,
    group_fields: list[FieldSchema],
    *,
    file_name: str,
    sheet: str,
    row: int,
) -> list[ValidationError]:
    """Validate the conditional-mandatory group constraint.

    If at least one field in the group has a non-empty value, every other
    field in the group must also be non-empty.

    Args:
        row_data: Dict mapping field name -> cell value for this row.
        group_name: The name of the group being validated.
        group_fields: All FieldSchema instances belonging to this group.
        file_name: Source file name (for error reporting).
        sheet: Sheet name (for error reporting).
        row: 1-indexed row number (for error reporting).

    Returns:
        A list of ValidationError instances.
    """
    filled = []
    empty = []

    for f in group_fields:
        val = row_data.get(f.name)
        if _is_empty(val):
            empty.append(f)
        else:
            filled.append(f)

    # If no fields are filled, the whole group is unused — that's fine
    if not filled:
        return []

    # If all fields are filled, the group is complete — that's fine
    if not empty:
        return []

    # Partial fill — report an error for each missing field
    filled_names = ", ".join(f"'{f.name}'" for f in filled)
    errors: list[ValidationError] = []
    for missing in empty:
        errors.append(
            ValidationError(
                file_name=file_name,
                sheet=sheet,
                row=row,
                field_name=missing.name,
                rule_id=f"GROUP_{group_name}",
                severity=Severity.ERROR,
                message=(
                    f"Field '{missing.name}' is required because "
                    f"{filled_names} in group '{group_name}' "
                    f"{'is' if len(filled) == 1 else 'are'} populated."
                ),
                actual_value=None,
                expected="non-empty (group constraint)",
            )
        )
    return errors
