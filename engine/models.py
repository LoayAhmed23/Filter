"""Data models for the file verification engine."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Severity(enum.Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class FieldCategory(enum.Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    GROUP = "group"  # value will be like 'group:agent_info'


@dataclass
class FieldSchema:
    """Schema definition for a single field / column."""
    name: str
    column: str              # Excel column letter or header name
    data_type: str           # string, integer, float, date, boolean
    category: str            # 'required', 'optional', or 'group:<group_name>'
    length: int | None = None
    pattern: str | None = None        # regex pattern
    catalog: str | None = None        # name of catalog file (without extension)
    date_format: str | None = None    # e.g. '%Y-%m-%d'
    min_value: float | None = None    # minimum numeric value
    max_value: float | None = None    # maximum numeric value
    description: str = ""

    # Cached computed properties (set in __post_init__)
    _group_name: str | None = field(default=None, init=False, repr=False)
    _is_required: bool = field(default=False, init=False, repr=False)
    _is_group: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._is_required = self.category == "required"
        self._is_group = self.category.startswith("group:")
        if self._is_group:
            self._group_name = self.category.split(":", 1)[1]
        else:
            self._group_name = None

    @property
    def is_required(self) -> bool:
        return self._is_required

    @property
    def is_group(self) -> bool:
        return self._is_group

    @property
    def group_name(self) -> str | None:
        return self._group_name


@dataclass
class FileSchema:
    """Schema definition for an entire file."""
    name: str
    description: str
    sheet_name: str             # Excel sheet name (or index)
    header_row: int             # 1-indexed row number where headers are
    data_start_row: int         # 1-indexed row number where data starts
    fields: list[FieldSchema] = field(default_factory=list)

    # Cached lookup (built lazily)
    _groups: dict[str, list[FieldSchema]] | None = field(default=None, init=False, repr=False)

    def get_all_groups(self) -> dict[str, list[FieldSchema]]:
        if self._groups is None:
            groups: dict[str, list[FieldSchema]] = {}
            for f in self.fields:
                gn = f.group_name
                if gn:
                    groups.setdefault(gn, []).append(f)
            self._groups = groups
        return self._groups


@dataclass
class CrossFieldRule:
    """A rule that validates relationships between fields."""
    rule_id: str
    description: str
    condition: str | None = None  # Python expression; if None, assertion always checked
    assertion: str = ""           # Python expression that must be True
    severity: str = "ERROR"


@dataclass(slots=True)
class ValidationError:
    """A single validation error."""
    file_name: str
    sheet: str
    row: int                  # 1-indexed Excel row
    field_name: str
    rule_id: str
    severity: Severity
    message: str
    actual_value: Any = None
    expected: str = ""

    def to_dict(self) -> dict:
        return {
            "file": self.file_name,
            "sheet": self.sheet,
            "row": self.row,
            "field": self.field_name,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "actual_value": str(self.actual_value) if self.actual_value is not None else "",
            "expected": self.expected,
        }
