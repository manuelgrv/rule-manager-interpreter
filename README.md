# Rule Manager Interpreter

## Purpose

This project is a controlled runtime for business rules used in banking workflows. It will accept rules written in a restricted Python/PySpark-like or SQL-like syntax, validate and translate them into a common internal representation, and execute them against an approved data context.

The goal is to let authorized users change business logic without shipping application code for every rule change, while preserving the review, security, audit, and rollback controls required in production.

This is **not** intended to execute arbitrary Python or unrestricted SQL.

## Quick start

Prerequisites are Python 3.11+ and Java 17+ for PySpark. The project uses `uv` for reproducible setup:

```bash
uv sync
uv run rule-manager build-demo
uv run rule-manager verify-demo --engine duckdb
uv run rule-manager verify-demo --engine spark
```

`build-demo` creates `demo/banking.duckdb` and matching Parquet files from deterministic synthetic data. `verify-demo` executes the original SQL directly, compiles it to DSL, executes the DSL on the selected engine, normalizes both results, and fails unless they match.

The three core commands can also be run separately:

```bash
uv run rule-manager sql-to-dsl demo/rules/credit_decisions.sql \
  --catalog demo/catalog.json \
  --output demo/generated/credit_decisions.dsl.json

uv run rule-manager py-to-dsl demo/rules/client_status.py \
  --schema demo/client_schema.json \
  --output demo/generated/client_status.dsl.json

uv run rule-manager py-to-dsl demo/rules/credit_decisions_pyspark.py \
  --catalog demo/catalog.json \
  --output demo/generated/credit_decisions_pyspark.dsl.json

uv run rule-manager execute demo/generated/credit_decisions.dsl.json \
  --engine duckdb \
  --catalog demo/catalog.json
```

Replace `duckdb` with `spark` in the final command to execute the same DSL using real PySpark.

### Demo notebook

The pre-executed notebook at `notebooks/rule_manager_demo.ipynb` walks through the workflow visually for both input languages. It displays and directly executes the original SQL and PySpark DataFrame files, displays both generated JSON DSL documents, executes each DSL on DuckDB and real PySpark, and proves that all six paths produce identical results.

To refresh every saved output after changing the compiler or demo rule:

```bash
uv run jupyter execute notebooks/rule_manager_demo.ipynb --inplace --timeout=180
```

## Design principles

- **Safe by default:** only explicitly supported syntax, functions, fields, and operations are allowed.
- **One semantic model:** Python and SQL inputs compile to the same intermediate representation (IR), so equivalent rules behave consistently.
- **Separate compilation from execution:** parsing and validation happen before a rule can be run.
- **Deterministic and testable:** a rule should produce the same result for the same versioned inputs and context.
- **Auditable:** retain source, normalized IR, version, author, approval state, timestamps, and execution results.
- **Backend-independent core:** use a lightweight local evaluator as the semantic reference and ship the required PySpark backend behind the same stable interface.
- **No implicit production access:** the caller supplies a constrained data context; rules cannot open files, import modules, use the network, or access credentials.

## Proposed architecture

```text
Python-like rule ─┐
                  ├─> Parser -> Validator -> Normalized IR -> Executor -> Result
SQL-like rule ────┘                    │              │
                                      │              ├─ Local evaluator
                                      │              ├─ DuckDB adapter
                                      │              └─ PySpark adapter
                                      └─ Diagnostics and audit metadata
```

### 1. Source languages

The first version will support two input syntaxes:

- Python-like expressions parsed with Python's `ast` module, never `eval` or `exec`.
- Full, read-only SQL `SELECT` statements parsed by a dedicated SQL parser, never by string rewriting.

The Python-like syntax will initially focus on expressions and structured rule decisions. The SQL syntax has a broader target and should support:

- literals: strings, numbers, booleans, and nulls;
- approved field references;
- comparisons: equality, inequality, ordering, membership, and null checks;
- boolean operators: `and`, `or`, and `not`;
- arithmetic needed by rule expressions;
- a small allowlist of pure functions, such as string normalization and date operations;
- projections, aliases, filtering, joins, grouping, aggregate functions, ordering, and limits;
- common expressions such as `CASE`, casts, date operations, and explicit null handling;
- structured decisions containing an outcome, reason, and optional action or supporting data.

SQL subqueries and common table expressions are part of the intended broad scope, although they may be delivered incrementally. DDL, DML, administrative commands, and access to unregistered catalogs remain prohibited. Python loops, imports, assignment, reflection, dynamic attribute access, and user-defined code are also out of scope initially.

Broad SQL support does not mean unrestricted execution: every table, column, function, statement type, and resource limit must still pass validation before a query reaches Spark.

### 2. Command-line interface

The demo will expose three primary commands:

```text
rule-manager py-to-dsl <rule.py>  --schema <schema.json> --output <rule.dsl.json>
rule-manager sql-to-dsl <rule.sql> --catalog <catalog.json> --output <rule.dsl.json>
rule-manager execute <rule.dsl.json> --engine <duckdb|spark> --catalog <catalog.json>
```

- `py-to-dsl` parses either a restricted scalar Python expression with `--schema` or a restricted PySpark DataFrame pipeline with `--catalog`, validates it, and writes versioned DSL JSON.
- `sql-to-dsl` parses a full read-only `SELECT`, validates it against the registered catalog, and writes versioned DSL JSON.
- `execute` validates the DSL envelope and compatibility again, loads only registered demo data, dispatches to the selected backend, and emits structured results.

The demo also provides `build-demo` and `verify-demo` convenience commands. They create reproducible fixtures and run the source-versus-DSL acceptance check; they are not part of the production rule API.

Compilation and execution are deliberately separate. The generated DSL artifact can be inspected, tested, reviewed, checksummed, stored, and approved before it is executed. Commands should write results to standard output by default, diagnostics to standard error, and return non-zero exit codes for invalid source, invalid DSL, or execution failure.

The initial CLI only accepts local files. Reading source from standard input, accepting inline source, batch execution, and service/API transport can be added without changing the compiler or executor contracts.

### 3. Intermediate representation

Both parsers produce typed IR nodes rather than executable source text. Example:

```json
{
  "type": "and",
  "operands": [
    {
      "type": "comparison",
      "operator": "gte",
      "left": {"type": "field", "name": "customer.age"},
      "right": {"type": "literal", "value": 18}
    },
    {
      "type": "comparison",
      "operator": "eq",
      "left": {"type": "field", "name": "account.status"},
      "right": {"type": "literal", "value": "ACTIVE"}
    }
  ]
}
```

The IR is versioned and is the contract between compilation, persistence, and execution. It must preserve explicit null semantics and type information so Python-like and SQL-like rules do not silently disagree. Query-level IR nodes will represent projections, data sources, joins, filters, grouping, ordering, and limits in addition to scalar expressions.

The serialized DSL is a versioned envelope around the IR. At minimum it contains the DSL version, source language, expected output schema, referenced inputs, normalized IR, and integrity metadata. It contains no executable Python or interpolated SQL.

Null values remain null throughout parsing, compilation, and execution unless the submitted rule handles them explicitly, for example with `IS NULL`, `COALESCE`, or an equivalent approved Python-like function. Missing fields are schema-validation errors rather than implicit null values.

#### Data-source catalog

Physical locations and credentials do not belong in rule DSL. A separate catalog maps stable logical source names to backend-specific bindings:

```json
{
  "catalog_version": "1.0",
  "sources": {
    "clients": {
      "schema_version": "1",
      "schema": [
        {"name": "client_id", "type": "int64", "nullable": false},
        {"name": "age", "type": "int32", "nullable": false},
        {"name": "account_status", "type": "string", "nullable": false}
      ],
      "bindings": {
        "duckdb": {"kind": "table", "name": "clients"},
        "spark": {"kind": "parquet", "path": "demo/parquet/clients"}
      }
    }
  }
}
```

The compiler validates logical table and column references against the catalog schema. At execution time, the selected backend resolves the logical name through its binding. Production catalogs should be deployment-owned configuration and should resolve only approved locations; rule authors cannot place file paths, connection strings, or credentials in DSL.

#### Rule DSL envelope

A compiled rule is a self-describing, immutable envelope:

```json
{
  "dsl_version": "1.0",
  "rule": {
    "id": "credit-eligibility",
    "version": 1,
    "kind": "query",
    "source_language": "sql"
  },
  "inputs": [
    {"source": "clients", "schema_version": "1"},
    {"source": "credit_profiles", "schema_version": "1"}
  ],
  "parameters": [],
  "plan": {},
  "output": {
    "schema": [
      {"name": "client_id", "type": "int64", "nullable": false},
      {"name": "decision", "type": "decision", "nullable": false}
    ]
  },
  "compiler": {"name": "rule-manager", "version": "0.1.0"},
  "integrity": {"algorithm": "sha256", "digest": "..."}
}
```

`parameters` contains typed runtime values such as an evaluation date or configurable threshold. Parameters are distinct from fields and literals and must be supplied explicitly at execution. The integrity digest is computed from a canonical serialization of the semantic fields; operational metadata such as author and approval status remains in the rule-management system.

#### Relational plan

Full SQL and PySpark-style pipelines compile to a backend-neutral relational tree. The main plan nodes are:

- `scan`: read a logical catalog source;
- `join`: combine two plans using a typed condition and join type;
- `filter`: retain rows for which a predicate is true;
- `project`: produce named output expressions;
- `aggregate`: group rows and compute approved aggregates;
- `sort`: apply explicit ordering and null placement;
- `limit`: restrict the result size;
- later, `distinct`, `union`, and reusable subplans for SQL CTEs.

Example plan for a credit decision:

```json
{
  "op": "project",
  "input": {
    "op": "join",
    "join_type": "left",
    "left": {"op": "scan", "source": "clients", "alias": "c"},
    "right": {"op": "scan", "source": "credit_profiles", "alias": "cp"},
    "condition": {
      "expr": "compare",
      "operator": "eq",
      "left": {"expr": "column", "relation": "c", "name": "client_id", "type": "int64"},
      "right": {"expr": "column", "relation": "cp", "name": "client_id", "type": "int64"}
    }
  },
  "columns": [
    {
      "name": "client_id",
      "value": {"expr": "column", "relation": "c", "name": "client_id", "type": "int64"}
    },
    {
      "name": "decision",
      "value": {
        "expr": "decision",
        "outcome": {
          "expr": "case",
          "branches": [
            {
              "when": {
                "expr": "compare",
                "operator": "gte",
                "left": {"expr": "column", "relation": "cp", "name": "credit_score", "type": "int32"},
                "right": {"expr": "literal", "type": "int32", "value": 650}
              },
              "then": {"expr": "literal", "type": "string", "value": "APPROVE"}
            }
          ],
          "else": {"expr": "literal", "type": "string", "value": "REVIEW"}
        },
        "reason": {"expr": "literal", "type": "string", "value": "CREDIT_SCORE_POLICY"},
        "action": {"expr": "literal", "type": "string", "value": null},
        "details": {"expr": "struct", "fields": {}}
      }
    }
  ]
}
```

Every expression node carries or resolves to a DSL type. Column references are qualified after name resolution, functions use stable DSL function identifiers rather than backend names, and identifiers are never represented as raw SQL fragments.

#### Null and boolean behavior

The DSL uses SQL-style three-valued logic for portable query behavior: comparisons involving null normally produce `unknown`; filters retain only `true`; and `is_null`, `is_not_null`, and `coalesce` provide explicit handling. A null literal is represented as a typed literal with `"value": null`. The compiler rejects an untyped null when its type cannot be inferred from context.

This semantic contract is implemented identically by DuckDB and PySpark adapters and covered by cross-backend conformance tests.

### 4. Validation

Validation occurs before execution and returns useful source-positioned diagnostics. It checks:

- supported syntax and operators;
- fields against a supplied schema;
- types and function signatures;
- function and operator allowlists;
- complexity limits such as source length, nesting depth, and node count;
- the expected output type;
- compatibility with the requested execution backend.

### 5. Execution

Executors consume validated IR and an explicit context. The implemented DuckDB executor renders query IR as quoted, read-only DuckDB SQL over registered tables. The implemented PySpark executor loads approved Parquet files as temporary views and independently renders the same nodes using Spark SQL syntax. Renderer code owns all syntax and identifier quoting; submitted source text never survives in the DSL or reaches either executor. A direct DataFrame/`Column` renderer can be added behind the same IR contract.

The DSL targets capabilities, not generated source-code strings. A backend declares the IR nodes, functions, and types it supports. Execution fails before running if a DSL artifact uses an unsupported capability. This allows DuckDB and PySpark to execute the same portable subset while still permitting explicitly backend-specific capabilities later.

Execution should enforce time/resource limits at the service boundary and return a structured result containing the rule version, outcome, reason, and diagnostics. A rule is immutable after publication; changes create a new version that can be tested, approved, promoted, or rolled back.

### 6. Rule lifecycle

The interpreter library is only one part of a safe rule-management system. The intended lifecycle is:

```text
Draft -> Compile -> Validate -> Test -> Review/Approve -> Publish -> Execute
                                                        -> Roll back
```

Persistence, authentication, authorization, approval policy, and deployment are service concerns. They should use the library's versioned source, IR, and diagnostics rather than bypassing compilation.

## Proposed package layout

```text
src/rule_interpreter/
├── api.py                 # Public compile and execute interface
├── cli.py                 # py-to-dsl, sql-to-dsl, and execute commands
├── catalog.py             # Logical source schemas and physical bindings
├── demo.py                # Deterministic fixture generation and verification
├── dsl.py                 # Versioned envelope and integrity validation
├── errors.py              # Validation and execution errors
├── result.py              # Cross-engine result normalization
├── parsers/
│   ├── python_parser.py   # Restricted Python AST -> IR
│   └── sql_parser.py      # Restricted SQL AST -> IR
└── executors/
    ├── sql_renderer.py    # Trusted IR -> backend SQL renderer
    ├── duckdb.py          # DuckDB catalog and runtime adapter
    └── spark.py           # Required real-PySpark runtime adapter
tests/
├── unit/
├── conformance/           # Equivalent Python/SQL rule behavior
├── security/              # Rejected syntax and abuse cases
└── integration/
```

## Implementation plan

### Demo delivery plan

The demo will be delivered in this order:

1. **Create the sample DuckDB database.** Generate deterministic synthetic client, income, employment, debt, and credit-score data; persist it in `demo/banking.duckdb`; export the same tables to canonical Parquet fixtures; and generate the catalog/schema files used by the compilers and executors.
2. **Create the CLI.** Implement the established `py-to-dsl`, `sql-to-dsl`, and `execute` commands, including validation, useful diagnostics, stable exit codes, and JSON output suitable for automated comparison.
3. **Prove source-to-DSL equivalence.** Run an initial trusted source script/query directly against the sample data, compile that source to DSL, execute the DSL, and assert that both paths produce the same normalized result. Run this conformance check for both DuckDB and real PySpark where the selected features are supported.

Direct source execution exists only as a demo/test oracle. The production-facing execution path consumes validated DSL and must not execute arbitrary submitted Python or SQL.

Result comparison will normalize the declared output schema, column ordering, row ordering, numeric representation, timestamps, and null values. Queries whose results are compared must declare deterministic ordering or be compared as unordered row sets.

The demo is complete when a clean checkout can run one documented command sequence that creates the database and fixtures, compiles the initial source, executes its DSL, compares both outputs, and exits successfully only when they match.

### Phase 1: Define the language contract and demo data — complete for the first slice

1. Create deterministic sample client datasets with identity, income, employment, debt, and credit-score data.
2. Materialize a reproducible DuckDB database and equivalent Parquet fixtures from one deterministic seed/source definition.
3. Write representative credit-decision rules and SQL queries with their expected results.
4. Specify supported Python and SQL grammar, data types, null behavior, structured outputs, and error format.
5. Define the versioned scalar and query IR plus the input-schema/catalog model.
6. Record explicit non-goals and security limits.

**Deliverable:** an executable specification expressed as fixtures and tests.

### Phase 2: Build the safe core — complete for the first slice

1. Add project packaging, typed IR models, diagnostics, the public API, and the CLI shell.
2. Implement restricted Python AST parsing and validation.
3. Implement the local reference executor without `eval` or `exec`.
4. Add source-versus-DSL result normalization and comparison tooling.
5. Add unit, property, security, and end-to-end equivalence tests.

**Deliverable:** use `py-to-dsl` to compile a Python-like file and `execute` it against local records.

### Phase 3: Add full read-only SQL — first vertical slice complete

1. Select and integrate a SQL parser with usable AST and source locations.
2. Translate `SELECT` projections, sources, joins, filters, grouping, ordering, limits, subqueries, and common table expressions to query IR in incremental slices.
3. Reject all non-read-only statements and references to unregistered data.
4. Add conformance tests proving equivalent Python and SQL expressions yield identical scalar and null behavior.
5. Compare the initial SQL query executed directly in DuckDB with the output obtained by compiling it to DSL and executing the DSL.

**Deliverable:** use `sql-to-dsl` to compile validated full `SELECT` queries to the shared expression/query model.

### Phase 4: Add query executors — first vertical slice complete

1. Translate query IR into safe DuckDB SQL over registered tables for fast demo feedback.
2. Translate validated IR nodes into generated Spark SQL over registered Parquet-backed temporary views.
3. Validate schema and backend capability compatibility before submitting work.
4. Test DuckDB and Spark against shared expected results, especially null, numeric, date, string, join, and aggregation behavior.
5. Run the initial trusted PySpark script directly and compare its normalized output with the PySpark DSL executor output.

**Deliverable:** execute approved rules and full read-only queries on the demo Spark data without evaluating arbitrary source code.

### Phase 5: Production rule management

1. Add immutable rule versions, status transitions, and audit events.
2. Add test cases and approval gates to promotion.
3. Add authorization, observability, resource limits, rollout, and rollback support.
4. Threat-model the complete service and run adversarial tests before production use.

**Deliverable:** a production-facing service or integration with controlled rule publication and execution.

## Demo domain

The demo will model clients and their financial profile. The initial dataset should be small, deterministic, and include nulls and boundary values deliberately.

Suggested tables:

- `clients`: client ID, age, country, customer segment, and account status;
- `income`: client ID, monthly income, income source, employment status, and months employed;
- `credit_profiles`: client ID, credit score, current debt, credit utilization, delinquency count, and last score update;

The dataset will include examples such as missing credit scores, null income, exactly-at-threshold scores, high income with high debt, and otherwise eligible clients with inactive accounts. Generated data must not contain real customer information.

Parquet is the canonical demo storage format because both DuckDB and PySpark can read it directly while preserving useful schema information. The demo catalog maps logical names such as `clients` to approved Parquet paths and schemas. DuckDB may expose those files as views and PySpark may load them as DataFrames and temporary views. A generated `.duckdb` file can be provided as a convenience for exploration, but it is not the canonical data source and the Spark executor does not depend on it.

DuckDB's experimental Spark-compatible API is useful for experimentation, but it is not a substitute for testing the required backend on real PySpark. The project will therefore keep DuckDB and PySpark as distinct executors behind the common DSL contract.

The initial structured decision shape is:

```json
{
  "outcome": "APPROVE | REVIEW | REJECT",
  "reason": "machine-readable reason code",
  "action": "optional next action",
  "details": {}
}
```

The exact schema will be typed and versioned during Phase 1.

## First milestone

The first vertical slice should compile equivalent Python and SQL logic to compatible IR and evaluate it against the demo client data using PySpark:

```python
client.age >= 18 and client.account_status == "ACTIVE" and credit.credit_score >= 650
```

```sql
SELECT
    c.client_id,
    CASE
        WHEN c.age >= 18
         AND c.account_status = 'ACTIVE'
         AND cp.credit_score >= 650
        THEN 'APPROVE'
        WHEN cp.credit_score IS NULL THEN 'REVIEW'
        ELSE 'REJECT'
    END AS outcome
FROM clients AS c
LEFT JOIN credit_profiles AS cp ON cp.client_id = c.client_id
```

## Confirmed design decisions

1. SQL input supports full, read-only `SELECT` statements rather than predicates only.
2. Rules return structured decisions rather than booleans only.
3. Null values remain null unless the rule handles them explicitly; unknown fields fail validation.
4. The demo uses synthetic client, income, debt, employment, and credit-score data.
5. PySpark execution is required for the demo implementation.
6. The demo CLI provides `py-to-dsl`, `sql-to-dsl`, and `execute` commands.
7. Parquet fixtures are the shared demo data source; DuckDB and PySpark are separate execution backends.
8. The demo includes a generated DuckDB database and an automated proof that direct source execution and DSL execution produce equivalent outputs.

## Current status

The first end-to-end demo is implemented. It includes:

- deterministic DuckDB and Parquet fixture generation;
- versioned catalogs, schemas, DSL envelopes, and SHA-256 integrity checks;
- the `py-to-dsl`, `sql-to-dsl`, and `execute` CLI commands;
- restricted Python expressions with structured `decision(...)` and `when(...)` values;
- restricted PySpark DataFrame pipelines with catalog sources, aliases, joins, filters, explicit projections, chained `when`/`otherwise`, ordering, and limits;
- SQL `SELECT`, explicit projections, table aliases, joins, filters, comparisons, boolean expressions, `CASE`, basic arithmetic/functions, ordering, and limits;
- DuckDB and real PySpark execution;
- automated rejection of mutation statements, unknown fields, unsupported Python syntax, and modified DSL documents;
- direct SQL and direct PySpark versus DSL equivalence verification.

CTEs, subqueries, aggregation, unions, runtime parameters, production signing, and service-level rule lifecycle management remain planned. Unsupported constructs fail compilation explicitly.
