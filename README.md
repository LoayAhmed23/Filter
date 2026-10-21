## Checks performed

- **Structure**: Sheet presence, header placement, and missing required columns.
- **Fields**: Data types (`string`, `integer`, `date`), character lengths, regex patterns, and required/optional values.
- **Catalogs**: Validates codes against reference CSV tables in `catalogs/`.
- **Field Groups**: Dependent fields (e.g. if one collateral or address field is set, related fields must be set too).
- **Cross-field logic**: Custom business rules across multiple columns (e.g. overdue days vs. overdue amount).

## Setup

```bash
pip install -r requirements.txt
```

*(Requires Python 3.10+)*

## Usage

```bash
# Basic validation
python main.py data.xlsx -s schemas/CF_schema.json

# Full check with business rules and Excel report export
python main.py data.xlsx \
  -s schemas/CF_schema.json \
  -r rules/cross_field_rules_CF.json \
  -o errors.xlsx
```

### Options

| Flag | Description |
| --- | --- |
| `-s, --schema` | Path to schema file (`.json` or `.yaml`) **[required]** |
| `-r, --rules` | Path to cross-field rules file (`.json` or `.yaml`) |
| `-c, --catalogs` | Directory with catalog CSVs (default: `catalogs/`) |
| `-o, --output` | Path to export error report (`.xlsx`) |

Exits with `0` on clean run (or warnings only), and `1` if any validation errors are detected.

## Configuration

### Schemas

Schemas define the sheet structure and column-level constraints (`schemas/*.json`):

```json
{
  "name": "Credit Facility",
  "sheet_name": 0,
  "header_row": 1,
  "data_start_row": 2,
  "fields": [
    {
      "column": "Segment_Identifier",
      "data_type": "string",
      "category": "required",
      "length": 4
    },
    {
      "column": "Consent_Status",
      "data_type": "string",
      "category": "required",
      "catalog": "consent_statuses"
    },
    {
      "column": "Collateral_Amount_1",
      "data_type": "integer",
      "category": "group:collateral"
    }
  ]
}
```

Field categories:
- `"required"`: Must not be null or empty.
- `"optional"`: Can be empty.
- `"group:<name>"`: If any field in this group is populated, all other fields in the group must be populated as well.

### Cross-Field Rules

Define multi-column business logic (`rules/*.json`):

```json
[
  {
    "rule_id": "R001",
    "description": "Primary Card Number required when Liability Indicator is 003",
    "condition": "Liability_Indicator == '003'",
    "assertion": "Primary_Card_Number is not None",
    "severity": "ERROR"
  },
  {
    "rule_id": "R006",
    "description": "If past due days > 0, amount overdue must be > 0",
    "condition": "int(Number_of_Days_Past_Due or 0) > 0",
    "assertion": "int(Amount_Overdue or 0) > 0",
    "severity": "ERROR"
  }
]
```

- `condition`: Optional filter expression.
- `assertion`: Must evaluate to `True` for each row that satisfies `condition`.
- `severity`: `"ERROR"` or `"WARNING"`.

## Project Layout

```
Filter/
├── main.py              # CLI entry point
├── engine/              # Parsing, schema loading, and validation pipeline
├── reporting/           # Terminal summaries and Excel error exporting
├── catalogs/            # CSV lookup tables (currencies, status codes, etc.)
├── schemas/             # Schema definitions
└── rules/               # Cross-field business rules
```
