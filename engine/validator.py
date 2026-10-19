"""Main validation orchestrator — runs the full layered pipeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from engine.catalog_validator import validate_catalog
from engine.cross_field_validator import validate_cross_field
from engine.field_validator import validate_field
from engine.group_validator import validate_group
from engine.models import CrossFieldRule, FileSchema, ValidationError
from engine.parser import parse_excel
from engine.schema_loader import load_all_catalogs, load_cross_field_rules, load_file_schema

logger = logging.getLogger(__name__)


class FileValidator:
    """Orchestrates the full validation pipeline for a single file.

    Usage::

        validator = FileValidator(
            schema_path=Path("schemas/file_a.yaml"),
            catalog_dir=Path("catalogs"),
            rules_path=Path("rules/cross_field_rules_a.yaml"),
        )
        errors = validator.validate(Path("data/report_a.xlsx"))
    """

    def __init__(
        self,
        schema_path: Path,
        catalog_dir: Path,
        rules_path: Path | None = None,
    ) -> None:
        self.schema: FileSchema = load_file_schema(schema_path)
        self.catalogs: dict[str, set[str]] = load_all_catalogs(catalog_dir)
        self.cross_field_rules: list[CrossFieldRule] = []
        if rules_path:
            self.cross_field_rules = load_cross_field_rules(rules_path)

    def validate(self, file_path: Path) -> list[ValidationError]:
        """Run the full validation pipeline on an Excel file.

        Args:
            file_path: Path to the Excel file to validate.

        Returns:
            A list of all ValidationError instances found.
        """
        all_errors: list[ValidationError] = []
        file_name = file_path.name
        sheet = self.schema.sheet_name

        # ── Layer 1: Structural / Parse ──
        logger.info("Layer 1: Parsing '%s'...", file_name)
        df, parse_errors = parse_excel(file_path, self.schema)
        all_errors.extend(parse_errors)

        # If there are structural errors that prevent further validation, stop
        if df.empty and parse_errors:
            return all_errors

        # Build a column mapping: field_name -> column header
        col_map: dict[str, str] = {}
        for field in self.schema.fields:
            if field.column in df.columns:
                col_map[field.name] = field.column

        groups = self.schema.get_all_groups()

        # ── Iterate over every data row ──
        for idx, pandas_row in df.iterrows():
            # Excel row = header_row + data offset + pandas index
            excel_row = self.schema.data_start_row + int(idx)

            # Build a dict of field_name -> value for this row
            row_data: dict[str, Any] = {}
            for field in self.schema.fields:
                col = col_map.get(field.name)
                val = pandas_row.get(col) if col is not None else None
                row_data[field.name] = val
                if field.column and field.column not in row_data:
                    row_data[field.column] = val

            # ── Layer 2: Field-level checks ──
            for field in self.schema.fields:
                value = row_data.get(field.name)
                field_errors = validate_field(
                    value, field,
                    file_name=file_name, sheet=sheet, row=excel_row,
                )
                all_errors.extend(field_errors)

                # ── Layer 3: Catalog check ──
                if field.catalog and field.catalog in self.catalogs:
                    cat_error = validate_catalog(
                        value, field, self.catalogs[field.catalog],
                        file_name=file_name, sheet=sheet, row=excel_row,
                    )
                    if cat_error:
                        all_errors.append(cat_error)
                elif field.catalog and field.catalog not in self.catalogs:
                    logger.warning(
                        "Catalog '%s' referenced by field '%s' not found.",
                        field.catalog, field.name,
                    )

            # ── Layer 4: Group checks ──
            for group_name, group_fields in groups.items():
                group_errors = validate_group(
                    row_data, group_name, group_fields,
                    file_name=file_name, sheet=sheet, row=excel_row,
                )
                all_errors.extend(group_errors)

            # ── Layer 5: Cross-field checks ──
            for rule in self.cross_field_rules:
                xf_error = validate_cross_field(
                    row_data, rule,
                    file_name=file_name, sheet=sheet, row=excel_row,
                )
                if xf_error:
                    all_errors.append(xf_error)

        logger.info(
            "Validation complete for '%s': %d error(s) found.",
            file_name, len(all_errors),
        )
        return all_errors
