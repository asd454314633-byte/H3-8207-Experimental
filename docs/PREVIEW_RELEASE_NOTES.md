# v0.1.0-preview — creative editing and Native continuation

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
