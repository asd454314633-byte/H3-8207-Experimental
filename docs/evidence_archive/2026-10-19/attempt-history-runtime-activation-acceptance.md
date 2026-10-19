# 2026-10-19 8207 PreBake runtime activation and stability acceptance

This report supplements the earlier live follow-up, which recorded runtime activation as HOLD before a safe restart. The current process now loaded the classified-attempt patch.

## Runtime evidence

- After queue and GPU safety checks, the existing managed instance was stopped and restarted once. The manager returned a new listener identity and generation; one listener remained attached to the same new server process for the observation window.
- The startup log recorded `attempt_lifecycle.py` SHA256 `5448c05ddd66b086a844a370440d14f830e04538f7bd05e7b9a657828c59ba0d`, matching the local, GitHub `main`, and packaged source.
- Startup classification reported 198 verified terminal parent attempts and one unconfirmed record kept isolated. The unchanged-history identity error did not recur after the patch load.
- Direct requests to `127.0.0.1:8207` with proxy bypass returned HTTP 200 for `/system_stats`, `/queue`, and `/history` at all 60 samples across 1,813.273 seconds. Each sample created three separate `Connection: close` requests. Listener ownership and server process identity remained stable.
- The existing browser tab also completed same-origin fetches for those three endpoints.
- A running queue task appeared during the observation. It was left untouched: no prompt or History contents were inspected, and no task was cancelled, retried, or resubmitted. At the final sample the queue reported one running and zero pending.
- The independent 8210 managed compiler listener returned HTTP 200 from `/api/health`; its scheduled task remained running.
- The sanitized 198+1 attempt-classification regression passed 2/2 against the distribution source and fixture. No GPU job was submitted by this repair.

## Acceptance boundary

`8207_RUNTIME_STABILITY=PASS_WITHIN_30_MINUTE_WINDOW`. This records the measured local window only; it is not a long-term guarantee. GPU generation, fresh public-package installation, and GPU quality remain `NOT_TESTED` / `HOLD`.