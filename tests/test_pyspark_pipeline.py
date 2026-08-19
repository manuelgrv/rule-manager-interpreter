from pathlib import Path

import pytest

from rule_interpreter.api import execute, py_to_dsl, sql_to_dsl
from rule_interpreter.catalog import Catalog
from rule_interpreter.demo import build_demo
from rule_interpreter.errors import ValidationError
from rule_interpreter.result import comparable


ROOT = Path(__file__).parents[1]


def test_pyspark_and_sql_compile_to_equivalent_results() -> None:
    build_demo(ROOT / "demo")
    catalog = Catalog.load(ROOT / "demo/catalog.json")
    pyspark_dsl = py_to_dsl(
        (ROOT / "demo/rules/credit_decisions_pyspark.py").read_text(),
        catalog=catalog,
        rule_id="credit-decisions-pyspark",
    )
    sql_dsl = sql_to_dsl(
        (ROOT / "demo/rules/credit_decisions.sql").read_text(),
        catalog,
        rule_id="credit-decisions-sql",
    )
    assert pyspark_dsl["rule"]["source_language"] == "pyspark"
    assert comparable(execute(pyspark_dsl, catalog, "duckdb")) == comparable(execute(sql_dsl, catalog, "duckdb"))


def test_pyspark_compiler_rejects_arbitrary_code() -> None:
    catalog = Catalog.load(ROOT / "demo/catalog.json")
    with pytest.raises(ValidationError, match="exactly one function"):
        py_to_dsl("import os\nos.system('echo unsafe')", catalog=catalog)
