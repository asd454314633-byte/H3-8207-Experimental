"""Every CLI token V28 hands to llama-server.exe must exist in THAT build.

Why this file exists (P11 TEST1, first real `POST /h3_director/start`):
    the shipped command line carried `--n-parallel` and `--no-display-prompt`.
    The binary this project froze - PrismML llama.cpp b10743 / adfffbe41, the one
    that actually sits in director_runtime/bonsai2/runtime - answered
        error: invalid argument: --n-parallel
    and exited 1 after five seconds. The director never loaded, so every
    downstream PHASE A test was blocked by a spelling. Static review missed it
    for the same reason the HTTP guard bug survived: nothing had ever run the
    binary. `--help` costs under a second and loads no weights, so there is no
    excuse for guessing flag names.

    Two controls keep this honest:
      * absence control - the retired spellings must NOT be in the parsed set,
        otherwise "all tokens accepted" would be a probe that cannot fail;
      * garbage control - a made-up flag must be rejected by the same set.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B                                                 # noqa: E402

PKG_DIR = B.PKG_DIR
COMFY_ROOT = PKG_DIR.parent.parent          # ...\ComfyUI_H3_V27_Lab
SERVER_EXE = COMFY_ROOT / "director_runtime" / "bonsai2_cuda_lab" / "runtime" / "llama-server.exe"

_FLAG_RE = re.compile(r"--[a-z0-9][a-z0-9\-]*")


def help_text():
    p = subprocess.run([str(SERVER_EXE), "--help"], capture_output=True,
                       text=True, timeout=120, cwd=str(SERVER_EXE.parent))
    return (p.stdout or "") + (p.stderr or "")


@unittest.skipUnless(SERVER_EXE.is_file(), f"no llama-server.exe at {SERVER_EXE}")
class TestBonsaiCommandLine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.R = B.load("v28_bonsai_runtime")
        cls.txt = help_text()
        cls.accepted = set(_FLAG_RE.findall(cls.txt))

    def cfg(self, **over):
        base = {"server_exe": str(SERVER_EXE),
                "model_main": str(COMFY_ROOT / "director_runtime" / "bonsai2" / "models"
                                  / "Ternary-Bonsai-2-27B-PQ2_0.gguf"),
                "mmproj": str(COMFY_ROOT / "director_runtime" / "bonsai2" / "models"
                              / "Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf"),
                "port": 18999, "thinking": "medium", "n_parallel": 1,
                "ctx_size": 32768, "gpu_layers": 99, "no_mmap": True}
        base.update(over)
        return base

    def flags_of(self, cmd):
        return [t for t in cmd if t.startswith("--")]

    # ------------------------------------------------------------------ #
    # controls: the parsed set must be able to say "no"
    # ------------------------------------------------------------------ #
    def test_absence_control_the_retired_spellings_are_rejected_by_the_binary(self):
        self.assertNotIn("--n-parallel", self.accepted,
                         "probe changed: the build now accepts --n-parallel again")
        self.assertNotIn("--no-display-prompt", self.accepted)
        self.assertIn("--parallel", self.accepted)
        self.assertIn("--gpu-layers", self.accepted)

    def test_garbage_control(self):
        self.assertNotIn("--not-a-real-flag-xyz", self.accepted)
        self.assertGreater(len(self.accepted), 80,
                           "help parsing returned almost nothing: the probe is broken")

    # ------------------------------------------------------------------ #
    # the actual assertion
    # ------------------------------------------------------------------ #
    def test_every_flag_we_pass_exists_in_this_build(self):
        for purpose in ("plan", "analyze", "continue"):
            for thinking in ("off", "low", "medium", "high"):
                cmd, env = self.R.build_command(self.cfg(thinking=thinking), purpose)
                for tok in self.flags_of(cmd):
                    self.assertIn(tok, self.accepted,
                                  f"{purpose}/{thinking}: {tok} is not a flag of "
                                  f"{self.R.__file__}'s frozen build")

    def test_retired_tokens_are_gone_from_the_built_command(self):
        cmd, _ = self.R.build_command(self.cfg(), "plan")
        self.assertNotIn("--n-parallel", cmd)
        self.assertNotIn("--no-display-prompt", cmd)
        self.assertIn("--parallel", cmd)
        self.assertEqual(cmd[cmd.index("--parallel") + 1], "1")

    def test_slot_count_config_key_is_still_n_parallel(self):
        """The config vocabulary must not churn with the CLI spelling."""
        cmd, _ = self.R.build_command(self.cfg(n_parallel=4), "plan")
        self.assertEqual(cmd[cmd.index("--parallel") + 1], "4")

    def test_thinking_maps_to_the_reasoning_budget_tiers(self):
        for level, expected in (("off", "0"), ("low", "512"), ("medium", "2048"),
                                ("high", "4096")):
            cmd, _ = self.R.build_command(self.cfg(thinking=level), "plan")
            self.assertEqual(cmd[cmd.index("--reasoning-budget") + 1], expected, level)
            self.assertNotIn("-1", cmd[cmd.index("--reasoning-budget") + 1:])

    def test_mmproj_only_when_the_projector_file_exists(self):
        self.assertIn("--no-mmproj", self.accepted,
                      "the fallback spelling is not a flag of this build either")
        cmd, _ = self.R.build_command(self.cfg(), "analyze")
        self.assertIn("--mmproj", cmd)
        cmd2, _ = self.R.build_command(self.cfg(mmproj=str(COMFY_ROOT / "nope.gguf")),
                                       "analyze")
        self.assertNotIn("--mmproj", cmd2)
        self.assertIn("--no-mmproj", cmd2)

    def test_cuda_dll_dirs_are_on_path_and_gpu_layers_reach_the_server(self):
        cmd, env = self.R.build_command(self.cfg(gpu_layers=99), "plan")
        self.assertEqual(cmd[cmd.index("--gpu-layers") + 1], "99")
        self.assertIn("PATH", env)
        self.assertTrue(bool(os.path.splitdrive(env["PATH"].split(os.pathsep)[0])[0]) or
                        "director_runtime" in env["PATH"].lower(),
                        "the CUDA dll directories must be searched first")

    def test_no_forbidden_port_can_ever_be_picked(self):
        """`start_server` refuses these, and the picker must never hand one out."""
        P = B.load("v28_paths")
        for preferred in sorted(P.FORBIDDEN_PORTS):
            got = self.R.probe_free_port(preferred)
            self.assertNotIn(got, P.FORBIDDEN_PORTS, f"{preferred} leaked through")
            self.assertTrue(P.DIRECTOR_PORT_MIN <= got <= P.DIRECTOR_PORT_MAX, got)

    def test_cuda_start_gate_requires_modules_buffers_and_compute_identity(self):
        maps = [SimpleNamespace(path=x) for x in
                ("ggml-cuda.dll", "cublas64_13.dll", "cudart64_13.dll", "nvcuda.dll")]
        fake_psutil = SimpleNamespace(Process=lambda pid: SimpleNamespace(memory_maps=lambda: maps),
                                       NoSuchProcess=RuntimeError, AccessDenied=PermissionError)
        log = "CUDA0 model buffer\nCUDA0 KV buffer\nCUDA0 compute buffer\n"
        pmon = SimpleNamespace(returncode=0,
                               stdout="    0      43210     C     90     70 llama-server.exe\n")
        with mock.patch.object(self.R, "psutil", fake_psutil), \
             mock.patch.object(self.R.Path, "read_text", return_value=log), \
             mock.patch.object(self.R.subprocess, "run", return_value=pmon):
            gate = self.R.cuda_start_gate(43210, "unused.log")
        self.assertTrue(gate["passed"])
        self.assertFalse(gate["CPU_DOMINANT"])

    def test_cuda_start_gate_fails_closed_on_cpu_buffers(self):
        fake_psutil = SimpleNamespace(Process=lambda pid: SimpleNamespace(memory_maps=lambda: []),
                                       NoSuchProcess=RuntimeError, AccessDenied=PermissionError)
        pmon = SimpleNamespace(returncode=0, stdout="")
        with mock.patch.object(self.R, "psutil", fake_psutil), \
             mock.patch.object(self.R.Path, "read_text", return_value="CPU compute buffer"), \
             mock.patch.object(self.R.subprocess, "run", return_value=pmon):
            gate = self.R.cuda_start_gate(43210, "unused.log")
        self.assertFalse(gate["passed"])
        self.assertTrue(gate["CPU_DOMINANT"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
