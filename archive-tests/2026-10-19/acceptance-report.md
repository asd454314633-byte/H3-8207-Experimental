# 2026-10-19 8207/8210 Recovery Acceptance Report

## Current runtime snapshot

- 8207: `127.0.0.1:8207`, listener PID 23548; queue running 0, pending 0.
- 8210: `127.0.0.1:8210`, listener PID 44116; compiler health 200 and same-origin proxy health 200.
- Existing History prompt `481b2639-9b76-4cef-a72e-86822259529b`: success/completed, output `LongSong_20261016/segment_00059_.mp4`, 4,604,391 bytes, SHA256 `610E19B1866FBFFA602CB72AFE87C754A31880F2BB4146A7AC223A49D9394B05`.
- No GPU task was submitted for this compiler-preview acceptance.

## Real compiler preview

The plain Chinese raw prompt was: “林薇在雨后的街道上慢慢走向路灯，停下脚步，抬头看向夜空。” The browser called 8210 through the existing 8207 same-origin proxy. 8210 returned a complete official-format prompt and its validator returned `valid=true` in 3.081 seconds. The live workflow had 9 connected pictures, 0 videos, and 1 audio; pictures were sent with empty `role_id`, `purpose`, and `note`. The compiler preview did not alter the six-prompt source textarea and did not queue GPU work.

The full returned prompt is in `test-results.json`.

A separate real 8210 compile attempt with no connected picture/video returned `Ref2VA 至少需要一张已连接的参考图或参考视频。` The preview result was `RAW_FALLBACK`, and the prospective used text equaled the original Chinese prompt exactly.

## Regression tests

- Independent compiler rules: PASS.
- PreBake branch recovery: 2/2 PASS.
- PreBake CPU regression: 11/11 PASS, with CUDA disabled and temporary synthetic fixtures.
- JavaScript syntax checks: PASS for the compiler, extension integration, and preview UI module.

## Scope and exclusions

Only 8207-side source and a small 8207 lifecycle patch are included. Frozen 8210 app sources were not changed. Raw listener logs, screenshots, prompt histories, original videos, model files, and any credentials are excluded. Existing local forensic evidence and outputs remain in place. A private local copy of `listener_watch.log` (11,278 bytes; SHA256 `4B19C933C946D38370C47912ED63F094712DC24412BDF55C93913057AF94425F`) and `listener_forensics.log` (284,234 bytes; SHA256 `6EA12468515C99A2D1280CAADB894421E2C7BE6B1EFF594F184F8E0D2C4A1931`) is stored under the local `evidence_private/2026-10-19/` directory. Neither log is in this public package.

The live BrowserOS workflow was not reloaded or restarted in this capture to protect its unsaved state. The new preview module was loaded into that existing tab for actual online acceptance.
