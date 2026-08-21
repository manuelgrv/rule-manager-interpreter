# Rule Manager Interpreter

Rule Manager Interpreter is a working MVP for authoring, compiling, inspecting, executing, and versioning business rules without running arbitrary user code in production.

Restricted SQL, Python expressions, and PySpark-style pipelines compile into a common, versioned JSON DSL. The DSL—not the original script—is validated and executed using DuckDB or PySpark.

## Live demo

Open [Rule Studio — Databricks App Demo](https://rule-studio-databricks-demo.manuelrodval.chatgpt.site).

The demo provides:

- a visual rule builder and `.sql`/`.py` upload;
- deterministic DSL compilation and SHA-256 integrity validation;
- execution against 10,000 synthetic customers with 15 financial and customer features;
- decision distributions and sample results;
- persistent, versioned rule publication with author and timestamp metadata.

The hosted application represents how the solution can operate inside Databricks Apps. It uses a portable TypeScript implementation because the demo does not depend on a live Databricks workspace. The Python package under `src/` is the reference implementation.

## Implemented capabilities

### Compilation and validation

- Restricted Python expressions parsed with Python `ast`; no `eval` or `exec`.
- Restricted PySpark DataFrame pipelines parsed rather than executed.
- Read-only SQL `SELECT` parsed with SQLGlot.
- Catalog validation for tables, columns, types, and supported operations.
- Explicit rejection of imports, arbitrary Python, SQL mutations, unknown fields, and unsupported syntax.

### DSL and execution

- Common relational nodes: `scan`, `join`, `filter`, `project`, `sort`, and `limit`.
- Typed literals, columns, comparisons, boolean expressions, functions, `CASE`, and structured decisions.
- Versioned rule metadata, logical inputs, output schema, compiler metadata, and SHA-256 digest.
- DuckDB execution over registered tables.
- PySpark execution over registered Parquet fixtures.
- SQL-style null behavior: null remains null unless handled explicitly.
- Source-versus-DSL equivalence tests across supported engines.

The DSL contains no executable Python or unvalidated SQL fragments.

## Architecture

```text
SQL / Python / PySpark
          |
          v
Parser -> Catalog validation -> Versioned DSL
                                      |
                         inspect / test / publish
                                      |
                                      v
                    Integrity + capability checks
                              /             \
                         DuckDB             PySpark
```

The target Databricks flow is:

```text
Risk specialist
      |
Databricks App (visual editor or .sql/.py upload)
      |
Interpreter library from Artifactory
      |
      +-> compile -> RDV versioned exercises -> DDV approved rules
      +-> execute selected DSL versions from development or production jobs

EDV: experimentation and testing
RDV: versioned rule exercises and metadata
DDV: approved rules available for consumption
```

See `business/databricks-rule-manager.c4` for the complete LikeC4 model.

## Quick start

Requirements: Python 3.11+, `uv`, and Java 17+ for PySpark.

```bash
uv sync
uv run rule-manager build-demo
uv run rule-manager verify-demo --engine duckdb
uv run rule-manager verify-demo --engine spark
uv run pytest
```

## CLI

Compilation and execution are separate so a DSL artifact can be inspected and approved before it runs.

```bash
# SQL -> DSL
uv run rule-manager sql-to-dsl demo/rules/credit_decisions.sql \
  --catalog demo/catalog.json \
  --output demo/generated/credit_decisions.dsl.json

# Python expression -> DSL
uv run rule-manager py-to-dsl demo/rules/client_status.py \
  --schema demo/client_schema.json \
  --output demo/generated/client_status.dsl.json

# PySpark pipeline -> DSL
uv run rule-manager py-to-dsl demo/rules/credit_decisions_pyspark.py \
  --catalog demo/catalog.json \
  --output demo/generated/credit_decisions_pyspark.dsl.json

# Execute validated DSL
uv run rule-manager execute demo/generated/credit_decisions.dsl.json \
  --engine duckdb \
  --catalog demo/catalog.json
```

Replace `duckdb` with `spark` to use the PySpark backend.

## Demo assets

- `demo/`: DuckDB database, Parquet fixtures, catalogs, schemas, rules, and generated DSL.
- `notebooks/rule_manager_demo.ipynb`: source-to-DSL execution and equivalence walkthrough.
- `business/databricks-rule-manager.c4`: target Databricks architecture.
- `business/interprete_reglas_deterministico.pptx`: Spanish business presentation.
- `web/`: deployable Databricks App-style web demo.

To refresh the notebook outputs:

```bash
uv run jupyter execute notebooks/rule_manager_demo.ipynb --inplace --timeout=180
```

## Repository structure

```text
src/rule_interpreter/
├── api.py              # Public compile and execute API
├── catalog.py          # Logical sources, schemas, and bindings
├── cli.py              # CLI commands
├── dsl.py              # Envelope and integrity validation
├── parsers/            # Python, PySpark, and SQL parsers
└── executors/          # DuckDB, Spark, and SQL rendering

demo/                    # Data and example rules
notebooks/               # Executable walkthrough
tests/                   # Pipeline, integrity, and rejection tests
business/                # Architecture and presentation
web/                     # Public web demo
```

## Safety and limitations

- Submitted Python and PySpark are parsed, never evaluated.
- SQL must be a supported read-only `SELECT`.
- Tables and columns must exist in the supplied catalog.
- Only implemented DSL nodes and functions are accepted.
- The original source is never forwarded to an executor.
- DSL integrity is checked before execution.

The MVP is not a complete production authorization boundary. Authentication, authorization, approval gates, resource limits, observability, signing, retention, and controlled rollback must be added for production use.

CTEs, subqueries, aggregation, unions, runtime parameters, broader function coverage, and production lifecycle controls remain outside the current reference implementation. Unsupported constructs fail explicitly.
