from __future__ import annotations

import os
from typing import Any

from ..catalog import Catalog
from ..dsl import validate_envelope
from ..errors import ExecutionError, ValidationError
from ..result import make_result
from .sql_renderer import SQLRenderer, quote


def execute_spark(document: dict[str, Any], catalog: Catalog) -> dict[str, Any]:
    validate_envelope(document)
    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:
        raise ExecutionError("PySpark is not installed") from exc
    java_home = "/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
    if "JAVA_HOME" not in os.environ and os.path.exists(java_home):
        os.environ["JAVA_HOME"] = java_home
    spark = SparkSession.builder.master("local[1]").appName("rule-manager-demo").config("spark.ui.enabled", "false").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    try:
        for item in document["inputs"]:
            source = item["source"]
            definition = catalog.source(source)
            if str(definition.get("schema_version", "1")) != str(item.get("schema_version", "1")):
                raise ValidationError(f"Schema version mismatch for {source}")
            binding = catalog.binding(source, "spark")
            if binding.get("kind") != "parquet" or not binding.get("path"):
                raise ValidationError(f"Invalid Spark binding for {source}")
            path = catalog.resolve_path(binding["path"])
            if not path.exists():
                raise ExecutionError(f"Parquet source does not exist: {path}. Run 'rule-manager build-demo'.")
            spark.read.parquet(str(path)).createOrReplaceTempView(source)
        renderer = SQLRenderer(lambda source: quote(source, "spark"), "spark")
        frame = spark.sql(renderer.query(document["plan"]))
        return make_result("spark", frame.columns, [tuple(row) for row in frame.collect()])
    except ExecutionError:
        raise
    except Exception as exc:
        raise ExecutionError(f"Spark execution failed: {exc}") from exc
    finally:
        spark.stop()
