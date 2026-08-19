from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from ..catalog import Catalog
from ..dsl import validate_envelope
from ..errors import ExecutionError, ValidationError
from ..result import make_result
from .sql_renderer import SQLRenderer, quote


def execute_duckdb(document: dict[str, Any], catalog: Catalog) -> dict[str, Any]:
    validate_envelope(document)
    databases: set[Path] = set()
    tables: dict[str, str] = {}
    for item in document["inputs"]:
        source = item["source"]
        definition = catalog.source(source)
        if str(definition.get("schema_version", "1")) != str(item.get("schema_version", "1")):
            raise ValidationError(f"Schema version mismatch for {source}")
        binding = catalog.binding(source, "duckdb")
        if binding.get("kind") != "table" or not binding.get("name") or not binding.get("database"):
            raise ValidationError(f"Invalid DuckDB binding for {source}")
        databases.add(catalog.resolve_path(binding["database"]))
        tables[source] = binding["name"]
    if len(databases) != 1:
        raise ExecutionError("The first DuckDB executor requires all sources in one database")
    database = databases.pop()
    if not database.exists():
        raise ExecutionError(f"DuckDB database does not exist: {database}. Run 'rule-manager build-demo'.")
    renderer = SQLRenderer(lambda source: quote(tables[source]), "duckdb")
    query = renderer.query(document["plan"])
    connection = duckdb.connect(str(database), read_only=True)
    try:
        cursor = connection.execute(query)
        columns = [item[0] for item in cursor.description]
        return make_result("duckdb", columns, cursor.fetchall())
    except duckdb.Error as exc:
        raise ExecutionError(f"DuckDB execution failed: {exc}") from exc
    finally:
        connection.close()

