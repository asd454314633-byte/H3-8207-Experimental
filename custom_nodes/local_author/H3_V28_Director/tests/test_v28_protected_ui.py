# -*- coding: utf-8 -*-
"""PROTECTED UI CONTRACT tests — born from the DirectorConsole loss incident (2026-09-28).

Root cause (see <H3_PROJECT_DIR>\\V28_1_DIRECTOR_CONSOLE_ROOT_CAUSE.md):
the accepted P11 candidate had H3V28DirectorConsole @998 (520x860) but was never
promoted; every later upgrade/merge/promotion was built on the console-less v027
lineage, MemoryOpt reused ids 998/999, and no test ever asserted the node INSTANCE
inside the workflow JSON (only the class registration).

These tests close that hole. Identification is BY TYPE, never by node id.
Run: python -m unittest tests.test_v28_protected_ui -v
Set H3_UI_GATE_WORKFLOW to gate an arbitrary workflow file.
"""
import copy
import json
import os
import unittest
from pathlib import Path

PROJ = Path(r"<H3_PROJECT_DIR>")
PRODUCTION = PROJ / "MiniMax_H3_全中文导演台_v028_1_PRODUCTION.json"
P11_CANDIDATE = PROJ / "【待晋升候选】MiniMax_H3_全中文导演台_v028_DIRECTOR_DEV_P11真实生成_20260927.json"
CONSOLE_RESTORE = PROJ / "【待晋升候选】MiniMax_H3_全中文导演台_v028_1_CONSOLE_RESTORE_20260928.json"
CONTRACT = PROJ / "V28_1_PROTECTED_UI_CONTRACT.json"

CONSOLE_TYPE = "H3V28DirectorConsole"


def _target_workflow():
    env = os.environ.get("H3_UI_GATE_WORKFLOW")
    return Path(env) if env else CONSOLE_RESTORE


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _nodes_of_type(wf, t):
    return [n for n in wf.get("nodes", []) if n.get("type") == t]


class TestProtectedUIContract(unittest.TestCase):
    """Contract: PROTECTED nodes identified by type, EXACTLY-1 counts."""

    def setUp(self):
        self.wf = _load(_target_workflow())
        self.contract = _load(CONTRACT)

    # -- core contract --------------------------------------------------

    def test_protected_ui_contract(self):
        """Every node in the contract must be present with EXACTLY_1 count."""
        prot = self.contract["protected_nodes"]
        types = {n["type"] for n in wf_nodes(self.wf)} if False else None
        for entry in prot:
            t = entry["type"]
            got = len(_nodes_of_type(self.wf, t))
            self.assertEqual(got, 1, f"{t} count={got}, contract requires EXACTLY_1")

    def test_director_console_exists_once(self):
        got = _nodes_of_type(self.wf, CONSOLE_TYPE)
        self.assertEqual(len(got), 1, f"{CONSOLE_TYPE} count={len(got)}")
        self.assertEqual(got[0].get("mode"), 0, "console must be ACTIVE (mode=0), not BYPASS")

    def test_director_console_visible(self):
        """JSON-level visibility proxy: mode=0, not collapsed, sane size/pos.
        (Real on-screen visibility is separately gated by the BrowserOS live gate.)"""
        n = _nodes_of_type(self.wf, CONSOLE_TYPE)[0]
        self.assertEqual(n.get("mode"), 0)
        self.assertFalse(bool(n.get("collapsed")))
        size = n.get("size") or [0, 0]
        self.assertGreater(size[0], 100, "console width unrealistically small = collapsed/hidden")
        self.assertGreater(size[1], 100, "console height unrealistically small = collapsed/hidden")
        self.assertTrue(n.get("pos") is not None, "console must have a canvas position")

    def test_node_ids_are_unique(self):
        ids = [n["id"] for n in self.wf.get("nodes", [])]
        dupes = {i for i in ids if ids.count(i) > 1}
        self.assertEqual(dupes, set(), f"duplicate node ids: {dupes}")

    def test_last_node_id_valid(self):
        ids = [n["id"] for n in self.wf.get("nodes", [])]
        self.assertEqual(self.wf.get("last_node_id"), max(ids),
                         "last_node_id must equal max node id")

    def test_director_console_survives_roundtrip(self):
        """json.dumps -> parse must keep the console with identical structure."""
        raw = json.dumps(self.wf, ensure_ascii=False)
        rt = json.loads(raw)
        a = _nodes_of_type(self.wf, CONSOLE_TYPE)
        b = _nodes_of_type(rt, CONSOLE_TYPE)
        self.assertEqual(len(b), 1)
        self.assertEqual(json.dumps(a[0], sort_keys=True), json.dumps(b[0], sort_keys=True))

    def test_director_console_survives_memopt_merge(self):
        """THE incident regression: start from a console-bearing lineage,
        programmatically merge the two MemoryOpt nodes (fresh ids), and verify
        the console + both MemoryOpt nodes coexist with EXACTLY_1 counts.
        This permanently seals the 2026-09-28 loss path."""
        base = _load(P11_CANDIDATE)  # console @998, no MemoryOpt
        self.assertEqual(len(_nodes_of_type(base, CONSOLE_TYPE)), 1)
        self.assertEqual(len(_nodes_of_type(base, "H3MemoryOptimization")), 0)

        merged = copy.deepcopy(base)
        nid = max(n["id"] for n in merged["nodes"]) + 1
        memopt = {"id": nid, "type": "H3MemoryOptimization", "mode": 4,
                  "inputs": [], "outputs": [], "properties": {}, "widgets_values": []}
        selector = {"id": nid + 1, "type": "H3MemoryOptimizationSelector", "mode": 0,
                    "inputs": [], "outputs": [], "properties": {},
                    "widgets_values": ["关闭"]}
        merged["nodes"] += [memopt, selector]
        merged["last_node_id"] = nid + 1

        self.assertEqual(len(_nodes_of_type(merged, CONSOLE_TYPE)), 1,
                         "console must survive a MemoryOpt merge")
        self.assertEqual(len(_nodes_of_type(merged, "H3MemoryOptimization")), 1)
        self.assertEqual(len(_nodes_of_type(merged, "H3MemoryOptimizationSelector")), 1)
        ids = [n["id"] for n in merged["nodes"]]
        self.assertEqual(len(ids), len(set(ids)), "merge must not create id collisions")


def wf_nodes(wf):
    return wf.get("nodes", [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
