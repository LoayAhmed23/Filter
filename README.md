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

Schemas define the sheet structure and column-level constraints (`schemas/*.json` or `schemas/*.yaml`):

```json
{
  "name": "Credit Facility",
  "description": "Regulatory credit facility submission schema",
  "sheet_name": 0,
  "header_row": 1,
  "data_start_row": 2,
  "fields": [
    {
      "name": "1. Segment Identifier",
      "column": "Segment_Identifier",
      "data_type": "string",
      "category": "required",
      "length": 4,
      "description": "Must contain the value CNCF"
    },
    {
      "name": "2. Data Provider ID",
      "column": "Data_Provider_ID",
      "data_type": "string",
      "category": "required",
      "length": 10,
      "pattern": "^[A-Za-z0-9]{10}$"
    },
    {
      "name": "3. Customer Name",
      "column": "Customer_Name",
      "data_type": "string",
      "category": "required",
      "length": 40,
      "min_length": 2
    },
    {
      "name": "4. Open Date",
      "column": "Open_Date",
      "data_type": "date",
      "category": "required",
      "length": 8,
      "date_format": "%Y%m%d"
    },
    {
      "name": "5. Consent Status",
      "column": "Consent_Status",
      "data_type": "string",
      "category": "required",
      "length": 3,
      "catalog": "consent_statuses"
    },
    {
      "name": "6. Collateral Amount 1",
      "column": "Collateral_Amount_1",
      "data_type": "integer",
      "category": "group:collateral",
      "length": 20
    }
  ]
}
```

#### File-Level Options

| Property | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | string | **[required]** | Logical name of the schema. |
| `description` | string | `""` | Description or metadata for the schema file. |
| `sheet_name` | string \| int | `"Sheet1"` | Excel sheet name or 0-indexed sheet index. |
| `header_row` | int | `1` | 1-indexed Excel row where column headers are located. |
| `data_start_row` | int | `2` | 1-indexed Excel row where data rows begin. |
| `fields` | array | `[]` | List of field constraint objects. |

#### Field-Level Options

| Property | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | string | **[required]** | Human-readable field label (used in error reports). |
| `column` | string | **[required]** | Header column name or Excel column letter (e.g. `"Segment_Identifier"` or `"A"`). |
| `length` | int | **[required]** | Character length specification. Exact length if `min_length` is omitted; maximum length if `min_length` is provided. |
| `category` | string | `"optional"` | Requirement constraint: `"required"`, `"optional"`, or `"group:<name>"`. |
| `data_type` | string | `"string"` | Data type: `"string"`, `"integer"`, `"date"`, `"float"`, or `"boolean"`. |
| `min_length` | int \| null | `null` | Optional minimum character length. Supersedes exact length measurement and validates range `min_length <= len <= length`. |
| `pattern` | string \| null | `null` | Regex pattern that non-empty values must fully match. |
| `catalog` | string \| null | `null` | Name of reference CSV in `catalogs/` (without `.csv`) containing allowed values. |
| `date_format` | string \| null | `"%Y-%m-%d"` | Python `strptime` date format when `data_type` is `"date"`. |
| `description` | string | `""` | Optional documentation explaining the field. |

#### Field Categories
- `"required"`: Must not be null or empty.
- `"optional"`: Can be empty.
- `"group:<name>"`: If any field in this group is populated, all other fields in the group must also be populated.

#### Field Length Validation
- `length` (required): Character length specification for the field. When `min_length` is not provided, enforces an exact character length (`len == length`).
- `min_length` (optional): Minimum character length. When provided alongside `length`, `length` is treated as the maximum allowed length (validating `min_length <= len <= length`).

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
