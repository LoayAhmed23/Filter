"""Loads field schemas from JSON/YAML and catalog lookup tables from CSV."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from engine.models import CrossFieldRule, FieldSchema, FileSchema


def _load_data_file(path: Path) -> Any:
    """Load a JSON or YAML file, auto-detecting by extension."""
    with open(path, "r", encoding="utf-8") as fh:
        if path.suffix.lower() in (".yaml", ".yml"):
            import yaml
            return yaml.safe_load(fh)
        else:
            return json.load(fh)


def load_file_schema(path: Path) -> FileSchema:
    """Load a file schema from a JSON or YAML file.

    Args:
        path: Path to the schema file (.json or .yaml).

    Returns:
        A FileSchema instance with all field definitions.
    """
    raw: dict[str, Any] = _load_data_file(path)

    fields = []
    for f in raw.get("fields", []):
        fields.append(
            FieldSchema(
                name=f["name"],
                column=str(f["column"]),
                data_type=f.get("data_type", "string"),
                category=f.get("category", "optional"),
                length=f.get("length"),
                pattern=f.get("pattern"),
                catalog=f.get("catalog"),
                date_format=f.get("date_format"),
                description=f.get("description", ""),
            )
        )

    return FileSchema(
        name=raw["name"],
        description=raw.get("description", ""),
        sheet_name=raw.get("sheet_name", "Sheet1"),
        header_row=raw.get("header_row", 1),
        data_start_row=raw.get("data_start_row", 2),
        fields=fields,
    )


def load_catalog(path: Path) -> set[str]:
    """Load a catalog (allowed values) from a CSV file.

    The CSV must have at least one column. The first column is treated as the
    set of allowed values.  Header row is skipped.

    Args:
        path: Path to the CSV catalog file.

    Returns:
        A set of allowed string values.
    """
    values: set[str] = set()
    with open(path, "r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # skip header
        for row in reader:
            if row:
                values.add(row[0].strip())
    return values


def load_all_catalogs(catalog_dir: Path) -> dict[str, set[str]]:
    """Load all catalog CSV files from a directory.

    Args:
        catalog_dir: Directory containing catalog CSV files.

    Returns:
        A dict mapping catalog name (filename without extension) to the set of
        allowed values.
    """
    catalogs: dict[str, set[str]] = {}
    if not catalog_dir.exists():
        return catalogs
    for csv_file in catalog_dir.glob("*.csv"):
        catalogs[csv_file.stem] = load_catalog(csv_file)
    return catalogs


def load_cross_field_rules(path: Path) -> list[CrossFieldRule]:
    """Load cross-field validation rules from a JSON or YAML file.

    Args:
        path: Path to the rules file (.json or .yaml).

    Returns:
        A list of CrossFieldRule instances.
    """
    if not path.exists():
        return []
    raw = _load_data_file(path)
    if not raw:
        return []
    rules: list[CrossFieldRule] = []
    for r in raw:
        rules.append(
            CrossFieldRule(
                rule_id=r["rule_id"],
                description=r.get("description", ""),
                condition=r.get("condition"),
                assertion=r["assertion"],
                severity=r.get("severity", "ERROR"),
            )
        )
    return rules
