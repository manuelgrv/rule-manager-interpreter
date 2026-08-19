from __future__ import annotations

from typing import Any

import sqlglot
from sqlglot import exp

from ..catalog import Catalog
from ..dsl import create_envelope
from ..errors import ValidationError


COMPARE = {exp.EQ: "eq", exp.NEQ: "neq", exp.GT: "gt", exp.GTE: "gte", exp.LT: "lt", exp.LTE: "lte"}
ARITHMETIC = {exp.Add: "add", exp.Sub: "sub", exp.Mul: "mul", exp.Div: "div"}
FUNCTIONS = {"COALESCE": "coalesce", "LOWER": "lower", "UPPER": "upper", "ABS": "abs"}


class SQLCompiler:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.aliases: dict[str, str] = {}

    def compile(self, source: str, rule_id: str) -> dict[str, Any]:
        try:
            statements = sqlglot.parse(source, read="duckdb")
        except sqlglot.errors.ParseError as exc:
            raise ValidationError(f"Invalid SQL: {exc}") from exc
        if len(statements) != 1 or not isinstance(statements[0], exp.Select):
            raise ValidationError("Exactly one read-only SELECT statement is required")
        query = statements[0]
        if query.args.get("with_") is not None or query.args.get("group") is not None or query.args.get("having") is not None:
            raise ValidationError("CTEs and aggregation are planned but not implemented in the first slice")

        from_clause = query.args.get("from_")
        if from_clause is None or not isinstance(from_clause.this, exp.Table):
            raise ValidationError("SELECT must read from one catalog table")
        plan = self._scan(from_clause.this)
        for join in query.args.get("joins") or []:
            if not isinstance(join.this, exp.Table) or join.args.get("on") is None:
                raise ValidationError("Only catalog-table joins with an ON condition are supported")
            side = (join.args.get("side") or "inner").lower()
            if side not in {"inner", "left", "right", "full"}:
                raise ValidationError(f"Unsupported join type: {side}")
            plan = {"op": "join", "join_type": side, "left": plan, "right": self._scan(join.this), "condition": self._expr(join.args["on"])}
        where = query.args.get("where")
        if where is not None:
            plan = {"op": "filter", "input": plan, "condition": self._expr(where.this)}

        columns = []
        output_schema = []
        for index, projection in enumerate(query.expressions):
            if isinstance(projection, exp.Star):
                raise ValidationError("SELECT * is not supported; output columns must be explicit")
            value_node = projection.this if isinstance(projection, exp.Alias) else projection
            name = projection.alias_or_name or f"column_{index + 1}"
            value = self._expr(value_node)
            columns.append({"name": name, "value": value})
            output_schema.append({"name": name, "type": value.get("type", "unknown"), "nullable": True})
        plan = {"op": "project", "input": plan, "columns": columns}

        order = query.args.get("order")
        if order is not None:
            keys = []
            for ordered in order.expressions:
                output_name = next(
                    (column["name"] for column, projection in zip(columns, query.expressions, strict=True) if (projection.this if isinstance(projection, exp.Alias) else projection) == ordered.this),
                    ordered.this.name if isinstance(ordered.this, exp.Column) and not ordered.this.table and ordered.this.name in {column["name"] for column in columns} else None,
                )
                if output_name is None:
                    raise ValidationError("ORDER BY expressions must appear in the SELECT output in the first slice")
                keys.append({"value": {"expr": "output", "name": output_name}, "direction": "desc" if ordered.args.get("desc") else "asc", "nulls": "first" if ordered.args.get("nulls_first") else "last"})
            plan = {"op": "sort", "input": plan, "keys": keys}
        limit = query.args.get("limit")
        if limit is not None:
            if not isinstance(limit.expression, exp.Literal) or limit.expression.is_string:
                raise ValidationError("LIMIT must be an integer literal")
            plan = {"op": "limit", "input": plan, "count": int(limit.expression.this)}

        inputs = [{"source": name, "schema_version": self.catalog.source(name).get("schema_version", "1")} for name in dict.fromkeys(self.aliases.values())]
        return create_envelope(rule_id=rule_id, source_language="sql", inputs=inputs, plan=plan, output_schema=output_schema)

    def _scan(self, table: exp.Table) -> dict[str, Any]:
        if table.db or table.catalog:
            raise ValidationError("Catalog and schema qualification are not allowed")
        source = table.name
        self.catalog.source(source)
        alias = table.alias_or_name
        if alias in self.aliases:
            raise ValidationError(f"Duplicate relation alias: {alias}")
        self.aliases[alias] = source
        return {"op": "scan", "source": source, "alias": alias}

    def _column(self, node: exp.Column) -> dict[str, Any]:
        relation = node.table
        if relation:
            if relation not in self.aliases:
                raise ValidationError(f"Unknown relation alias: {relation}")
            source = self.aliases[relation]
        else:
            matches = [source for source in self.aliases.values() if node.name in self.catalog.columns(source)]
            if len(matches) != 1:
                raise ValidationError(f"Column {node.name!r} is unknown or ambiguous")
            source = matches[0]
            relation = next(alias for alias, candidate in self.aliases.items() if candidate == source)
        column = self.catalog.columns(source).get(node.name)
        if column is None:
            raise ValidationError(f"Unknown column: {relation}.{node.name}")
        return {"expr": "column", "relation": relation, "name": node.name, "type": column["type"], "nullable": column.get("nullable", True)}

    def _expr(self, node: exp.Expression) -> dict[str, Any]:
        if isinstance(node, exp.Column):
            return self._column(node)
        if isinstance(node, exp.Null):
            return {"expr": "literal", "type": "null", "value": None}
        if isinstance(node, exp.Boolean):
            return {"expr": "literal", "type": "boolean", "value": bool(node.this)}
        if isinstance(node, exp.Literal):
            if node.is_string:
                return {"expr": "literal", "type": "string", "value": node.this}
            value = float(node.this) if "." in node.this else int(node.this)
            return {"expr": "literal", "type": "float64" if isinstance(value, float) else "int64", "value": value}
        for cls, operator in COMPARE.items():
            if isinstance(node, cls):
                return {"expr": "compare", "operator": operator, "left": self._expr(node.this), "right": self._expr(node.expression), "type": "boolean"}
        for cls, operator in ARITHMETIC.items():
            if isinstance(node, cls):
                return {"expr": "binary", "operator": operator, "left": self._expr(node.this), "right": self._expr(node.expression), "type": "float64"}
        if isinstance(node, (exp.And, exp.Or)):
            return {"expr": "boolean", "operator": "and" if isinstance(node, exp.And) else "or", "operands": [self._expr(node.this), self._expr(node.expression)], "type": "boolean"}
        if isinstance(node, exp.Not):
            return {"expr": "not", "operand": self._expr(node.this), "type": "boolean"}
        if isinstance(node, exp.Is) and isinstance(node.expression, exp.Null):
            return {"expr": "is_null", "value": self._expr(node.this), "type": "boolean"}
        if isinstance(node, exp.Case):
            branches = [{"when": self._expr(item.this), "then": self._expr(item.args["true"])} for item in node.args.get("ifs") or []]
            default = self._expr(node.args["default"]) if node.args.get("default") is not None else {"expr": "literal", "type": "null", "value": None}
            inferred = next((branch["then"].get("type") for branch in branches if branch["then"].get("type") != "null"), default.get("type", "unknown"))
            return {"expr": "case", "branches": branches, "else": default, "type": inferred}
        if isinstance(node, exp.Func):
            name = node.sql_name().upper()
            if name not in FUNCTIONS:
                raise ValidationError(f"Unsupported SQL function: {name}")
            args = [self._expr(arg) for arg in node.expressions]
            if node.this is not None and not isinstance(node.this, str) and not args:
                args = [self._expr(node.this)]
            return {"expr": "call", "function": FUNCTIONS[name], "arguments": args, "type": args[0].get("type", "unknown") if args else "unknown"}
        if isinstance(node, exp.Paren):
            return self._expr(node.this)
        raise ValidationError(f"Unsupported SQL expression: {node.key} ({node.sql()})")


def compile_sql(source: str, catalog: Catalog, rule_id: str) -> dict[str, Any]:
    return SQLCompiler(catalog).compile(source, rule_id)
