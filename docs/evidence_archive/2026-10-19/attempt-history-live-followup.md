# 2026-10-19 attempt-history live follow-up

## Scope and safety

Observed the existing 8207 process and its existing console log without restarting the service, submitting work, stopping processes, or editing the production ledger. Queue and History were read through the local API. The sanitized 198-record regression fixture was used for all code-path tests; the raw ledger and raw console log are not part of this report or the public package.

## Evidence

- At the API snapshot, `/queue` reported no running or waiting prompts and `/history` returned an empty object.
- During a continuous 60-second observation, the existing `instances/h3-lab/console.log` remained unchanged in byte size and last-write time. No new instance of the reported recovery error was written during that window.
- Full-log parsing found 796 matching error records across 199 distinct ledger/attempt identities. They formed four 199-record bursts, each immediately following a `Starting server` line. This is evidence of repeated startup scans in the saved log, not a 0.25-second repeating error loop during the observation window.
- The active process was started at 20:03:06 local time. Its startup marker reported lifecycle source SHA256 `3715e559089345e199be0134b3cde40b2616ba22ff685df22dfdb7bd9cfda112`. The current local source has SHA256 `5448c05ddd66b086a844a370440d14f830e04538f7bd05e7b9a657828c59ba0d`; the GitHub main checkout and full-capability source copy match the current local source. The process therefore has not loaded the current scanner classification patch.
- The old scanner treated every attempt whose immutable identity differed from the ledger execution as an ERROR. Older fork ledgers can retain a parent's completed attempt in a child execution record; the old scanner did not classify its parent provenance and terminal receipt before reporting the mismatch.
- Current `attempt_lifecycle.py` first separates mismatched historical candidates from current execution attempts, verifies parent execution ancestry, exact attempt/prompt identity, parent receipt identity, and terminal state before classifying a record as verified historical. Unproven records stay unconfirmed and are not recovered. Audit output is fingerprinted and emitted again only when the evidence state changes. Current-execution attempts remain subject to exact prompt ID and execution identity checks.

## Regression results

`test_attempt_history_classification.py` passed 2/2 against the local runtime source, GitHub main source, and full-capability directory source. The 30-scan fixture regression produced one audit summary, no repeated ERROR, preserved one valid in-flight parent task under its exact prompt ID, kept all 198 verified historical child attempts and one unconfirmed attempt out of recovery, reclassified when receipt evidence changed, and left the fixture bytes unchanged. The measured test CPU time was below 0.2 seconds per source copy.

## Status

The source fix and regression are present in local, GitHub main, and full-capability source. Runtime activation remains **HOLD**: the running 8207 process loaded the older SHA, and this follow-up deliberately did not restart it. No GPU task was submitted. GPU generation and public-package installation remain **NOT_TESTED / HOLD**.
