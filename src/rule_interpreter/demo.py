from __future__ import annotations

import json
from pathlib import Path

import duckdb

from .api import execute, sql_to_dsl
from .catalog import Catalog
from .result import comparable, make_result

CLIENTS = [
    (1, 34, "PE", "RETAIL", "ACTIVE"),
    (2, 17, "PE", "RETAIL", "ACTIVE"),
    (3, 45, "PE", "PREMIUM", "ACTIVE"),
    (4, 29, "CL", "RETAIL", "INACTIVE"),
    (5, 62, "PE", "PREMIUM", "ACTIVE"),
    (6, 38, "CO", "RETAIL", "ACTIVE"),
]
INCOME = [
    (1, 5200.0, "SALARY", "EMPLOYED", 48),
    (2, None, None, "STUDENT", 0),
    (3, 12000.0, "BUSINESS", "SELF_EMPLOYED", 96),
    (4, 4000.0, "SALARY", "EMPLOYED", 18),
    (5, 8500.0, "PENSION", "RETIRED", 120),
    (6, 3000.0, "SALARY", "EMPLOYED", 8),
]
CREDIT = [
    (1, 720, 1200.0, 0.22, 0, "2026-08-01"),
    (2, None, 0.0, None, 0, None),
    (3, 650, 18000.0, 0.71, 1, "2026-07-15"),
    (4, 690, 3500.0, 0.33, 0, "2026-08-03"),
    (5, 810, 2000.0, 0.10, 0, "2026-08-05"),
    (6, 610, 14000.0, 0.88, 3, "2026-06-20"),
]


def build_demo(root: str | Path) -> dict[str, str]:
    root_path = Path(root).resolve()
    root_path.mkdir(parents=True, exist_ok=True)
    parquet = root_path / "parquet"
    parquet.mkdir(parents=True, exist_ok=True)
    database = root_path / "banking.duckdb"
    if database.exists():
        database.unlink()
    connection = duckdb.connect(str(database))
    try:
        connection.execute("CREATE TABLE clients(client_id BIGINT NOT NULL, age INTEGER NOT NULL, country VARCHAR NOT NULL, customer_segment VARCHAR NOT NULL, account_status VARCHAR NOT NULL)")
        connection.executemany("INSERT INTO clients VALUES (?, ?, ?, ?, ?)", CLIENTS)
        connection.execute("CREATE TABLE income(client_id BIGINT NOT NULL, monthly_income DOUBLE, income_source VARCHAR, employment_status VARCHAR NOT NULL, months_employed INTEGER NOT NULL)")
        connection.executemany("INSERT INTO income VALUES (?, ?, ?, ?, ?)", INCOME)
        connection.execute("CREATE TABLE credit_profiles(client_id BIGINT NOT NULL, credit_score INTEGER, current_debt DOUBLE NOT NULL, credit_utilization DOUBLE, delinquency_count INTEGER NOT NULL, last_score_update DATE)")
        connection.executemany("INSERT INTO credit_profiles VALUES (?, ?, ?, ?, ?, ?)", CREDIT)
        for table in ("clients", "income", "credit_profiles"):
            target = (parquet / f"{table}.parquet").as_posix().replace("'", "''")
            connection.execute(f"COPY {table} TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        connection.close()
    return {"database": str(database), "parquet": str(parquet)}


def verify_demo(root: str | Path, engine: str = "duckdb") -> dict[str, object]:
    root_path = Path(root).resolve()
    build_demo(root_path)
    catalog = Catalog.load(root_path / "catalog.json")
    sql_path = root_path / "rules" / "credit_decisions.sql"
    source = sql_path.read_text(encoding="utf-8")
    dsl = sql_to_dsl(source, catalog, "credit-decisions")
    generated = root_path / "generated"
    generated.mkdir(exist_ok=True)
    (generated / "credit_decisions.dsl.json").write_text(json.dumps(dsl, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    connection = duckdb.connect(str(root_path / "banking.duckdb"), read_only=True)
    try:
        cursor = connection.execute(source)
        direct = make_result("direct-duckdb", [item[0] for item in cursor.description], cursor.fetchall())
    finally:
        connection.close()
    compiled = execute(dsl, catalog, engine)
    matches = comparable(direct) == comparable(compiled)
    return {"matches": matches, "direct": direct, "compiled": compiled, "dsl": str(generated / "credit_decisions.dsl.json")}

