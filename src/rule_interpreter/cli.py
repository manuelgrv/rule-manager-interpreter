from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .api import execute, py_to_dsl, sql_to_dsl
from .catalog import Catalog
from .demo import build_demo, verify_demo
from .errors import RuleError
from .io import read_json, write_json


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="rule-manager", description="Compile safe Python/SQL rules to DSL and execute them")
    commands = root.add_subparsers(dest="command", required=True)

    py = commands.add_parser("py-to-dsl", help="compile a restricted Python expression or PySpark pipeline")
    py.add_argument("source")
    py_input = py.add_mutually_exclusive_group(required=True)
    py_input.add_argument("--schema", help="schema for a scalar Python expression rule")
    py_input.add_argument("--catalog", help="catalog for a PySpark DataFrame pipeline")
    py.add_argument("--output", "-o")
    py.add_argument("--rule-id")

    sql = commands.add_parser("sql-to-dsl", help="compile a read-only SQL SELECT file")
    sql.add_argument("source")
    sql.add_argument("--catalog", required=True)
    sql.add_argument("--output", "-o")
    sql.add_argument("--rule-id")

    run = commands.add_parser("execute", help="execute a validated DSL document")
    run.add_argument("dsl")
    run.add_argument("--engine", required=True, choices=("duckdb", "spark"))
    run.add_argument("--catalog", required=True)
    run.add_argument("--output", "-o")

    build = commands.add_parser("build-demo", help="generate the DuckDB and Parquet demo data")
    build.add_argument("--root", default="demo")

    verify = commands.add_parser("verify-demo", help="prove direct SQL and DSL execution are equivalent")
    verify.add_argument("--root", default="demo")
    verify.add_argument("--engine", choices=("duckdb", "spark"), default="duckdb")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "py-to-dsl":
            path = Path(args.source)
            document = py_to_dsl(
                path.read_text(encoding="utf-8"),
                schema_path=args.schema,
                catalog=Catalog.load(args.catalog) if args.catalog else None,
                rule_id=args.rule_id or path.stem,
            )
            write_json(document, args.output)
        elif args.command == "sql-to-dsl":
            path = Path(args.source)
            document = sql_to_dsl(path.read_text(encoding="utf-8"), Catalog.load(args.catalog), args.rule_id or path.stem)
            write_json(document, args.output)
        elif args.command == "execute":
            write_json(execute(read_json(args.dsl), Catalog.load(args.catalog), args.engine), args.output)
        elif args.command == "build-demo":
            write_json(build_demo(args.root))
        elif args.command == "verify-demo":
            result = verify_demo(args.root, args.engine)
            write_json(result)
            return 0 if result["matches"] else 1
        return 0
    except (RuleError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
