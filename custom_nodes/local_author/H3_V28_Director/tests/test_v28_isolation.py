"""The isolation harness itself under test - not the code, the GUARD.

Why this file exists: a previous revision of `_v28_bootstrap.load()` preferred a
bare-name import, which created a SECOND copy of every audited module
(`v28_paths`, `v28_project`, ...) next to the synthetic-package copy the package
itself uses. `isolate()` patched only the first copy, so the tests asserted
against a temp directory while the code under test wrote through the copy that
still carried the production constants. Result: the suite reported green while it
had been creating real projects under `<H3_PROJECT_DIR>\\V28_PROJECTS` and
overwriting a real Motion Context slot in
`<COMFYUI_DIR>\\ComfyUI_H3_V27_Lab\\output\\h3_context\\`.

"Nothing reached the production tree" is a claim about the harness, so it needs a
test that measures the harness instead of trusting its docstring. Every check here
is either a module-identity assertion or a before/after fingerprint of the real
directories; the nominal-only checks that existed before all passed while the
damage was happening.
"""
from __future__ import annotations

import io
import os
import pathlib
import re
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B                                                 # noqa: E402
from test_v28_state_machine import StateMachineCase                        # noqa: E402

AUDITED = B.MODULES + ("v28_orchestrator", "v28_routes", "v28_gemma_provider")

# The two production locations a leak shows up in first.
REAL_PROJECTS_ROOT = pathlib.Path(r"<H3_PROJECT_DIR>\V28_PROJECTS")
REAL_MC_DIR = pathlib.Path(r"<COMFYUI_DIR>\ComfyUI_H3_V27_Lab\output\h3_context")

# Built by concatenation on purpose: written as one literal, the second pattern
# would match the line that defines it and the scanner would report its own
# source as an offender (a real failure this file had before it was worded this
# way). The control below proves the patterns still catch a genuine bare import.
BARE_IMPORT_PATTERNS = (re.compile(r"^(?:import|from)\s+v28_\w+"),
                        re.compile("import_module\\(\\s*['\"]" + "v28_"))


def scan_for_bare_imports(here):
    """[(file, lineno, line)] for any import that bypasses `_v28_bootstrap.load`."""
    offenders = []
    for fn in sorted(os.listdir(here)):
        if not fn.endswith(".py") or fn == "_v28_bootstrap.py":
            continue
        with io.open(os.path.join(here, fn), encoding="utf-8") as fh:
            src = fh.read()
        for i, line in enumerate(src.splitlines(), 1):
            s = line.strip()
            if any(rx.search(s) for rx in BARE_IMPORT_PATTERNS):
                offenders.append(f"{fn}:{i}: {s}")
    return offenders


def snapshot(root: pathlib.Path) -> tuple:
    """(relpath, size, mtime_ns) for every file under `root`; ("<ABSENT>",) if missing.

    Recursive and cheap on purpose: these trees hold a handful of small files, and
    a full walk is the only thing that catches "one real 17 MB latent replaced by
    an 11-byte placeholder" - a count or a top-level listing would have missed it.
    """
    if not root.exists():
        return ("<ABSENT>",)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            p = pathlib.Path(dirpath) / fn
            try:
                st = p.stat()
            except OSError:
                continue                      # vanished mid-walk: not our write
            out.append((str(p.relative_to(root)), st.st_size, st.st_mtime_ns))
    return tuple(out)


class TestOneModuleIdentity(unittest.TestCase):
    """The precondition every other test silently depended on."""

    def test_every_audited_module_exists_once(self):
        for name in AUDITED:
            B.load(name)
        self.assertEqual(B.identity_check(AUDITED), [],
                         "two copies of an audited module are importable at once")

    def test_bare_alias_and_package_copy_are_the_same_object(self):
        bare = B.load("v28_paths")
        self.assertIs(bare, sys.modules[f"{B.PKG_NAME}.v28_paths"])
        B.load("v28_project")
        self.assertIs(sys.modules["v28_project"],
                      sys.modules[f"{B.PKG_NAME}.v28_project"])

    def test_consumers_hold_the_patched_paths_module(self):
        M = B.load_all()
        # Every module that binds `from . import v28_paths as P` at import time.
        # v28_h3_format imports it lazily inside a function, so it has no
        # module attribute to compare - identity_check() covers it instead.
        eager = ("v28_project", "v28_state_machine", "v28_provider",
                 "v28_bonsai_runtime",  
                 "v28_orchestrator", "v28_routes")
        for name in eager:
            mod = B.load(name)
            self.assertTrue(hasattr(mod, "P"), f"{name} no longer binds v28_paths as P")
            self.assertIs(mod.P, M["v28_paths"],
                          f"{name}.P is a different v28_paths object - isolate() "
                          f"would patch a copy this module never reads")
        self.assertEqual(B.identity_check(AUDITED), [])

    def test_load_refuses_a_second_identity_instead_of_shipping_it(self):
        """The guard raises: a bare copy appearing later must break the run loudly."""
        M = B.load_all()
        sys.modules["v28_gemma_provider"] = types.ModuleType("duplicate")
        try:
            with self.assertRaises(RuntimeError) as cm:
                B.load("v28_gemma_provider")
            self.assertIn("double module identity", str(cm.exception))
        finally:
            sys.modules["v28_gemma_provider"] = M["v28_gemma_provider"]

    def test_bare_import_scanner_is_not_vacuous(self):
        """A guard that finds nothing because it is broken is worse than none."""
        hit = [l for l in ("import v28_paths", "from v28_paths import PROJECTS_ROOT",
                           'importlib.import_module("' + 'v28_state_machine")')
               if any(rx.search(l) for rx in BARE_IMPORT_PATTERNS)]
        self.assertEqual(len(hit), 3, hit)
        clean = [l for l in ("import os", "from test_v28_state_machine import make_plan",
                             'B.load("v28_' + 'paths")')
                 if any(rx.search(l) for rx in BARE_IMPORT_PATTERNS)]
        self.assertEqual(clean, [])

    def test_no_test_file_imports_an_audited_module_by_bare_name(self):
        self.assertEqual(scan_for_bare_imports(B.HERE), [],
                         "an import bypassing B.load() reintroduces the leak")


class TestWritesStayInTemp(StateMachineCase):
    """Run the real lifecycle, then prove where the bytes actually went."""

    def test_project_and_slot_paths_resolve_inside_the_temp_root(self):
        d = self.PJ.project_dir("iso_case")
        self.assertTrue(str(d).startswith(str(self.root)),
                        f"project_dir escaped the temp root: {d}")
        slot = self.PJ.mc_slot_path(1)
        self.assertTrue(str(slot).startswith(str(self.root)),
                        f"Motion Context slot path escaped the temp root: {slot}")
        self.assertIn("h3_context", str(slot))          # still the V27 pack layout

    def test_full_lifecycle_lands_where_the_reader_looks(self):
        """create -> plan -> generate -> accept, then read the result back.

        The old harness could pass a test like this by accident: the writer used
        the production module copy and the reader the patched one, so only checks
        that went through a SINGLE module survived - and they survived for the
        wrong reason. Here the same objects are asserted, in both directions.
        """
        self.set_plan(2)
        self.generate(expect_seg=1)
        self.SM.accept(self.pid)
        d = self.PJ.project_dir(self.pid)
        self.assertTrue(str(d).startswith(str(self.root)), str(d))
        st = self.SM.load_state(self.pid)
        self.assertEqual(st["last_accepted_segment"], 1)
        self.assertEqual(st["current_segment"], 2)
        self.assertTrue((d / "SESSION_STATE.json").is_file())
        self.assertTrue(list((d / "accepted").glob("seg_001_*.json")),
                        "the accept record is not under the temp project dir")
        self.assertEqual(self.PJ.mc_slot_path(1).read_bytes(), b"FAKE-LATENT")
        self.assertIs(self.PJ.P, self.P)
        self.assertIs(sys.modules[f"{B.PKG_NAME}.v28_paths"], self.P)

    def test_reroll_also_writes_only_to_temp(self):
        self.set_plan(3)
        self.generate(expect_seg=1)
        wi = self.SM.widget_instructions(self.pid, reroll=True)
        self.SM.mark_generating(self.pid, instruction=wi)
        st = self.SM.load_state(self.pid)
        self.assertEqual(st["status"], "GENERATING")
        self.assertEqual(st["attempt"], 2, "the reroll counter should live in temp state")
        for p in pathlib.Path(self.root).rglob("SESSION_STATE.json"):
            self.assertTrue(str(p).startswith(str(self.root)), str(p))


class TestProductionTreesUntouched(StateMachineCase):
    """Before/after fingerprints of the two directories that got hit before."""

    def test_real_project_root_is_unchanged_by_a_full_lifecycle(self):
        before = snapshot(REAL_PROJECTS_ROOT)
        self.set_plan(2)
        self.generate(expect_seg=1)
        self.SM.accept(self.pid)
        self.assertEqual(snapshot(REAL_PROJECTS_ROOT), before,
                         "a test wrote into the real V28_PROJECTS root")

    def test_real_motion_context_slot_dir_is_unchanged(self):
        before = snapshot(REAL_MC_DIR)
        self.set_plan(2)
        self.generate(expect_seg=1)
        self.assertEqual(snapshot(REAL_MC_DIR), before,
                         "a test wrote into the real h3_context slot directory")


class TestThePatchIsUndone(unittest.TestCase):
    """`isolate()` rewrites constants on the ONE shared module object, so it has
    to give them back. Measured, not assumed (2026-09-27, P11 BUG-5 round).

    A fresh test file sorted alphabetically before
    `test_v28_bonsai_cli_flags.py`, ran its `fresh_env()`, and left
    `v28_paths.BONSAI_RUNTIME_DIR` pointing at a temp directory that had just been
    deleted. The CLI test then asserted the CUDA directories appear on PATH, got
    an empty list from `cuda_dll_dirs()`, and failed - while passing perfectly on
    its own. Nothing about the product changed between those two runs; only the
    order did. Isolation that outlives the `with` block is a second, quieter
    version of the double-identity bug this whole file exists for.
    """

    def test_path_constants_survive_the_block(self):
        P = B.load("v28_paths")
        before = {k: v for k, v in vars(P).items() if isinstance(v, pathlib.Path)}
        with B.fresh_env() as (_M, root):
            self.assertNotEqual(str(P.BONSAI_RUNTIME_DIR), str(before["BONSAI_RUNTIME_DIR"]),
                                "the temp patch must actually be applied inside the block")
            self.assertTrue(str(P.PROJECTS_ROOT).startswith(str(root)))
        after = {k: v for k, v in vars(P).items() if isinstance(v, pathlib.Path)}
        changed = {k: (str(before[k]), str(after[k])) for k in before if before[k] != after[k]}
        self.assertEqual(changed, {}, f"fresh_env left the shared module patched: {changed}")

    def test_control_isolate_alone_would_have_leaked(self):
        """Positive control: prove the check above can fail. Calling `isolate()`
        without the restore must be observable, otherwise
        test_path_constants_survive_the_block is asserting nothing."""
        P = B.load("v28_paths")
        import shutil as _sh
        import tempfile as _tf
        keep = {k: v for k, v in vars(P).items() if isinstance(v, pathlib.Path)}
        tmp = _tf.mkdtemp(prefix="h3v28_control_")
        try:
            B.isolate(P, tmp)
            self.assertNotEqual(P.BONSAI_RUNTIME_DIR, keep["BONSAI_RUNTIME_DIR"])
            self.assertTrue(str(P.PROJECTS_ROOT).startswith(str(tmp)),
                            "isolate() did not move the project root - the control is broken")
        finally:
            for k, v in keep.items():          # ALL of them: this leaks otherwise,
                setattr(P, k, v)               # and this test sorts first in the class
            _sh.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
