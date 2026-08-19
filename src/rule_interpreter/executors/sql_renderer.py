from __future__ import annotations

from typing import Any, Callable

from ..errors import ExecutionError


def quote(name: str, dialect: str = "duckdb") -> str:
    if dialect == "spark":
        return "`" + name.replace("`", "``") + "`"
    return '"' + name.replace('"', '""') + '"'


class SQLRenderer:
    def __init__(self, resolve_source: Callable[[str], str], dialect: str):
        self.resolve_source = resolve_source
        self.dialect = dialect

    def query(self, plan: dict[str, Any]) -> str:
        limit = None
        order = None
        project = None
        current = plan
        if current["op"] == "limit":
            limit, current = current["count"], current["input"]
        if current["op"] == "sort":
            order, current = current["keys"], current["input"]
        if current["op"] != "project":
            raise ExecutionError("A query plan must end in project")
        project, current = current["columns"], current["input"]
        where = None
        if current["op"] == "filter":
            where, current = current["condition"], current["input"]
        select = ", ".join(f"{self.expr(item['value'])} AS {quote(item['name'], self.dialect)}" for item in project)
        sql = f"SELECT {select} FROM {self.from_plan(current)}"
        if where is not None:
            sql += f" WHERE {self.expr(where)}"
        if order:
            sql += " ORDER BY " + ", ".join(f"{self.expr(key['value'])} {key['direction'].upper()} NULLS {key['nulls'].upper()}" for key in order)
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        return sql

    def from_plan(self, plan: dict[str, Any]) -> str:
        if plan["op"] == "scan":
            return f"{self.resolve_source(plan['source'])} AS {quote(plan['alias'], self.dialect)}"
        if plan["op"] == "join":
            join_type = {"inner": "INNER", "left": "LEFT", "right": "RIGHT", "full": "FULL"}.get(plan["join_type"])
            if not join_type:
                raise ExecutionError(f"Unsupported join: {plan['join_type']}")
            return f"{self.from_plan(plan['left'])} {join_type} JOIN {self.from_plan(plan['right'])} ON {self.expr(plan['condition'])}"
        raise ExecutionError(f"Unsupported FROM plan node: {plan['op']}")

    def expr(self, node: dict[str, Any]) -> str:
        kind = node["expr"]
        if kind == "column":
            return f"{quote(node['relation'], self.dialect)}.{quote(node['name'], self.dialect)}"
        if kind == "output":
            return quote(node["name"], self.dialect)
        if kind == "literal":
            value = node.get("value")
            if value is None:
                return "NULL"
            if isinstance(value, bool):
                return "TRUE" if value else "FALSE"
            if isinstance(value, (int, float)):
                return str(value)
            return "'" + str(value).replace("'", "''") + "'"
        if kind == "compare":
            op = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "in": "IN", "not_in": "NOT IN"}[node["operator"]]
            return f"({self.expr(node['left'])} {op} {self.expr(node['right'])})"
        if kind == "binary":
            op = {"add": "+", "sub": "-", "mul": "*", "div": "/"}[node["operator"]]
            return f"({self.expr(node['left'])} {op} {self.expr(node['right'])})"
        if kind == "boolean":
            return "(" + f" {node['operator'].upper()} ".join(self.expr(value) for value in node["operands"]) + ")"
        if kind == "not":
            return f"(NOT {self.expr(node['operand'])})"
        if kind == "is_null":
            return f"({self.expr(node['value'])} IS NULL)"
        if kind == "case":
            branches = " ".join(f"WHEN {self.expr(branch['when'])} THEN {self.expr(branch['then'])}" for branch in node["branches"])
            return f"CASE {branches} ELSE {self.expr(node['else'])} END"
        if kind == "call":
            function = {"coalesce": "COALESCE", "lower": "LOWER", "upper": "UPPER", "abs": "ABS"}[node["function"]]
            return f"{function}({', '.join(self.expr(arg) for arg in node['arguments'])})"
        if kind in {"decision", "struct"}:
            fields = node.get("fields") if kind == "struct" else {name: node[name] for name in ("outcome", "reason", "action", "details")}
            if not fields:
                return "map()"
            if self.dialect == "spark":
                args = ", ".join(f"'{name}', {self.expr(value)}" for name, value in fields.items())
                return f"named_struct({args})"
            args = ", ".join(f"{quote(name, self.dialect)} := {self.expr(value)}" for name, value in fields.items())
            return f"struct_pack({args})"
        raise ExecutionError(f"Unsupported expression node: {kind}")
