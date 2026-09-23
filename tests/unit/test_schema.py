import json

from multicam_engine.models.schema import EXPORTED_MODELS, build_schema, render_schema


def test_all_exported_models_are_present() -> None:
    schema = build_schema()
    for name in EXPORTED_MODELS:
        assert schema["properties"][name] == {"$ref": f"#/$defs/{name}"}
        assert name in schema["$defs"]


def test_nested_types_are_named() -> None:
    defs = build_schema()["$defs"]
    for name in ("Rational", "Segment", "Clip", "ClipRole", "SpeechTurn", "MsRange"):
        assert name in defs, name
        assert defs[name]["title"] == name


def test_property_titles_are_stripped() -> None:
    defs = build_schema()["$defs"]
    for props in (d.get("properties", {}) for d in defs.values()):
        for prop in props.values():
            assert "title" not in prop


def test_defaults_are_required_in_serialization_schema() -> None:
    # Serialized output always contains defaulted fields, so TS types must not be optional.
    segment = build_schema()["$defs"]["Segment"]
    assert "source" in segment["required"]


def test_render_is_deterministic_json() -> None:
    first, second = render_schema(), render_schema()
    assert first == second
    assert first.endswith("\n")
    json.loads(first)
