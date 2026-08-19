from __future__ import annotations

from pathlib import Path
from typing import Any

from .catalog import Catalog
from .dsl import validate_envelope
from .errors import ValidationError
from .executors.duckdb import execute_duckdb
from .executors.spark import execute_spark
from .parsers.python_parser import compile_python
from .parsers.pyspark_parser import compile_pyspark
from .parsers.sql_parser import compile_sql


def sql_to_dsl(source: str, catalog: Catalog, rule_id: str = "sql-rule") -> dict[str, Any]:
    return compile_sql(source, catalog, rule_id)


def py_to_dsl(
    source: str, schema_path: str | Path | None = None, rule_id: str = "python-rule", catalog: Catalog | None = None
) -> dict[str, Any]:
    if catalog is not None:
        return compile_pyspark(source, catalog, rule_id)
    if schema_path is None:
        raise ValidationError("Python compilation requires either schema_path or catalog")
    return compile_python(source, schema_path, rule_id)


def execute(document: dict[str, Any], catalog: Catalog, engine: str) -> dict[str, Any]:
    validate_envelope(document)
    if engine == "duckdb":
        return execute_duckdb(document, catalog)
    if engine == "spark":
        return execute_spark(document, catalog)
    raise ValidationError(f"Unknown execution engine: {engine}")
