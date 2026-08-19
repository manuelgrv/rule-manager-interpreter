from pathlib import Path

import pytest

from rule_interpreter.api import execute, sql_to_dsl
from rule_interpreter.catalog import Catalog
from rule_interpreter.demo import build_demo, verify_demo
from rule_interpreter.errors import ValidationError


ROOT = Path(__file__).parents[1]


def test_sql_source_and_duckdb_dsl_are_equivalent(tmp_path: Path) -> None:
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "catalog.json").write_text((ROOT / "demo/catalog.json").read_text())
    rules = demo / "rules"
    rules.mkdir()
    (rules / "credit_decisions.sql").write_text((ROOT / "demo/rules/credit_decisions.sql").read_text())
    result = verify_demo(demo)
    assert result["matches"] is True
    assert result["compiled"]["row_count"] == 6


def test_sql_compiler_rejects_mutation(tmp_path: Path) -> None:
    build_demo(ROOT / "demo")
    catalog = Catalog.load(ROOT / "demo/catalog.json")
    with pytest.raises(ValidationError, match="read-only SELECT"):
        sql_to_dsl("DELETE FROM clients", catalog)


def test_dsl_integrity_is_checked() -> None:
    build_demo(ROOT / "demo")
    catalog = Catalog.load(ROOT / "demo/catalog.json")
    document = sql_to_dsl((ROOT / "demo/rules/credit_decisions.sql").read_text(), catalog)
    document["rule"]["id"] = "tampered"
    with pytest.raises(ValidationError, match="integrity"):
        execute(document, catalog, "duckdb")
