"""Build the combined JSON Schema that the TypeScript types are generated from."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from multicam_engine.benchmark.ground_truth import GroundTruth
from multicam_engine.models.cutlist import CutList
from multicam_engine.models.project import Project

# Top-level types exposed to the UI. Nested types are included automatically.
EXPORTED_MODELS: dict[str, type[BaseModel]] = {
    "Project": Project,
    "CutList": CutList,
    "GroundTruth": GroundTruth,
}

_NESTED_SCHEMA_KEYS = ("items", "additionalProperties", "not", "contains", "propertyNames")
_LIST_SCHEMA_KEYS = ("anyOf", "oneOf", "allOf", "prefixItems")


def _strip_titles(node: Any, keep_title: bool) -> Any:
    """Remove ``title`` from everything except named definitions.

    Pydantic adds a title to every property ("Start Frame"); json-schema-to-typescript
    would turn each of those into a pointless type alias. Only ``$defs`` entries keep
    their title, so they become named TypeScript types.
    """
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "title" and not keep_title:
            continue
        if key in ("properties", "$defs", "patternProperties") and isinstance(value, dict):
            out[key] = {
                name: _strip_titles(sub, keep_title=(key == "$defs")) for name, sub in value.items()
            }
        elif key in _NESTED_SCHEMA_KEYS and isinstance(value, dict):
            out[key] = _strip_titles(value, keep_title=False)
        elif key in _LIST_SCHEMA_KEYS and isinstance(value, list):
            out[key] = [_strip_titles(v, keep_title=False) for v in value]
        else:
            out[key] = value
    return out


def build_schema() -> dict[str, Any]:
    _, schema = models_json_schema(
        [(model, "serialization") for model in EXPORTED_MODELS.values()],
        ref_template="#/$defs/{model}",
    )
    combined = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "MulticamSchemas",
        "description": "AUTO-GENERATED from multicam_engine models. Do not edit by hand.",
        "type": "object",
        "additionalProperties": False,
        "properties": {name: {"$ref": f"#/$defs/{name}"} for name in EXPORTED_MODELS},
        "$defs": schema.get("$defs", {}),
    }
    result: dict[str, Any] = _strip_titles(combined, keep_title=True)
    return result


def render_schema() -> str:
    """Deterministic JSON text (sorted keys, trailing newline) for stable diffs."""
    return json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"
