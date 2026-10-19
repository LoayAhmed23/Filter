"""Main validation orchestrator — runs the full layered pipeline.

Optimized for large files (100K+ rows) using vectorized pandas operations
instead of row-by-row Python iteration.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.models import (
    CrossFieldRule,
    FieldSchema,
    FileSchema,
    Severity,
    ValidationError,
)
from engine.parser import parse_excel
from engine.schema_loader import load_all_catalogs, load_cross_field_rules, load_file_schema

logger = logging.getLogger(__name__)

# Safe builtins exposed to cross-field rule expressions
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


class FileValidator:
    """Orchestrates the full validation pipeline for a single file.

    Usage::

        validator = FileValidator(
            schema_path=Path("schemas/file_a.json"),
            catalog_dir=Path("catalogs"),
            rules_path=Path("rules/cross_field_rules_a.json"),
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

        # Pre-compile regex patterns for all fields that have them
        self._compiled_patterns: dict[str, re.Pattern] = {}
        for field in self.schema.fields:
            if field.pattern:
                self._compiled_patterns[field.name] = re.compile(field.pattern)

        # Pre-compile cross-field rule expressions
        self._compiled_conditions: dict[str, Any] = {}
        self._compiled_assertions: dict[str, Any] = {}
        for rule in self.cross_field_rules:
            if rule.condition:
                try:
                    self._compiled_conditions[rule.rule_id] = compile(
                        rule.condition, f"<rule:{rule.rule_id}:condition>", "eval"
                    )
                except SyntaxError:
                    self._compiled_conditions[rule.rule_id] = None
            try:
                self._compiled_assertions[rule.rule_id] = compile(
                    rule.assertion, f"<rule:{rule.rule_id}:assertion>", "eval"
                )
            except SyntaxError:
                self._compiled_assertions[rule.rule_id] = None

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

        t0 = time.perf_counter()

        # ── Layer 1: Structural / Parse ──
        logger.info("Layer 1: Parsing '%s'...", file_name)
        df, parse_errors = parse_excel(file_path, self.schema)
        all_errors.extend(parse_errors)

        # If there are structural errors that prevent further validation, stop
        if df.empty and parse_errors:
            return all_errors

        n_rows = len(df)
        logger.info("Loaded %d rows. Starting vectorized validation...", n_rows)

        # Build column mapping: field_name -> column header (only for present columns)
        col_map: dict[str, str] = {}
        for field in self.schema.fields:
            if field.column in df.columns:
                col_map[field.name] = field.column

        # Precompute excel row numbers (vectorized)
        excel_rows = np.arange(n_rows, dtype=np.int64) + self.schema.data_start_row

        # ── Layer 2 & 3: Vectorized field-level + catalog checks ──
        logger.info("Layer 2-3: Field-level + catalog validation...")
        field_errors = self._validate_fields_vectorized(
            df, col_map, excel_rows, file_name, sheet
        )
        all_errors.extend(field_errors)

        # ── Layer 4: Group checks (vectorized) ──
        logger.info("Layer 4: Group validation...")
        group_errors = self._validate_groups_vectorized(
            df, col_map, excel_rows, file_name, sheet
        )
        all_errors.extend(group_errors)

        # ── Layer 5: Cross-field checks ──
        if self.cross_field_rules:
            logger.info("Layer 5: Cross-field validation (%d rules)...",
                        len(self.cross_field_rules))
            xf_errors = self._validate_cross_fields_vectorized(
                df, col_map, excel_rows, file_name, sheet
            )
            all_errors.extend(xf_errors)

        elapsed = time.perf_counter() - t0
        logger.info(
            "Validation complete for '%s': %d error(s) found in %.2fs.",
            file_name, len(all_errors), elapsed,
        )
        return all_errors

    # ─────────────────────────────────────────────────────────────────
    # Vectorized Layer 2 & 3: Field-level + Catalog
    # ─────────────────────────────────────────────────────────────────
    def _validate_fields_vectorized(
        self,
        df: pd.DataFrame,
        col_map: dict[str, str],
        excel_rows: np.ndarray,
        file_name: str,
        sheet: str,
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []
        n_rows = len(df)

        for field in self.schema.fields:
            col = col_map.get(field.name)
            if col is None:
                continue  # column missing, already reported in structural checks

            # Get the raw series, stripped
            series = df[col]
            str_series = series.fillna("").astype(str).str.strip()
            is_empty = str_series == ""

            # ── Required check ──
            if field.is_required:
                empty_mask = is_empty
                if empty_mask.any():
                    empty_rows = excel_rows[empty_mask.values]
                    for row in empty_rows:
                        errors.append(ValidationError(
                            file_name=file_name, sheet=sheet, row=int(row),
                            field_name=field.name, rule_id="REQUIRED",
                            severity=Severity.ERROR,
                            message=f"Required field '{field.name}' is empty.",
                            actual_value=None, expected="non-empty",
                        ))

            # For non-empty values: run type, length, pattern, catalog checks
            non_empty_mask = ~is_empty
            if not non_empty_mask.any():
                continue

            ne_str_series = str_series[non_empty_mask]
            ne_excel_rows = excel_rows[non_empty_mask.values]

            # ── Data type check ──
            type_fail_mask = None
            if field.data_type == "integer":
                # Check if values can be parsed as integers
                # A valid integer string: optional sign, digits, no decimal point
                type_fail_mask = ~ne_str_series.str.fullmatch(r"-?\d+")
                if type_fail_mask.any():
                    fail_rows = ne_excel_rows[type_fail_mask.values]
                    fail_vals = ne_str_series[type_fail_mask].values
                    for row, val in zip(fail_rows, fail_vals):
                        errors.append(ValidationError(
                            file_name=file_name, sheet=sheet, row=int(row),
                            field_name=field.name, rule_id="TYPE_INTEGER",
                            severity=Severity.ERROR,
                            message=f"Field '{field.name}' expected integer, got '{val}'.",
                            actual_value=val, expected="integer",
                        ))

            elif field.data_type == "date":
                fmt = field.date_format or "%Y-%m-%d"
                # Try to parse dates vectorized with pandas
                parsed = pd.to_datetime(ne_str_series, format=fmt, errors="coerce")
                type_fail_mask = parsed.isna()
                if type_fail_mask.any():
                    fail_rows = ne_excel_rows[type_fail_mask.values]
                    fail_vals = ne_str_series[type_fail_mask].values
                    for row, val in zip(fail_rows, fail_vals):
                        errors.append(ValidationError(
                            file_name=file_name, sheet=sheet, row=int(row),
                            field_name=field.name, rule_id="TYPE_DATE",
                            severity=Severity.ERROR,
                            message=(
                                f"Field '{field.name}' expected date format "
                                f"'{fmt}', got '{val}'."
                            ),
                            actual_value=val, expected=f"date in format {fmt}",
                        ))

            # Skip length/pattern/catalog checks on type-failed values
            if type_fail_mask is not None and type_fail_mask.any():
                valid_mask = ~type_fail_mask
                check_str_series = ne_str_series[valid_mask]
                check_excel_rows = ne_excel_rows[valid_mask.values]
            else:
                check_str_series = ne_str_series
                check_excel_rows = ne_excel_rows

            if check_str_series.empty:
                continue

            # ── Length check ──
            if field.length is not None:
                str_lens = check_str_series.str.len()
                len_fail = str_lens != field.length
                if len_fail.any():
                    fail_rows = check_excel_rows[len_fail.values]
                    fail_vals = check_str_series[len_fail].values
                    fail_lens = str_lens[len_fail].values
                    for row, val, actual_len in zip(fail_rows, fail_vals, fail_lens):
                        errors.append(ValidationError(
                            file_name=file_name, sheet=sheet, row=int(row),
                            field_name=field.name, rule_id="LENGTH",
                            severity=Severity.ERROR,
                            message=(
                                f"Field '{field.name}' must be exactly "
                                f"{field.length} characters (actual: {int(actual_len)})."
                            ),
                            actual_value=val,
                            expected=f"exactly {field.length} characters",
                        ))

            # ── Regex pattern check ──
            if field.pattern is not None:
                compiled = self._compiled_patterns.get(field.name)
                if compiled:
                    pat_fail = ~check_str_series.str.fullmatch(compiled)
                    if pat_fail.any():
                        fail_rows = check_excel_rows[pat_fail.values]
                        fail_vals = check_str_series[pat_fail].values
                        for row, val in zip(fail_rows, fail_vals):
                            errors.append(ValidationError(
                                file_name=file_name, sheet=sheet, row=int(row),
                                field_name=field.name, rule_id="PATTERN",
                                severity=Severity.ERROR,
                                message=(
                                    f"Field '{field.name}' does not match "
                                    f"pattern '{field.pattern}'."
                                ),
                                actual_value=val,
                                expected=f"matches /{field.pattern}/",
                            ))

            # ── Layer 3: Catalog check ──
            if field.catalog:
                catalog_values = self.catalogs.get(field.catalog)
                if catalog_values is not None:
                    cat_fail = ~check_str_series.isin(catalog_values)
                    if cat_fail.any():
                        fail_rows = check_excel_rows[cat_fail.values]
                        fail_vals = check_str_series[cat_fail].values
                        for row, val in zip(fail_rows, fail_vals):
                            errors.append(ValidationError(
                                file_name=file_name, sheet=sheet, row=int(row),
                                field_name=field.name,
                                rule_id=f"CATALOG_{field.catalog}",
                                severity=Severity.ERROR,
                                message=(
                                    f"Field '{field.name}' value '{val}' is not in "
                                    f"catalog '{field.catalog}'."
                                ),
                                actual_value=val,
                            ))
                else:
                    logger.warning(
                        "Catalog '%s' referenced by field '%s' not found.",
                        field.catalog, field.name,
                    )

        return errors

    # ─────────────────────────────────────────────────────────────────
    # Vectorized Layer 4: Group validation
    # ─────────────────────────────────────────────────────────────────
    def _validate_groups_vectorized(
        self,
        df: pd.DataFrame,
        col_map: dict[str, str],
        excel_rows: np.ndarray,
        file_name: str,
        sheet: str,
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []
        groups = self.schema.get_all_groups()

        for group_name, group_fields in groups.items():
            # Build boolean DataFrame: which fields are non-empty per row
            field_cols = []
            field_names_in_group = []
            for f in group_fields:
                col = col_map.get(f.name)
                if col is None:
                    continue
                field_cols.append(col)
                field_names_in_group.append(f.name)

            if not field_cols:
                continue

            # Create a boolean frame: True where non-empty
            non_empty_df = pd.DataFrame({
                fname: df[col].fillna("").astype(str).str.strip() != ""
                for fname, col in zip(field_names_in_group, field_cols)
            })

            # Count filled and total per row
            filled_count = non_empty_df.sum(axis=1)
            total = len(field_names_in_group)

            # Partial fill rows: at least one filled, but not all
            partial_mask = (filled_count > 0) & (filled_count < total)

            if not partial_mask.any():
                continue

            # For each partial row, find which fields are missing
            partial_indices = np.where(partial_mask.values)[0]
            partial_non_empty = non_empty_df.iloc[partial_indices]
            partial_excel_rows = excel_rows[partial_indices]

            for i, (idx, row_vals) in enumerate(partial_non_empty.iterrows()):
                excel_row = int(partial_excel_rows[i])
                filled_names = [fname for fname in field_names_in_group if row_vals[fname]]
                empty_names = [fname for fname in field_names_in_group if not row_vals[fname]]
                filled_str = ", ".join(f"'{n}'" for n in filled_names)

                for missing_name in empty_names:
                    errors.append(ValidationError(
                        file_name=file_name, sheet=sheet, row=excel_row,
                        field_name=missing_name,
                        rule_id=f"GROUP_{group_name}",
                        severity=Severity.ERROR,
                        message=(
                            f"Field '{missing_name}' is required because "
                            f"{filled_str} in group '{group_name}' "
                            f"{'is' if len(filled_names) == 1 else 'are'} populated."
                        ),
                        actual_value=None,
                        expected="non-empty (group constraint)",
                    ))

        return errors

    # ─────────────────────────────────────────────────────────────────
    # Vectorized Layer 5: Cross-field validation
    # ─────────────────────────────────────────────────────────────────
    def _validate_cross_fields_vectorized(
        self,
        df: pd.DataFrame,
        col_map: dict[str, str],
        excel_rows: np.ndarray,
        file_name: str,
        sheet: str,
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []

        # Build the evaluation context DataFrame once:
        # Map field schema names -> column header names, and also expose column names directly
        # We need to build a context dict with safe keys for each row.
        # Instead of row-by-row, we pre-build a dict of column -> safe_key mappings.

        safe_key_map: dict[str, str] = {}  # original column -> safe key
        clean_key_map: dict[str, str] = {}  # original column -> cleaned key (no leading numbers)

        for field_schema in self.schema.fields:
            col = col_map.get(field_schema.name)
            if col is None:
                continue
            # Use the column header as the variable name (with safe replacements)
            safe_key = col.replace(" ", "_").replace("-", "_").replace("/", "_")
            safe_key_map[col] = safe_key
            # Also create a clean key (strip leading numbers/dots)
            clean_key = re.sub(r"^\d+[\._\s]*", "", safe_key)
            if clean_key and clean_key != safe_key:
                clean_key_map[col] = clean_key

        # Pre-build a "context frame" — one column per safe variable name
        # Convert NaN/empty to None for cleaner expressions
        ctx_data: dict[str, np.ndarray] = {}
        for col, safe_key in safe_key_map.items():
            series = df[col].fillna("").astype(str).str.strip()
            # Build array: None where empty, stripped string otherwise
            is_empty = (series == "")
            arr = np.where(is_empty.values, None, series.values)
            ctx_data[safe_key] = arr
            # Also map clean key
            if col in clean_key_map:
                ctx_data[clean_key_map[col]] = arr

        n_rows = len(df)

        # Process rules in chunks for memory efficiency
        CHUNK_SIZE = 10_000
        n_chunks = (n_rows + CHUNK_SIZE - 1) // CHUNK_SIZE

        for rule in self.cross_field_rules:
            compiled_cond = self._compiled_conditions.get(rule.rule_id)
            compiled_assert = self._compiled_assertions.get(rule.rule_id)

            if compiled_assert is None and rule.assertion:
                # Compilation failed earlier
                for row_idx in range(n_rows):
                    errors.append(ValidationError(
                        file_name=file_name, sheet=sheet,
                        row=int(excel_rows[row_idx]),
                        field_name="(cross-field)",
                        rule_id=rule.rule_id,
                        severity=Severity.WARNING,
                        message=(
                            f"Rule '{rule.rule_id}' could not be compiled: "
                            f"Assertion: {rule.assertion!r}"
                        ),
                    ))
                continue

            # Evaluate rule for each row using pre-built context
            for chunk_start in range(0, n_rows, CHUNK_SIZE):
                chunk_end = min(chunk_start + CHUNK_SIZE, n_rows)

                for row_idx in range(chunk_start, chunk_end):
                    # Build per-row context from pre-computed arrays
                    ctx = dict(_SAFE_BUILTINS)
                    for key, arr in ctx_data.items():
                        ctx[key] = arr[row_idx]

                    try:
                        # Check condition
                        if rule.condition and compiled_cond:
                            condition_met = eval(compiled_cond, {"__builtins__": {}}, ctx)
                            if not condition_met:
                                continue

                        # Evaluate assertion
                        result = eval(compiled_assert, {"__builtins__": {}}, ctx)
                        if result:
                            continue

                    except Exception as exc:
                        errors.append(ValidationError(
                            file_name=file_name, sheet=sheet,
                            row=int(excel_rows[row_idx]),
                            field_name="(cross-field)",
                            rule_id=rule.rule_id,
                            severity=Severity.WARNING,
                            message=(
                                f"Rule '{rule.rule_id}' could not be evaluated: {exc}. "
                                f"Condition: {rule.condition!r}, Assertion: {rule.assertion!r}"
                            ),
                        ))
                        continue

                    # Assertion failed
                    errors.append(ValidationError(
                        file_name=file_name, sheet=sheet,
                        row=int(excel_rows[row_idx]),
                        field_name="(cross-field)",
                        rule_id=rule.rule_id,
                        severity=Severity(rule.severity),
                        message=(
                            f"Cross-field rule '{rule.rule_id}' failed: {rule.description}. "
                            f"Assertion: {rule.assertion}"
                        ),
                        expected=rule.assertion,
                    ))

        return errors
