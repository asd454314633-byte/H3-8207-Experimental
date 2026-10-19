from pathlib import Path
import asyncio
import copy
import importlib
import json
import logging
import os
import sys
import tempfile
import time
import types
import unittest

PACKAGE_ROOT = Path(os.environ.get("H3_PREBAKE_PACKAGE_DIR", ""))
if not PACKAGE_ROOT.is_dir():
    raise RuntimeError("Set H3_PREBAKE_PACKAGE_DIR to the h3_conditioning_prebake package directory")
HOST_ROOT = os.environ.get("H3_COMFYUI_HOST_ROOT")
if HOST_ROOT:
    sys.path.insert(0, HOST_ROOT)
FIXTURE = Path(__file__).parent / "fixtures" / "sanitized_198_history_mismatches.json"
PKG = "_h3_history_classification_regression"
pkg = types.ModuleType(PKG)
pkg.__path__ = [str(PACKAGE_ROOT)]
sys.modules[PKG] = pkg
P = importlib.import_module(PKG + ".production")
L = importlib.import_module(PKG + ".attempt_lifecycle")


class HistoryClassificationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.path_to_data = {}
        self.reads = {}
        self.recovered = []
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._ledger_path = P.ledger_path
        self._read_state = P.read_state
        self._bindings = P.execution_state.bindings

        def ledger_path(ctx):
            return self.root / ctx["project_id"] / ("prebake_" + ctx["group_id"] + ".json")

        def read_state(path):
            path = Path(path)
            self.reads[str(path)] = self.reads.get(str(path), 0) + 1
            return copy.deepcopy(self.path_to_data.get(str(path)))

        P.ledger_path = ledger_path
        P.read_state = read_state
        self.bindings = list(self.fixture["bindings"])
        self.mismatch_keys = {
            (self.fixture["ledgers"][row["child_key"]]["binding"]["project_id"],
             int(row["index"]),
             self.fixture["ledgers"][row["child_key"]]["ledger"]["segments"][str(row["index"])]["attempt"]["attempt_id"])
            for row in self.fixture["rows"]
        }
        for record in self.fixture["ledgers"].values():
            self._put_record(record)
        self._put_parent(self.fixture["live_parent"])
        self.bindings.append(self.fixture["live_parent"]["binding"])
        P.execution_state.bindings = lambda: self.bindings
        self.manager = L.AttemptManager(types.SimpleNamespace(), None, None)
        self.signature_generation = 0
        self.manager._state_signature = lambda path: (self.signature_generation,)
        self.manager.recover = self._record_recovery

    def tearDown(self):
        P.ledger_path = self._ledger_path
        P.read_state = self._read_state
        P.execution_state.bindings = self._bindings
        self.tmp.cleanup()

    def _put_parent(self, parent):
        self._put_record(parent)

    def _put_record(self, record):
        path = P.ledger_path(record["binding"])
        self.path_to_data[str(path)] = record["ledger"]
        if "receipts" in record:
            self.path_to_data[str(path.parent / "six_acceptance.json")] = record["receipts"]

    def _record_recovery(self, project, index):
        ctx = next(b for b in self.bindings if b["project_id"] == project)
        ledger = self.path_to_data[str(P.ledger_path(ctx))]
        attempt = ledger["segments"][str(index)]["attempt"]
        self.recovered.append((project, index, attempt["prompt_id"], attempt["status"], attempt["attempt_id"]))

    def test_198_history_records_are_quiet_and_rechecked_when_evidence_changes(self):
        raw_fixture = FIXTURE.read_bytes()
        handler = logging.Handler()
        handler.records = []
        handler.emit = handler.records.append
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        old_level = root_logger.level
        root_logger.setLevel(logging.INFO)
        try:
            started = time.process_time()
            for _ in range(30):
                asyncio.run(self.manager.tick())
            cpu_seconds = time.process_time() - started
            first_audits = [r for r in handler.records if "inherited attempt audit changed" in r.getMessage()]
            self.assertEqual(len(first_audits), 1)
            self.assertFalse(any(r.levelno >= logging.ERROR and "identity does not belong" in r.getMessage()
                                 for r in handler.records))
            self.assertLess(first_audits[0].levelno, logging.ERROR)
            self.assertIn("verified_parent_terminal=198 unconfirmed=1", first_audits[0].getMessage())
            self.assertLess(cpu_seconds, 2.0)

            # The valid parent task remains eligible by its exact prompt ID.
            self.assertIn(("parent-live", 0, "prompt-live-guarded", "PENDING", "attempt-live"), self.recovered)
            # None of the 198 child copies and the one unconfirmed record is recovered.
            self.assertFalse(any((project, index, attempt_id) in self.mismatch_keys
                                 for project, index, _, _, attempt_id in self.recovered))

            # A parent receipt change invalidates historical classification; restoring it revalidates.
            row = self.fixture["mutation_row"]
            parent_path = P.ledger_path(self.fixture["ledgers"][row["parent_key"]]["binding"])
            receipts = self.path_to_data[str(parent_path.parent / "six_acceptance.json")]
            segment_index = str(row["index"])
            original = receipts[segment_index]["status"]
            receipts[segment_index]["status"] = "FAILED"
            self.signature_generation += 1
            before = len(handler.records)
            asyncio.run(self.manager.tick())
            self.assertTrue(any("verified_parent_terminal=197 unconfirmed=2" in r.getMessage()
                                for r in handler.records[before:]))
            receipts[segment_index]["status"] = original
            self.signature_generation += 1
            before = len(handler.records)
            asyncio.run(self.manager.tick())
            self.assertTrue(any("verified_parent_terminal=198 unconfirmed=1" in r.getMessage()
                                for r in handler.records[before:]))
            self.assertEqual(FIXTURE.read_bytes(), raw_fixture)
            self.assertTrue(all(count <= 70 for count in self.reads.values()))
        finally:
            root_logger.removeHandler(handler)
            root_logger.setLevel(old_level)

    def test_unconfirmed_parent_never_enters_recovery(self):
        row = self.fixture["unconfirmed"]
        child = self.fixture["ledgers"][row["child_key"]]
        classification, _ = self.manager.inherited_attempt_class(
            child["binding"], int(row["index"]), child["ledger"]["segments"][str(row["index"])]["attempt"],
            child["ledger"]["segments"][str(row["index"])], {}, set(self.fixture["unconfirmed_ancestor_projects"]))
        self.assertEqual(classification, "unconfirmed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
