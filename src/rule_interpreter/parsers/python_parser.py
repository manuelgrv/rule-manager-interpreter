from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from ..dsl import create_envelope
from ..errors import ValidationError
from ..io import read_json


COMPARE = {ast.Eq: "eq", ast.NotEq: "neq", ast.Gt: "gt", ast.GtE: "gte", ast.Lt: "lt", ast.LtE: "lte", ast.In: "in", ast.NotIn: "not_in"}
ARITHMETIC = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul", ast.Div: "div"}


class PythonCompiler:
    def __init__(self, schema: dict[str, Any]):
        self.schema = schema
        self.source = schema.get("source")
        self.alias = schema.get("alias")
        self.fields = {field["name"]: field for field in schema.get("schema", [])}
        if not self.source or not self.alias or not self.fields:
            raise ValidationError("Python schema requires source, alias, and a non-empty schema")

    def compile(self, source: str, rule_id: str) -> dict[str, Any]:
        try:
            module = ast.parse(source, mode="exec")
        except SyntaxError as exc:
            raise ValidationError(f"Invalid Python at line {exc.lineno}: {exc.msg}") from exc
        if len(module.body) != 1 or not isinstance(module.body[0], ast.Expr):
            raise ValidationError("Python rule files must contain exactly one expression")
        value = self._expr(module.body[0].value)
        identities = self.schema.get("identity", [])
        columns = []
        output_schema = []
        for name in identities:
            field = self.fields.get(name)
            if field is None:
                raise ValidationError(f"Unknown identity field: {name}")
            columns.append({"name": name, "value": self._column(name)})
            output_schema.append({"name": name, "type": field["type"], "nullable": field.get("nullable", True)})
        columns.append({"name": "decision", "value": value})
        output_schema.append({"name": "decision", "type": value.get("type", "unknown"), "nullable": False})
        plan = {"op": "project", "input": {"op": "scan", "source": self.source, "alias": self.alias}, "columns": columns}
        inputs = [{"source": self.source, "schema_version": self.schema.get("schema_version", "1")}]
        return create_envelope(rule_id=rule_id, source_language="python", inputs=inputs, plan=plan, output_schema=output_schema)

    def _column(self, name: str) -> dict[str, Any]:
        field = self.fields[name]
        return {"expr": "column", "relation": self.alias, "name": name, "type": field["type"], "nullable": field.get("nullable", True)}

    def _expr(self, node: ast.AST) -> dict[str, Any]:
        if isinstance(node, ast.Constant):
            value = node.value
            kind = "null" if value is None else "boolean" if isinstance(value, bool) else "int64" if isinstance(value, int) else "float64" if isinstance(value, float) else "string" if isinstance(value, str) else None
            if kind is None:
                raise ValidationError(f"Unsupported Python literal at line {node.lineno}")
            return {"expr": "literal", "type": kind, "value": value}
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == self.alias:
            if node.attr not in self.fields:
                raise ValidationError(f"Unknown field: {self.alias}.{node.attr}")
            return self._column(node.attr)
        if isinstance(node, ast.BoolOp):
            return {"expr": "boolean", "operator": "and" if isinstance(node.op, ast.And) else "or", "operands": [self._expr(value) for value in node.values], "type": "boolean"}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return {"expr": "not", "operand": self._expr(node.operand), "type": "boolean"}
        if isinstance(node, ast.BinOp) and type(node.op) in ARITHMETIC:
            return {"expr": "binary", "operator": ARITHMETIC[type(node.op)], "left": self._expr(node.left), "right": self._expr(node.right), "type": "float64"}
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
            left, right = self._expr(node.left), self._expr(node.comparators[0])
            if isinstance(node.ops[0], (ast.Is, ast.IsNot)) and right.get("value", object()) is None:
                expression = {"expr": "is_null", "value": left, "type": "boolean"}
                return {"expr": "not", "operand": expression, "type": "boolean"} if isinstance(node.ops[0], ast.IsNot) else expression
            operator = COMPARE.get(type(node.ops[0]))
            if operator is None:
                raise ValidationError(f"Unsupported comparison at line {node.lineno}")
            return {"expr": "compare", "operator": operator, "left": left, "right": right, "type": "boolean"}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name == "when" and len(node.args) == 3 and not node.keywords:
                true_value, false_value = self._expr(node.args[1]), self._expr(node.args[2])
                return {"expr": "case", "branches": [{"when": self._expr(node.args[0]), "then": true_value}], "else": false_value, "type": true_value.get("type", false_value.get("type", "unknown"))}
            if name in {"coalesce", "lower", "upper", "abs"} and node.args and not node.keywords:
                args = [self._expr(arg) for arg in node.args]
                return {"expr": "call", "function": name, "arguments": args, "type": args[0].get("type", "unknown")}
            if name == "decision" and not node.args:
                values = {keyword.arg: self._expr(keyword.value) for keyword in node.keywords if keyword.arg}
                required = {"outcome", "reason"}
                if not required.issubset(values) or set(values) - {"outcome", "reason", "action"}:
                    raise ValidationError("decision() requires outcome and reason and accepts optional action")
                values.setdefault("action", {"expr": "literal", "type": "string", "value": None})
                values["details"] = {"expr": "struct", "fields": {}}
                return {"expr": "decision", **values, "type": "decision"}
        raise ValidationError(f"Unsupported Python syntax at line {getattr(node, 'lineno', '?')}: {type(node).__name__}")


def compile_python(source: str, schema_path: str | Path, rule_id: str) -> dict[str, Any]:
    return PythonCompiler(read_json(schema_path)).compile(source, rule_id)

