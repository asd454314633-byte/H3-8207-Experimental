# v0.1.0-preview — creative editing and Native continuation

## 2026-10-14 main update: Adaptive V1 and a real local six-segment run

**Adaptive V1 is promoted on local 8207 and passed real History recovery, original-player refill and complete playback.** Six validated files are synchronized byte-for-byte. Metadata/types/topology discovery, 24 vs 24.0 normalization, immutable task snapshots and semantic workflow versions do not hardcode nine references, a private story or node IDs. Missing capabilities are still reported.

**LOCAL_8207_GPU_E2E_PASS=PASS:** the later independent PDD Ref2VA 8-step six-segment run has six SUCCESS receipts, exact histories, Native outputs, clips and a successful automatic merge. Measured 1056×608/24fps; merged output is 1302 frames / 54.25 seconds, not the earlier failed single clip or planned approximately 60-second setup. Matching-window VRAM/RAM peaks are NOT_RECORDED.

**PUBLIC_SOURCE_MATCH=PASS for the six listed files; PUBLIC_BUILD_GPU_E2E=NOT_TESTED.** Local success is not a guarantee for every sanitized installation. The existing 48 public regressions, 49 private Adaptive checks and actual GPU executions are separate evidence sets. The v0.1.0-preview tag/assets stay frozen; use main for the new source.

[Adaptive V1 guide](ADAPTIVE_V1.md) · [Measured acceptance report](8207_SIX_SEGMENT_GPU_ACCEPTANCE_20261014.md) · [Machine-readable data](../benchmarks/8207_six_segment_20261014.json)


This is an experimental source preview, not a production promotion.

- Story identity is separate from immutable execution snapshots. Unsubmitted editor changes do not revoke completed clips or a valid predecessor.
- The selected segment alone is planned for submission. Redoing a segment creates a version and invalidates only its real dependents; prior successful versions remain available.
- Execution stays available while other jobs run. Each click has an independent submission identity; the same attempt cannot be dispatched twice. Queue waiting is separate from the 300-second execution budget.
- Missing/stale conditioning is baked for the requested segment. Existing cache integrity and exact predecessor/receipt checks remain enabled.
- Cross-resolution Native continuation resamples only the real predecessor's video latent tail to the requested sampling grid. The audio prefix remains exact. Same-grid continuation remains exact. The plan/audit explicitly records the transform and does not claim raw latent equality after resampling.

## Evidence boundaries

The public source was synchronized from the repaired experimental line. Local component regressions and owner-reported manual acceptance do not establish a complete GPU retest of this sanitized public build. No new GPU acceptance was performed for publication. Full same-version six-segment GPU E2E and mixed-resolution automatic merge remain HOLD/NOT_TESTED; mixed-resolution merge still needs an explicit common output canvas.

The four assets in `assets/showcase` are redacted historical 8197 demonstrations, reused with authorization. They illustrate the interface and output only; they are not current 8207 GPU acceptance evidence. Original private prompts, input references, ledgers, model weights, caches, logs and private maintenance reports are excluded.

## Offline checks

Use a CPU-capable torch/safetensors environment and a reconstructed host (`<HOST>`):

```text
python -B tests/test_native_spatial_prefix.py --host <HOST>
python -B tests/test_prebake_runtime_contract.py --host <HOST>
python -B tests/test_release_guards.py
python -B tests/smoke_test.py
python -B scripts/verify/verify_integrity.py
```

The spatial test executes the actual Native preparation and audit classes against synthetic tensors. It never loads models or initializes CUDA. Repository privacy and hash checks cover the four binary assets through an exact filename/SHA whitelist.

The public portability adapter also retains the previously audited generic receipt protections (success, prompt identity and latent SHA). Legacy unbound receipts cannot bypass these checks. This sanitized adapter is not presented as byte-identical to the local runtime.

Publication regression: 48 executable CPU/JavaScript tests passed (11 spatial, 11 PreBake state, 9 release guards, 16 workflow helpers, 1 frontend/backend bridge), plus integrity, workflow sanitization and smoke checks. A clean pinned-source rebuild passed. No GPU or live browser acceptance is claimed for this public build.
