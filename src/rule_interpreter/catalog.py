from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .io import read_json


@dataclass(frozen=True)
class Catalog:
    document: dict[str, Any]
    path: Path

    @classmethod
    def load(cls, path: str | Path) -> "Catalog":
        catalog_path = Path(path).resolve()
        document = read_json(catalog_path)
        if document.get("catalog_version") != "1.0":
            raise ValidationError("catalog_version must be '1.0'")
        if not isinstance(document.get("sources"), dict) or not document["sources"]:
            raise ValidationError("catalog must contain a non-empty sources object")
        return cls(document, catalog_path)

    @property
    def sources(self) -> dict[str, Any]:
        return self.document["sources"]

    def source(self, name: str) -> dict[str, Any]:
        try:
            return self.sources[name]
        except KeyError as exc:
            raise ValidationError(f"Unknown catalog source: {name}") from exc

    def columns(self, source: str) -> dict[str, dict[str, Any]]:
        schema = self.source(source).get("schema")
        if not isinstance(schema, list):
            raise ValidationError(f"Source {source} has no valid schema")
        return {column["name"]: column for column in schema}

    def binding(self, source: str, engine: str) -> dict[str, Any]:
        binding = self.source(source).get("bindings", {}).get(engine)
        if not isinstance(binding, dict):
            raise ValidationError(f"Source {source} has no {engine} binding")
        return binding

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        return path.resolve() if path.is_absolute() else (self.path.parent / path).resolve()

