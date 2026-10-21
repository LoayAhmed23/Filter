"""Main entry point for the regulatory file verifier.

Usage:
    python main.py <excel_file> --schema <schema_yaml> [options]

Examples:
    python main.py report_a.xlsx --schema schemas/file_a.yaml
    python main.py report_a.xlsx --schema schemas/file_a.yaml --output errors.xlsx
    python main.py report_a.xlsx --schema schemas/file_a.yaml --rules rules/cross_field_rules.yaml
"""

import argparse
import sys
from pathlib import Path

from engine.validator import validate_file
from reporting.error_reporter import print_summary, save_to_excel


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
        help="Path to the schema file.",
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
        help="Path to the cross-field rules file.",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output file for the error report (.xlsx or .json).",
    )

    args = parser.parse_args()

    # Run validation
    errors = validate_file(
        file_path=args.file,
        schema_path=args.schema,
        catalog_dir=args.catalogs,
        rules_path=args.rules,
    )

    # Report results
    print_summary(errors)

    if args.output:
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
