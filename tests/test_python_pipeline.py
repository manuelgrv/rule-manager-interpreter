from pathlib import Path

import pytest

from rule_interpreter.api import execute, py_to_dsl
from rule_interpreter.catalog import Catalog
from rule_interpreter.demo import build_demo
from rule_interpreter.errors import ValidationError


ROOT = Path(__file__).parents[1]


def test_python_rule_compiles_and_executes() -> None:
    build_demo(ROOT / "demo")
    document = py_to_dsl((ROOT / "demo/rules/client_status.py").read_text(), ROOT / "demo/client_schema.json")
    result = execute(document, Catalog.load(ROOT / "demo/catalog.json"), "duckdb")
    assert result["row_count"] == 6
    assert result["rows"][0][1]["outcome"] == "APPROVE"
    assert result["rows"][1][1]["reason"] == "UNDERAGE"


def test_python_rule_rejects_imports() -> None:
    with pytest.raises(ValidationError, match="exactly one expression"):
        py_to_dsl("import os\nos.system('echo unsafe')", ROOT / "demo/client_schema.json")
