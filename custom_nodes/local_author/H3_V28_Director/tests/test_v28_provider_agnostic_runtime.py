from pathlib import Path

from _v28_bootstrap import load

RC = load("v28_runtime_contract")


def state(name, **changes):
    values = dict(provider_name=name, process_identity={"pid": 1},
                  server_endpoint="http://127.0.0.1:1", model_alias=name,
                  cuda_backend_loaded=True, gpu_layers_requested=True,
                  gpu_compute_confirmed=True, cpu_dominant=False,
                  offload_confirmed=True, resident=True, released=False)
    values.update(changes)
    return RC.DirectorProviderRuntimeContract(**values)


def test_common_gate_accepts_gemma_without_bonsai_identity():
    old = dict(RC._ADAPTERS)
    try:
        RC._ADAPTERS.clear()
        RC.register_runtime("gemma4", lambda: state("gemma4"), lambda: None)
        assert RC.verify_director_gpu_ready("gemma4").gpu_ready
    finally:
        RC._ADAPTERS.clear(); RC._ADAPTERS.update(old)


def test_cpu_fallback_is_fail_closed_for_every_provider():
    old = dict(RC._ADAPTERS)
    try:
        RC._ADAPTERS.clear()
        RC.register_runtime("gemma4", lambda: state("gemma4", cpu_dominant=True), lambda: None)
        try:
            RC.verify_director_gpu_ready("gemma4")
        except RuntimeError as exc:
            assert "禁止 CPU fallback" in str(exc)
        else:
            raise AssertionError("CPU-dominant runtime passed the GPU gate")
    finally:
        RC._ADAPTERS.clear(); RC._ADAPTERS.update(old)


def test_upper_layers_have_no_bonsai_lifecycle_branch():
    root = Path(__file__).resolve().parents[1]
    for name in ("v28_state_machine.py", "v28_orchestrator.py", "v28_routes.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "require_bonsai_released" not in text
        assert "v28_bonsai_runtime" not in text
        assert 'name != "bonsai2"' not in text
