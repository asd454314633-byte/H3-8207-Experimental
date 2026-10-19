# 2026-10-19 attempt-history / compiler sync evidence

Scope: public source/test artifacts only. No raw ledger, prompt, private screenshot, runtime log, media, credentials, or workstation-specific model registry is included.

- Regression fixture: 199 deidentified entries (198 parent-proven terminal histories; 1 retained unconfirmed).
- CPU regression: repeat scans emit one aggregate summary per evidence fingerprint; changed parent receipt reclassifies; exact live prompt identity remains guarded. Current test executes with no live service or GPU submission.
- Compiler rule regression: mocked HTTP only; ordinary/invalid Chinese input is not blocked; user-defined image responsibility is not forced. No GPU submission.
- Runtime boundary: 8207 was left running; edited module source is not active in its already-running Python PID until a safe future restart.
- Live online compiler results and screenshots remain in private local evidence because they contain user-facing prompt/UI content.
- GPU generation was not rerun. The new full package is a source/evidence package, not a new installation or GPU PASS.
