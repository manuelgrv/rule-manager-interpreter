from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
from typing import Any


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if dataclasses.is_dataclass(value):
        return {key: json_value(item) for key, item in dataclasses.asdict(value).items()}
    if hasattr(value, "asDict"):
        return {key: json_value(item) for key, item in value.asDict(recursive=True).items()}
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return str(value)


def make_result(engine: str, columns: list[str], rows: list[Any]) -> dict[str, Any]:
    return {"engine": engine, "columns": columns, "rows": [[json_value(value) for value in row] for row in rows], "row_count": len(rows)}


def comparable(result: dict[str, Any]) -> dict[str, Any]:
    return {"columns": result["columns"], "rows": result["rows"], "row_count": result["row_count"]}

