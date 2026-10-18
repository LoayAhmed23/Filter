# Regulatory File Verifier — Project Guide

## Project Structure

```
Filter/
├── main.py                          # CLI entry point
├── requirements.txt                 # pandas, openpyxl
│
├── schemas/                         # ⬅ YOUR FIELD DEFINITIONS GO HERE
│   ├── file_a.json                  # Schema for Report A (~70 fields)
│   └── file_b.json                  # Schema for Report B
│
├── catalogs/                        # ⬅ YOUR LOOKUP TABLES GO HERE
│   ├── currency_codes.csv
│   ├── country_codes.csv
│   ├── transaction_types.csv
│   ├── agent_codes.csv
│   └── branch_codes.csv
│
├── rules/                           # ⬅ CROSS-FIELD RULES GO HERE
│   └── cross_field_rules.json
│
├── engine/                          # Validation engine (no edits needed)
│   ├── models.py                    # Data models & dataclasses
│   ├── schema_loader.py             # JSON/CSV loaders
│   ├── parser.py                    # Excel reader + structural checks
│   ├── field_validator.py           # Type, length, required, pattern
│   ├── catalog_validator.py         # Lookup table membership
│   ├── group_validator.py           # Conditional-mandatory groups
│   ├── cross_field_validator.py     # Inter-field correlations
│   └── validator.py                 # Pipeline orchestrator
│
└── reporting/
    └── error_reporter.py            # Console, Excel, JSON output
```

## Quick Start

```bash
pip install -r requirements.txt

# Validate a file
python main.py report.xlsx --schema schemas/file_a.json

# With cross-field rules
python main.py report.xlsx -s schemas/file_a.json -r rules/cross_field_rules.json

# Output errors to Excel
python main.py report.xlsx -s schemas/file_a.json -o errors.xlsx

# Verbose logging
python main.py report.xlsx -s schemas/file_a.json -v
```

---

## How to Customize

### 1. Define Your Fields in `schemas/file_a.json`

Each field supports these properties:

| Property | Required | Description |
|---|---|---|
| `name` | ✅ | Internal field name (used in cross-field rules) |
| `column` | ✅ | **Excel column header** exactly as it appears |
| `data_type` | | `string`, `integer`, `float`, `date`, `boolean` |
| `category` | ✅ | `required`, `optional`, or `group:<name>` |
| `max_length` | | Max string length |
| `min_length` | | Min string length |
| `pattern` | | Regex the value must match |
| `catalog` | | Name of CSV file in `catalogs/` (without `.csv`) |
| `date_format` | | Python strftime format (default: `%Y-%m-%d`) |
| `min_value` | | Minimum numeric value |
| `max_value` | | Maximum numeric value |

**Example field:**

```json
{
  "name": "currency_code",
  "column": "Currency",
  "data_type": "string",
  "category": "required",
  "catalog": "currency_codes",
  "max_length": 3,
  "min_length": 3,
  "description": "ISO 4217 currency code"
}
```

### 2. Add Catalogs in `catalogs/`

Each CSV must have a **header row** and the **first column** holds the allowed values:

```csv
code,description
SAR,Saudi Riyal
USD,US Dollar
```

### 3. Define Groups (Conditional Mandatory)

In the schema JSON, tag related fields with the **same group name** in their `category`:

```json
[
  { "name": "agent_code",   "column": "Agent Code",   "category": "group:agent_info" },
  { "name": "agent_name",   "column": "Agent Name",   "category": "group:agent_info" },
  { "name": "agent_branch", "column": "Agent Branch",  "category": "group:agent_info" }
]
```

> [!IMPORTANT]
> If **any** field in the group is filled → **all** fields in that group become mandatory.

### 4. Define Cross-Field Rules in `rules/cross_field_rules.json`

```json
{
  "rule_id": "R001",
  "description": "Domestic transactions must have local country code",
  "condition": "transaction_type == 'DOMESTIC'",
  "assertion": "country_code == 'SA'",
  "severity": "ERROR"
}
```

- **Field names** in expressions use underscores (e.g., `Transaction Type` → `transaction_type`)
- **condition** is optional — if omitted, the assertion is always checked
- **severity** can be `ERROR` or `WARNING`

---

## Validation Pipeline (5 Layers)

```
Layer 1 → Structural    (file exists, sheet exists, columns match)
Layer 2 → Field-level   (type, length, required, pattern, range)
Layer 3 → Catalog       (value ∈ allowed set)
Layer 4 → Group         (conditional mandatory)
Layer 5 → Cross-field   (correlated value constraints)
```

All errors are **collected** (not fail-fast) — you get a complete report every run.

---

## Output Formats

| Flag | Format | Example |
|---|---|---|
| *(none)* | Console summary with icons | default |
| `-o errors.xlsx` | Excel spreadsheet | one row per error |
| `-o errors.json` | JSON array | machine-readable |

> [!NOTE]
> The loader auto-detects JSON vs YAML by file extension, so `.yaml` files still work as a fallback if `pyyaml` is installed.
