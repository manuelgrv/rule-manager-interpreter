from __future__ import annotations

import ast
from typing import Any

from ..catalog import Catalog
from ..dsl import create_envelope
from ..errors import ValidationError


COMPARE = {ast.Eq: "eq", ast.NotEq: "neq", ast.Gt: "gt", ast.GtE: "gte", ast.Lt: "lt", ast.LtE: "lte"}
ARITHMETIC = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul", ast.Div: "div"}


class PySparkCompiler:
    """Compile a deliberately restricted PySpark DataFrame pipeline without executing it."""

    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.aliases: dict[str, str] = {}

    def compile(self, source: str, rule_id: str) -> dict[str, Any]:
        try:
            module = ast.parse(source, mode="exec")
        except SyntaxError as exc:
            raise ValidationError(f"Invalid PySpark Python at line {exc.lineno}: {exc.msg}") from exc
        if len(module.body) != 1 or not isinstance(module.body[0], ast.FunctionDef):
            raise ValidationError("PySpark rule files must contain exactly one function")
        function = module.body[0]
        if function.decorator_list or len(function.body) != 1 or not isinstance(function.body[0], ast.Return):
            raise ValidationError("The PySpark rule function must contain exactly one return statement")
        arguments = {argument.arg for argument in function.args.args}
        allowed = set(self.catalog.sources) | {"F"}
        if not arguments.issubset(allowed) or "F" not in arguments:
            raise ValidationError("PySpark function arguments must be catalog sources plus F")
        plan = self._plan(function.body[0].value)
        if plan.get("op") not in {"project", "sort", "limit"}:
            raise ValidationError("PySpark pipeline must end with select()")
        output_schema = self._output_schema(plan)
        sources = self._sources(plan)
        inputs = [{"source": name, "schema_version": self.catalog.source(name).get("schema_version", "1")} for name in sources]
        return create_envelope(rule_id=rule_id, source_language="pyspark", inputs=inputs, plan=plan, output_schema=output_schema)

    def _plan(self, node: ast.AST) -> dict[str, Any]:
        if isinstance(node, ast.Name) and node.id in self.catalog.sources:
            self.catalog.source(node.id)
            self.aliases.setdefault(node.id, node.id)
            return {"op": "scan", "source": node.id, "alias": node.id}
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            raise self._unsupported(node, "PySpark plan")
        method = node.func.attr
        if method == "alias" and len(node.args) == 1:
            base = self._plan(node.func.value)
            if base["op"] != "scan":
                raise ValidationError("alias() is supported only directly on source DataFrames")
            alias = self._string(node.args[0], "DataFrame alias")
            if alias in self.aliases and self.aliases[alias] != base["source"]:
                raise ValidationError(f"Duplicate DataFrame alias: {alias}")
            self.aliases.pop(base["alias"], None)
            self.aliases[alias] = base["source"]
            return {**base, "alias": alias}
        if method == "join" and 2 <= len(node.args) <= 3:
            left = self._plan(node.func.value)
            right = self._plan(node.args[0])
            join_type = self._string(node.args[2], "join type") if len(node.args) == 3 else "inner"
            join_type = {"outer": "full", "full_outer": "full", "left_outer": "left", "right_outer": "right"}.get(join_type, join_type)
            if join_type not in {"inner", "left", "right", "full"}:
                raise ValidationError(f"Unsupported PySpark join type: {join_type}")
            return {"op": "join", "join_type": join_type, "left": left, "right": right, "condition": self._expr(node.args[1])}
        if method in {"filter", "where"} and len(node.args) == 1:
            return {"op": "filter", "input": self._plan(node.func.value), "condition": self._expr(node.args[0])}
        if method == "select" and node.args:
            input_plan = self._plan(node.func.value)
            columns = []
            for argument in node.args:
                if not isinstance(argument, ast.Call) or not isinstance(argument.func, ast.Attribute) or argument.func.attr != "alias" or len(argument.args) != 1:
                    raise ValidationError("Every select() expression must have an explicit alias()")
                columns.append({"name": self._string(argument.args[0], "column alias"), "value": self._expr(argument.func.value)})
            return {"op": "project", "input": input_plan, "columns": columns}
        if method in {"orderBy", "sort"} and node.args:
            input_plan = self._plan(node.func.value)
            keys = []
            output_names = set(self._project_columns(input_plan))
            for argument in node.args:
                direction = "asc"
                value_node = argument
                if isinstance(argument, ast.Call) and isinstance(argument.func, ast.Attribute) and argument.func.attr in {"asc", "desc", "asc_nulls_first", "asc_nulls_last", "desc_nulls_first", "desc_nulls_last"}:
                    direction = "desc" if argument.func.attr.startswith("desc") else "asc"
                    nulls = "first" if argument.func.attr.endswith("first") else "last"
                    value_node = argument.func.value
                else:
                    nulls = "last"
                value = self._expr(value_node)
                if value.get("expr") == "column" and not value.get("relation") and value["name"] in output_names:
                    value = {"expr": "output", "name": value["name"]}
                elif value.get("expr") != "output":
                    raise ValidationError("orderBy() columns must be projected output columns")
                keys.append({"value": value, "direction": direction, "nulls": nulls})
            return {"op": "sort", "input": input_plan, "keys": keys}
        if method == "limit" and len(node.args) == 1 and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, int):
            return {"op": "limit", "input": self._plan(node.func.value), "count": node.args[0].value}
        raise ValidationError(f"Unsupported PySpark DataFrame method at line {node.lineno}: {method}")

    def _expr(self, node: ast.AST) -> dict[str, Any]:
        if isinstance(node, ast.Constant):
            return self._literal(node.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitAnd, ast.BitOr)):
            return {"expr": "boolean", "operator": "and" if isinstance(node.op, ast.BitAnd) else "or", "operands": [self._expr(node.left), self._expr(node.right)], "type": "boolean"}
        if isinstance(node, ast.BinOp) and type(node.op) in ARITHMETIC:
            return {"expr": "binary", "operator": ARITHMETIC[type(node.op)], "left": self._expr(node.left), "right": self._expr(node.right), "type": "float64"}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
            return {"expr": "not", "operand": self._expr(node.operand), "type": "boolean"}
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1 and type(node.ops[0]) in COMPARE:
            return {"expr": "compare", "operator": COMPARE[type(node.ops[0])], "left": self._expr(node.left), "right": self._expr(node.comparators[0]), "type": "boolean"}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "F":
                if node.func.attr == "col" and len(node.args) == 1:
                    return self._column(self._string(node.args[0], "column name"))
                if node.func.attr == "lit" and len(node.args) == 1 and isinstance(node.args[0], ast.Constant):
                    return self._literal(node.args[0].value)
                if node.func.attr in {"coalesce", "lower", "upper", "abs"} and node.args:
                    arguments = [self._expr(argument) for argument in node.args]
                    return {"expr": "call", "function": node.func.attr, "arguments": arguments, "type": arguments[0].get("type", "unknown")}
                if node.func.attr == "when" and len(node.args) == 2:
                    return {"expr": "case", "branches": [{"when": self._expr(node.args[0]), "then": self._expr(node.args[1])}], "else": self._literal(None), "type": self._expr(node.args[1]).get("type", "unknown")}
            if node.func.attr in {"isNull", "isNotNull"} and not node.args:
                value = {"expr": "is_null", "value": self._expr(node.func.value), "type": "boolean"}
                return {"expr": "not", "operand": value, "type": "boolean"} if node.func.attr == "isNotNull" else value
            if node.func.attr == "when" and len(node.args) == 2:
                case = self._expr(node.func.value)
                if case.get("expr") != "case":
                    raise self._unsupported(node, "when chain")
                return {**case, "branches": [*case["branches"], {"when": self._expr(node.args[0]), "then": self._expr(node.args[1])}]}
            if node.func.attr == "otherwise" and len(node.args) == 1:
                case = self._expr(node.func.value)
                if case.get("expr") != "case":
                    raise self._unsupported(node, "otherwise chain")
                return {**case, "else": self._expr(node.args[0])}
        raise self._unsupported(node, "PySpark expression")

    def _column(self, reference: str) -> dict[str, Any]:
        if "." in reference:
            relation, name = reference.split(".", 1)
            if relation not in self.aliases:
                raise ValidationError(f"Unknown PySpark relation alias: {relation}")
            source = self.aliases[relation]
        else:
            relation, name = "", reference
            matches = [source for source in self.aliases.values() if name in self.catalog.columns(source)]
            if len(matches) == 1:
                source = matches[0]
            else:
                # Unqualified names after select() refer to output columns and are resolved by orderBy().
                return {"expr": "column", "relation": "", "name": name, "type": "unknown", "nullable": True}
        field = self.catalog.columns(source).get(name)
        if field is None:
            raise ValidationError(f"Unknown PySpark column: {reference}")
        return {"expr": "column", "relation": relation, "name": name, "type": field["type"], "nullable": field.get("nullable", True)}

    @staticmethod
    def _literal(value: Any) -> dict[str, Any]:
        kind = "null" if value is None else "boolean" if isinstance(value, bool) else "int64" if isinstance(value, int) else "float64" if isinstance(value, float) else "string" if isinstance(value, str) else None
        if kind is None:
            raise ValidationError(f"Unsupported PySpark literal: {value!r}")
        return {"expr": "literal", "type": kind, "value": value}

    @staticmethod
    def _string(node: ast.AST, label: str) -> str:
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            raise ValidationError(f"{label} must be a string literal")
        return node.value

    @staticmethod
    def _unsupported(node: ast.AST, label: str) -> ValidationError:
        return ValidationError(f"Unsupported {label} at line {getattr(node, 'lineno', '?')}: {type(node).__name__}")

    @staticmethod
    def _project_columns(plan: dict[str, Any]) -> list[str]:
        current = plan
        while current["op"] in {"sort", "limit"}:
            current = current["input"]
        return [column["name"] for column in current.get("columns", [])] if current["op"] == "project" else []

    def _output_schema(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        current = plan
        while current["op"] in {"sort", "limit"}:
            current = current["input"]
        if current["op"] != "project":
            raise ValidationError("PySpark pipeline has no select() output")
        return [{"name": column["name"], "type": column["value"].get("type", "unknown"), "nullable": True} for column in current["columns"]]

    @staticmethod
    def _sources(plan: dict[str, Any]) -> list[str]:
        found: list[str] = []

        def visit(node: dict[str, Any]) -> None:
            if node["op"] == "scan":
                if node["source"] not in found:
                    found.append(node["source"])
            elif node["op"] == "join":
                visit(node["left"])
                visit(node["right"])
            elif "input" in node:
                visit(node["input"])

        visit(plan)
        return found


def compile_pyspark(source: str, catalog: Catalog, rule_id: str) -> dict[str, Any]:
    return PySparkCompiler(catalog).compile(source, rule_id)

