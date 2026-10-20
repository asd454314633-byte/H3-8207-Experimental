from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

parser = argparse.ArgumentParser()
parser.add_argument("--module-root", required=True)
parser.add_argument("--route-manifest", required=True)
parser.add_argument("--endpoint", default="http://127.0.0.1:8207")
parser.add_argument("--report", required=True)
args = parser.parse_args()

manifest_path = Path(args.route_manifest)
manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
graph_path = Path(manifest["candidate_api_graph"])
if not graph_path.is_absolute():
    graph_path = (manifest_path.parent / graph_path).resolve()
graph_bytes = graph_path.read_bytes()
candidate = json.loads(graph_bytes)
opener = build_opener(ProxyHandler({}))
with opener.open(args.endpoint.rstrip("/") + "/object_info", timeout=30) as response:
    object_info = json.load(response)

sys.path.insert(0, args.module_root)
from h3_action_director.execution_graph import analyze_api_graph, find_roots

roots = find_roots(candidate, object_info)
result = analyze_api_graph(candidate, object_info, output_ids=roots)
report = {
    "schema_version": "1.0",
    "status": "PASS" if result["status"] == "LIVE_COMPATIBLE" else "HOLD",
    "endpoint": args.endpoint,
    "runtime_authority": "live /object_info",
    "selected_route": manifest.get("route_name", "UNNAMED"),
    "candidate_api_graph": str(graph_path),
    "candidate_api_graph_sha256": hashlib.sha256(graph_bytes).hexdigest(),
    "live_object_info_class_count": len(object_info),
    "live_object_info_sha256": hashlib.sha256(json.dumps(object_info, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    "output_roots": roots,
    "reachable_node_count": len(result["reachable_node_ids"]),
    "reachable_node_ids": result["reachable_node_ids"],
    "required_node_types": sorted({candidate[node_id]["class_type"] for node_id in result["reachable_node_ids"]}),
    "missing_node_types": sorted({item.get("class_type") for item in result["validation"]["errors"] if item.get("code") == "unregistered_node"}),
    "validation": result["validation"],
    "checked_unix": time.time(),
}
report_path = Path(args.report)
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 3)
