"""Compile and validate ComfyUI API graphs against a live /object_info snapshot.

The compiler intentionally refuses ambiguous bypasses and missing runtime nodes.
It never "fixes" a graph by dropping a reachable feature.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Mapping
import re


class GraphCompatibilityError(ValueError):
    def __init__(self, issues: list[dict[str, Any]]):
        self.issues = issues
        super().__init__("; ".join(f"{x.get('code')}: {x.get('message')}" for x in issues))


@dataclass
class CompiledGraph:
    api_graph: dict[str, dict[str, Any]]
    roots: list[str]
    reachable_node_ids: list[str]
    pruned_node_ids: list[str]
    sha256: str
    validation: dict[str, Any]


def _is_link(value: Any) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and isinstance(value[0], (str, int)) and isinstance(value[1], int)
            and not isinstance(value[1], bool))


def _ref_key(value: Any) -> str:
    return str(value[0])


def _clone_graph(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    import copy
    result = copy.deepcopy(dict(graph))
    for node_id, node in result.items():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict) or not isinstance(node.get("class_type"), str):
            raise GraphCompatibilityError([{"code": "invalid_api_node", "node_id": str(node_id), "message": f"API node {node_id} must contain class_type and inputs"}])
    return result


def _rewrite_bypasses(graph: dict[str, dict[str, Any]], modes: Mapping[str, int] | None,
                      bypass_outputs: Mapping[str, Mapping[str, str]] | None) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Apply Comfy node modes to an API graph. Mode 4 requires explicit output->input mapping."""
    modes = modes or {}
    bypass_outputs = bypass_outputs or {}
    issues: list[dict[str, Any]] = []
    disabled = {str(k) for k, mode in modes.items() if int(mode) == 2}
    bypassed = {str(k) for k, mode in modes.items() if int(mode) == 4}
    for node_id in disabled:
        if node_id not in graph:
            issues.append({"code": "mode_node_missing", "node_id": node_id, "message": f"Disabled node {node_id} is absent from candidate API graph"})
    for node_id in bypassed:
        node = graph.get(node_id)
        mapping = bypass_outputs.get(node_id)
        if node is None:
            issues.append({"code": "mode_node_missing", "node_id": node_id, "message": f"Bypassed node {node_id} is absent from candidate API graph"})
        elif not mapping:
            issues.append({"code": "bypass_mapping_required", "node_id": node_id, "class_type": node.get("class_type"), "message": f"Mode=4 node {node_id} requires an explicit output-to-input bypass map"})
    if issues:
        return graph, issues

    replacements: dict[tuple[str, int], Any] = {}
    for node_id in bypassed:
        node = graph[node_id]
        for out_index, input_name in bypass_outputs[node_id].items():
            try:
                idx = int(out_index)
            except (ValueError, TypeError):
                issues.append({"code": "invalid_bypass_output_index", "node_id": node_id, "message": f"Invalid output index {out_index!r}"}); continue
            if input_name not in node["inputs"]:
                issues.append({"code": "invalid_bypass_input", "node_id": node_id, "input": input_name, "message": f"Bypass input {input_name!r} does not exist"}); continue
            source = node["inputs"][input_name]
            if not _is_link(source):
                issues.append({"code": "bypass_input_not_linked", "node_id": node_id, "input": input_name, "message": "Bypass input must link to an upstream node"}); continue
            replacements[(node_id, idx)] = list(source)
    if issues:
        return graph, issues

    for consumer_id, node in graph.items():
        for input_name, value in list(node["inputs"].items()):
            if not _is_link(value):
                continue
            source_id = _ref_key(value)
            if source_id in bypassed:
                replacement = replacements.get((source_id, value[1]))
                if replacement is None:
                    issues.append({"code": "bypass_output_unmapped", "node_id": consumer_id, "input": input_name, "source_node_id": source_id, "source_output": value[1], "message": f"No bypass source maps output {value[1]} of node {source_id}"})
                else:
                    node["inputs"][input_name] = replacement
            elif source_id in disabled:
                issues.append({"code": "reference_to_disabled_node", "node_id": consumer_id, "input": input_name, "source_node_id": source_id, "message": f"Active node {consumer_id} references disabled node {source_id}"})
    if issues:
        return graph, issues
    return {k: v for k, v in graph.items() if k not in disabled | bypassed}, []


def find_roots(graph: Mapping[str, Any], object_info: Mapping[str, Any]) -> list[str]:
    roots = []
    for node_id, node in graph.items():
        schema = object_info.get(node.get("class_type"), {})
        if schema.get("output_node") is True:
            roots.append(str(node_id))
    return sorted(roots)


def reachable_nodes(graph: Mapping[str, Any], root_ids: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    queue = deque(str(x) for x in root_ids)
    for root in root_ids:
        if str(root) not in graph:
            issues.append({"code": "output_root_missing", "node_id": str(root), "message": f"Declared output root {root} is absent"})
    while queue:
        node_id = queue.popleft()
        if node_id in seen or node_id not in graph:
            continue
        seen.add(node_id)
        for name, value in graph[node_id].get("inputs", {}).items():
            if _is_link(value):
                source_id = _ref_key(value)
                if source_id in graph:
                    queue.append(source_id)
    return sorted(seen), issues


def _detect_cycles(graph: Mapping[str, Any]) -> list[list[str]]:
    edges: dict[str, list[str]] = defaultdict(list)
    for node_id, node in graph.items():
        for value in node.get("inputs", {}).values():
            if _is_link(value) and _ref_key(value) in graph:
                edges[str(node_id)].append(_ref_key(value))
    state: dict[str, int] = {}
    stack: list[str] = []
    cycles: list[list[str]] = []
    def visit(n: str) -> None:
        state[n] = 1; stack.append(n)
        for nxt in edges[n]:
            if state.get(nxt, 0) == 0:
                visit(nxt)
            elif state.get(nxt) == 1:
                cycles.append(stack[stack.index(nxt):] + [nxt])
        stack.pop(); state[n] = 2
    for n in graph:
        if state.get(n, 0) == 0:
            visit(str(n))
    return cycles


def validate_api_graph(graph: Mapping[str, Any], object_info: Mapping[str, Any], root_ids: list[str],
                       feature_sources: Mapping[str, str] | None = None) -> dict[str, Any]:
    feature_sources = feature_sources or {}
    issues: list[dict[str, Any]] = []; warnings: list[dict[str, Any]] = []
    ids = {str(x) for x in graph}
    schemas: dict[str, Mapping[str, Any]] = {}
    for node_id, node in graph.items():
        node_id = str(node_id); typ = node.get("class_type")
        schema = object_info.get(typ)
        if not schema:
            issues.append({"code": "unregistered_node", "node_id": node_id, "class_type": typ,
                           "feature_source": feature_sources.get(node_id, node.get("_meta", {}).get("title", "unattributed")),
                           "message": f"Required executable node {typ!r} is not registered in current /object_info"})
            continue
        schemas[node_id] = schema
        inputs = node.get("inputs", {})
        schema_inputs = schema.get("input", {})
        declared = dict(schema_inputs.get("required", {})) | dict(schema_inputs.get("optional", {}))
        wildcard_dynamic = not declared and "*" in schema.get("output", []) and not schema.get("is_input_list", False)
        for name in schema_inputs.get("required", {}):
            if name not in inputs and not any(str(key).startswith(name + ".") for key in inputs):
                issues.append({"code": "required_input_missing", "node_id": node_id, "class_type": typ, "input": name, "message": f"Required input {name!r} is missing"})
        for name, value in inputs.items():
            dynamic_family = name.split(".", 1)[0] if "." in name else None
            if name not in declared and dynamic_family not in declared:
                if wildcard_dynamic and re.fullmatch(r"any_\d+", name) and _is_link(value):
                    warnings.append({"code": "live_wildcard_input", "node_id": node_id, "class_type": typ, "input": name, "message": "Port accepted through wildcard schema; source reference and output index are still validated"})
                else:
                    issues.append({"code": "unknown_input", "node_id": node_id, "class_type": typ, "input": name, "message": f"Input {name!r} is not in live /object_info schema"})
            if _is_link(value):
                source_id = _ref_key(value); out_index = value[1]
                if source_id not in ids:
                    issues.append({"code": "dangling_reference", "node_id": node_id, "input": name, "source_node_id": source_id, "message": f"Input {name!r} refers to absent node {source_id}"}); continue
                source_schema = schemas.get(source_id) or object_info.get(graph[source_id].get("class_type"), {})
                if not source_schema:
                    # The source node already has an unregistered_node issue; its outputs cannot be schema-checked.
                    continue
                outputs = source_schema.get("output", []) if source_schema else []
                if out_index < 0 or out_index >= len(outputs):
                    issues.append({"code": "invalid_output_index", "node_id": node_id, "input": name, "source_node_id": source_id, "source_output": out_index, "message": f"Reference points to nonexistent output {out_index} on {source_id}"}); continue
                target = declared.get(name) or (declared.get(dynamic_family) if dynamic_family else None)
                actual = outputs[out_index]
                expected = target[0] if isinstance(target, (list, tuple)) and target else None
                accepted = set(str(expected or "").replace(" ", "").split(","))
                dynamic = any(x in accepted for x in ("*", "COMFY_DYNAMICCOMBO_V3", "COMFY_AUTOGROW_V3"))
                if expected and not dynamic and actual != "*" and actual not in accepted:
                    issues.append({"code": "connection_type_mismatch", "node_id": node_id, "input": name, "source_node_id": source_id, "expected": expected, "actual": actual, "message": f"{actual} output cannot feed {expected} input"})
        output_count = len(schema.get("output", []))
        for consumer_id, consumer in graph.items():
            for name, value in consumer.get("inputs", {}).items():
                if _is_link(value) and _ref_key(value) == node_id and value[1] >= output_count:
                    issues.append({"code": "invalid_output_index", "node_id": str(consumer_id), "input": name, "source_node_id": node_id, "source_output": value[1], "message": f"Reference points to nonexistent output {value[1]} on {node_id}"})
    for cycle in _detect_cycles(graph):
        issues.append({"code": "dependency_cycle", "cycle": cycle, "message": "API graph contains an executable dependency cycle"})
    return {"valid": not issues, "node_count": len(graph), "roots": sorted(map(str, root_ids)), "errors": issues, "warnings": warnings}


def analyze_api_graph(candidate: Mapping[str, Any], object_info: Mapping[str, Any], *,
                      output_ids: list[str] | None = None, node_modes: Mapping[str, int] | None = None,
                      bypass_outputs: Mapping[str, Mapping[str, str]] | None = None,
                      feature_sources: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return the reachable candidate and diagnostics, including a HOLD graph for evidence."""
    graph = _clone_graph(candidate)
    graph, mode_issues = _rewrite_bypasses(graph, node_modes, bypass_outputs)
    if mode_issues:
        return {"status": "HOLD", "api_graph": graph, "roots": list(map(str, output_ids or [])),
                "reachable_node_ids": [], "pruned_node_ids": [],
                "validation": {"valid": False, "node_count": len(graph), "roots": [], "errors": mode_issues}}
    roots = list(map(str, output_ids)) if output_ids is not None else find_roots(graph, object_info)
    if not roots:
        issue = {"code": "output_root_not_found", "message": "No output roots were supplied or declared by live /object_info"}
        return {"status": "HOLD", "api_graph": graph, "roots": [], "reachable_node_ids": [],
                "pruned_node_ids": sorted(graph), "validation": {"valid": False, "node_count": 0, "roots": [], "errors": [issue]}}
    reachable, root_issues = reachable_nodes(graph, roots)
    if root_issues:
        return {"status": "HOLD", "api_graph": {}, "roots": roots, "reachable_node_ids": [],
                "pruned_node_ids": sorted(graph), "validation": {"valid": False, "node_count": 0, "roots": roots, "errors": root_issues}}
    pruned = sorted(set(graph) - set(reachable))
    compiled = {node_id: graph[node_id] for node_id in reachable}
    validation = validate_api_graph(compiled, object_info, roots, feature_sources)
    return {"status": "LIVE_COMPATIBLE" if validation["valid"] else "HOLD", "api_graph": compiled,
            "roots": roots, "reachable_node_ids": reachable, "pruned_node_ids": pruned,
            "validation": validation}


def compile_api_graph(candidate: Mapping[str, Any], object_info: Mapping[str, Any], *,
                      output_ids: list[str] | None = None, node_modes: Mapping[str, int] | None = None,
                      bypass_outputs: Mapping[str, Mapping[str, str]] | None = None) -> CompiledGraph:
    """Resolve modes, retain all output-reachable features, validate live schemas and hash result."""
    import hashlib, json
    result = analyze_api_graph(candidate, object_info, output_ids=output_ids, node_modes=node_modes, bypass_outputs=bypass_outputs)
    compiled = result["api_graph"]; roots = result["roots"]
    reachable = result["reachable_node_ids"]; pruned = result["pruned_node_ids"]
    validation = result["validation"]
    if result["status"] != "LIVE_COMPATIBLE":
        raise GraphCompatibilityError(validation["errors"])
    canonical = json.dumps(compiled, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return CompiledGraph(compiled, roots, reachable, pruned, hashlib.sha256(canonical).hexdigest(), validation)


def validation_report(result: CompiledGraph) -> dict[str, Any]:
    return {"status": "LIVE_COMPATIBLE" if result.validation["valid"] else "HOLD",
            "roots": result.roots, "reachable_node_ids": result.reachable_node_ids,
            "pruned_node_ids": result.pruned_node_ids, "node_count": len(result.api_graph),
            "sha256": result.sha256, "validation": result.validation}


def authorize_recovery(original_receipt: Mapping[str, Any], existing_recovery: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Only a proven pre-enqueue HTTP rejection can authorize exactly one linked recovery."""
    queue = original_receipt.get("queue_after", {})
    status = original_receipt.get("http_status")
    accepted = original_receipt.get("accepted_by_queue")
    prompt_id = original_receipt.get("prompt_id")
    if status != 400 or accepted is not False or prompt_id is not None:
        raise GraphCompatibilityError([{"code": "recovery_not_proven_pre_enqueue", "message": "Original attempt is not a definite HTTP 400 rejection before queue acceptance"}])
    if queue.get("running") != 0 or queue.get("pending") != 0:
        raise GraphCompatibilityError([{"code": "recovery_queue_evidence_incomplete", "message": "Original rejection receipt does not prove an empty queue after rejection"}])
    if existing_recovery is not None:
        raise GraphCompatibilityError([{"code": "recovery_already_reserved", "message": "A linked recovery attempt is already reserved; no duplicate submit is allowed"}])
    return {"status": "REJECTED_PRE_ENQUEUE", "original_attempt_id": original_receipt.get("attempt_id"),
            "recovery_authorized": True, "requires_new_attempt_id": True, "original_evidence_preserved": True}
