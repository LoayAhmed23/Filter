"""Main entry point for the regulatory file verifier.

Usage:
    python main.py <excel_file> --schema <schema_yaml> [options]

Examples:
    python main.py report_a.xlsx --schema schemas/file_a.yaml
    python main.py report_a.xlsx --schema schemas/file_a.yaml --output errors.xlsx
    python main.py report_a.xlsx --schema schemas/file_a.yaml --rules rules/cross_field_rules.yaml
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from engine.validator import FileValidator
from reporting.error_reporter import print_summary, save_to_excel, save_to_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate regulatory Excel files against a YAML schema.",
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to the Excel file to validate.",
    )
    parser.add_argument(
        "--schema", "-s",
        type=Path,
        required=True,
        help="Path to the YAML schema file.",
    )
    parser.add_argument(
        "--catalogs", "-c",
        type=Path,
        default=Path("catalogs"),
        help="Directory containing catalog CSV files (default: catalogs/).",
    )
    parser.add_argument(
        "--rules", "-r",
        type=Path,
        default=None,
        help="Path to the cross-field rules YAML file.",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output file for the error report (.xlsx or .json).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging.",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Build the validator
    validator = FileValidator(
        schema_path=args.schema,
        catalog_dir=args.catalogs,
        rules_path=args.rules,
    )

    # Run validation
    errors = validator.validate(args.file)

    # Report results
    print_summary(errors)

    if args.output:
        ext = args.output.suffix.lower()
        if ext == ".json":
            save_to_json(errors, args.output)
        else:
            save_to_excel(errors, args.output)

    # Exit code: 1 if errors, 0 if clean
    has_errors = any(e.severity.value == "ERROR" for e in errors)
    return 1 if has_errors else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())
