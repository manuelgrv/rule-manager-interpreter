from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from . import __version__
from .errors import ValidationError

DSL_VERSION = "1.0"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(document: dict[str, Any]) -> str:
    semantic = deepcopy(document)
    semantic.pop("integrity", None)
    return hashlib.sha256(_canonical(semantic)).hexdigest()


def create_envelope(
    *, rule_id: str, source_language: str, inputs: list[dict[str, str]], plan: dict[str, Any], output_schema: list[dict[str, Any]]
) -> dict[str, Any]:
    document = {
        "dsl_version": DSL_VERSION,
        "rule": {"id": rule_id, "version": 1, "kind": "query", "source_language": source_language},
        "inputs": inputs,
        "parameters": [],
        "plan": plan,
        "output": {"schema": output_schema},
        "compiler": {"name": "rule-manager", "version": __version__},
    }
    document["integrity"] = {"algorithm": "sha256", "digest": digest(document)}
    return document


def validate_envelope(document: dict[str, Any]) -> None:
    if document.get("dsl_version") != DSL_VERSION:
        raise ValidationError(f"Unsupported dsl_version: {document.get('dsl_version')!r}")
    if not isinstance(document.get("plan"), dict) or "op" not in document["plan"]:
        raise ValidationError("DSL plan is missing or invalid")
    integrity = document.get("integrity", {})
    if integrity.get("algorithm") != "sha256" or integrity.get("digest") != digest(document):
        raise ValidationError("DSL integrity check failed")
    if not isinstance(document.get("inputs"), list):
        raise ValidationError("DSL inputs must be a list")

