#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui_contract_guard.py — H3 PROTECTED UI CONTRACT hard gate (P0.5, 2026-09-28)

Single shared promotion gate for V28.1 build / V28.1 promotion / future V28.2+ builds.
Wire this into EVERY script that writes a production workflow JSON.
On ANY failure: exit code 2, verdict JSON on stdout, caller MUST ABORT BEFORE WRITE.

Checks (per task H3_V28_2_DIRECTOR_FINAL_ARCHITECTURE_AND_UI_GUARD_01 P0.5-1):
  1. H3V28DirectorConsole           = EXACTLY 1
  2. H3OperationSelector            = EXACTLY 1
  3. H3MemoryOptimizationSelector   = EXACTLY 1
  4. H3MemoryOptimization           = EXACTLY 1
  5. NODE_IDS_UNIQUE = YES
  6. last_node_id >= max(node.id)

Identification is BY TYPE ONLY, never by node id (ids may change across upgrades).
Usage:
  python ui_contract_guard.py <workflow.json> [--contract <contract.json>]
Exit: 0 = PASS, 2 = FAIL, 3 = input error.
"""
import argparse
import json
import sys
from pathlib import Path

DEFAULT_CONTRACT = Path(r"<H3_PROJECT_DIR>\V28_1_PROTECTED_UI_CONTRACT.json")

# Fallback contract (must mirror V28_1_PROTECTED_UI_CONTRACT.json) used when the
# contract file itself is unreadable — the gate must never fail OPEN.
FALLBACK_REQUIRED = {
    "H3V28DirectorConsole": 1,
    "H3OperationSelector": 1,
    "H3MemoryOptimizationSelector": 1,
    "H3MemoryOptimization": 1,
}


def load_required_counts(contract_path):
    if contract_path and Path(contract_path).exists():
        try:
            c = json.loads(Path(contract_path).read_text(encoding="utf-8"))
            req = {}
            for entry in c.get("protected_nodes", []) + c.get("also_protected_context", []):
                if "type" in entry and entry.get("count") == "EXACTLY_1":
                    req[entry["type"]] = 1
            if req:
                return req, str(contract_path)
        except Exception:
            pass
    return dict(FALLBACK_REQUIRED), "FALLBACK_INLINE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow")
    ap.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    args = ap.parse_args()

    wf_path = Path(args.workflow)
    if not wf_path.exists():
        print(json.dumps({"VERDICT": "FAIL", "ERROR": "WORKFLOW_NOT_FOUND", "path": str(wf_path)},
                         ensure_ascii=False))
        return 3
    try:
        data = json.loads(wf_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"VERDICT": "FAIL", "ERROR": "JSON_UNREADABLE", "detail": str(e)},
                         ensure_ascii=False))
        return 3

    nodes = data.get("nodes") or []
    required, contract_source = load_required_counts(args.contract)

    checks = []
    type_counts = {}
    for n in nodes:
        t = str(n.get("type", ""))
        type_counts[t] = type_counts.get(t, 0) + 1

    for ntype, want in sorted(required.items()):
        got = type_counts.get(ntype, 0)
        checks.append({
            "check": f"{ntype} == EXACTLY_1",
            "expected": want, "actual": got,
            "pass": got == want,
        })

    ids = []
    for n in nodes:
        try:
            ids.append(int(n.get("id")))
        except (TypeError, ValueError):
            checks.append({"check": "node_id_parseable", "pass": False,
                           "detail": f"node with bad id: {n.get('id')!r}"})
            ids = None
            break

    if ids is not None:
        unique = len(ids) == len(set(ids))
        checks.append({"check": "NODE_IDS_UNIQUE", "pass": unique,
                       "total_ids": len(ids), "distinct_ids": len(set(ids))})
        try:
            last_node_id = int(data.get("last_node_id"))
            max_id = max(ids)
            ok = last_node_id >= max_id
            checks.append({"check": "last_node_id >= max(node.id)", "pass": ok,
                           "last_node_id": last_node_id, "max_id": max_id})
        except (TypeError, ValueError):
            checks.append({"check": "last_node_id_present_int", "pass": False,
                           "actual": data.get("last_node_id")})

    all_pass = bool(checks) and all(c.get("pass") for c in checks)
    verdict = {
        "VERDICT": "PASS" if all_pass else "FAIL",
        "workflow": str(wf_path),
        "sha256_16": __import__("hashlib").sha256(wf_path.read_bytes()).hexdigest()[:16],
        "node_count": len(nodes),
        "contract_source": contract_source,
        "checks": checks,
        "policy": "FAIL => CALLER MUST ABORT BEFORE WRITE (PRODUCTION_OVERWRITE=FORBIDDEN)",
    }
    print(json.dumps(verdict, ensure_ascii=False, indent=1))
    return 0 if all_pass else 2


if __name__ == "__main__":
    sys.exit(main())
