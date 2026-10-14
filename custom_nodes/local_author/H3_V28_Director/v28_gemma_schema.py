"""The same small JSON Schema drives decoding and local type validation."""
from . import v28_director_core as C

TEXT_FIELDS = ("segment_objective", "start_state", "new_action", "performance",
               "blocking", "camera", "end_state", "continuity_out")
ZH_FIELDS = ("objective", "start_state", "action_progression", "blocking", "camera",
             "dialogue", "sound", "reference_usage", "end_state")


def object_schema(properties: dict, required=None) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else list(required)}


def segment_schema() -> dict:
    text = {"type": "string", "minLength": 1}
    fields = {key: dict(text) for key in TEXT_FIELDS}
    fields.update({
        "beats": {"type": "array", "minItems": 1, "items": text},
        "body_state_start": object_schema({k: text for k in C.BODY_STATE_FIELDS}),
        "body_state_end": object_schema({k: text for k in C.BODY_STATE_FIELDS}),
        "micro_timeline": {"type": "array", "minItems": 1, "items": object_schema({
            "phase": {"type": "string", "enum": sorted(C.MICRO_PHASES)},
            "action": text, "state_change": {"type": "string"}})},
        "render_risk": object_schema({
            "body_geometry": {"type": "string", "enum": sorted(C.RISK_LEVELS)},
            "occlusion": {"type": "string", "enum": sorted(C.RISK_LEVELS)},
            "fast_full_body_motion": {"type": "boolean"}}),
        "user_display_zh": object_schema({k: text for k in ZH_FIELDS})})
    required = list(fields)
    fields.update({k: {"type": "string"} for k in (
        "interaction", "dialogue", "dialogue_timing", "ambience", "physical_sounds",
        "non_verbal_vocals", "music", "conflict_resolution", "anatomy_camera_notes")})
    fields.update({k: {"type": "array", "items": {"type": "string"}} for k in (
        "physical_conflicts", "physical_continuity_notes")})
    fields["reference_usage"] = {"type": "array"}
    return object_schema(fields, required)


def plan_schema(n: int) -> dict:
    seg = segment_schema()
    seg["properties"]["segment_index"] = {"type": "integer", "enum": list(range(1, n + 1))}
    seg["required"].append("segment_index")
    return object_schema({"segments": {"type": "array", "minItems": n, "maxItems": n,
                                       "items": seg}})


def patch_schema(fields: list[str]) -> dict:
    props = segment_schema()["properties"]
    return object_schema({k: props[k] for k in fields})


def errors(value, schema: dict, path: str = "$") -> list[str]:
    kind = schema.get("type")
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str), "integer": type(value) is int,
             "boolean": type(value) is bool}.get(kind, True)
    if not valid:
        return [f"{path}: expected {kind}"]
    out = []
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: invalid enum")
    if kind == "string" and len(value.strip()) < schema.get("minLength", 0):
        out.append(f"{path}: empty string")
    if kind == "object":
        for key in schema.get("required", []):
            if key not in value:
                out.append(f"{path}.{key}: required")
        for key, subschema in schema.get("properties", {}).items():
            if key in value:
                out.extend(errors(value[key], subschema, f"{path}.{key}"))
    if kind == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            out.append(f"{path}: invalid item count")
        if "items" in schema:
            for i, item in enumerate(value):
                out.extend(errors(item, schema["items"], f"{path}[{i}]"))
    return out


def invalid_fields(segment: dict) -> list[str]:
    schema = segment_schema()
    return [k for k in schema["required"]
            if k not in segment or errors(segment[k], schema["properties"][k])]
