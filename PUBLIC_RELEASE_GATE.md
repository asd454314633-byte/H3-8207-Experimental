# Experimental Publication Gate

## 2026-10-14 main update: Adaptive V1 and a real local six-segment run

**Adaptive V1 is promoted on local 8207 and passed real History recovery, original-player refill and complete playback.** Six validated files are synchronized byte-for-byte. Metadata/types/topology discovery, 24 vs 24.0 normalization, immutable task snapshots and semantic workflow versions do not hardcode nine references, a private story or node IDs. Missing capabilities are still reported.

**LOCAL_8207_GPU_E2E_PASS=PASS:** the later independent PDD Ref2VA 8-step six-segment run has six SUCCESS receipts, exact histories, Native outputs, clips and a successful automatic merge. Measured 1056×608/24fps; merged output is 1302 frames / 54.25 seconds, not the earlier failed single clip or planned approximately 60-second setup. Matching-window VRAM/RAM peaks are NOT_RECORDED.

**PUBLIC_SOURCE_MATCH=PASS for the six listed files; PUBLIC_BUILD_GPU_E2E=NOT_TESTED.** Local success is not a guarantee for every sanitized installation. The existing 48 public regressions, 49 private Adaptive checks and actual GPU executions are separate evidence sets. The v0.1.0-preview tag/assets stay frozen; use main for the new source.

[Adaptive V1 guide](docs/ADAPTIVE_V1.md) · [Measured acceptance report](docs/8207_SIX_SEGMENT_GPU_ACCEPTANCE_20261014.md) · [Machine-readable data](benchmarks/8207_six_segment_20261014.json)


`EXPERIMENTAL_PUBLICATION_READY = PASS`

Scope: local technical readiness of the audited, source-only experimental package. This is not production promotion and does not state that current-candidate GPU end-to-end tests passed.

| Gate | Result | Scope and limit |
|---|---|---|
| Source privacy, attribution, licenses, and Git/package history | PASS | Fresh export and reachable Git-object privacy scans, exact four-asset hash whitelist, private prompt fingerprint comparison; package provenance and excluded HOLD files remain as documented. No third-party component is relicensed as H3/MIT. |
| Fixed-source reconstruction and dependency source acquisition | PASS | Fixed H3/ComfyUI source, hash-checked GPL host patch, 11/11 Qwen target file reconstruction, and two formerly unpinned optional dependency sources were verified in clean isolated directories. This is source acquisition/reconstruction, not model or runtime deployment. |
| Current-candidate CPU/static contracts | PASS | Eleven PreBake runtime state/safetensors CPU checks and eleven synthetic spatial Native checks, one front-end-to-back-end state bridge, release guards, integrity, sanitization, smoke, and existing JavaScript suite passed in their logged scopes. DOM/ComfyUI queue/video transport was not exercised. |
| 8197 V29 six-segment automated generation and merge | PASS (HISTORICAL) | Historical automated generation-and-merge acceptance applies to the 8197 V29 version. It is retained as historical evidence, not transferred to the 8207 release candidate. |
| 8207 historical experimental six-segment evidence | MANUAL_ACCEPTANCE = USER_CONFIRMED; PARTIAL GPU EVIDENCE | The owner confirms prior manual success. Historical GPU/Latent/PreBake/Prompt/receipt records remain with their original identity and version limits. |
| H3 six-segment manual functionality | USER_CONFIRMED | The project owner confirms prior real manual acceptance. No new GPU test was run. |
| H3 six-segment automated GPU E2E for the current 8207 sanitized release candidate | NOT_TESTED | No complete same-version current-candidate six-video run or end-to-end receipt chain was generated in this correction. This does not mean the historical 8197 V29 automated PASS or partial 8207 historical GPU evidence never occurred. |
| Qwen Image 2.1 historical GPU runs | PASS (HISTORICAL, 4/4) | Four independent still-image workflows have historical execution records. Their current sanitized candidate payloads have not been dynamically revalidated. |
| Qwen Image 2.1 current-candidate GPU runs | NOT_RETESTED | Qwen Image is optional and independent of H3 six-segment video; this extension-specific gap does not block experimental source publication. |
| AI Director providers | OPTIONAL / NOT_REQUIRED | Manual six-prompt entry is supported. A compatible language-model provider may be configured; no single provider is mandatory. Provider-specific live inference is not claimed by this gate. |

`PUBLICATION_APPROVED = PASS (EXPERIMENTAL SOURCE SCOPE ONLY)`

`PRODUCTION_PROMOTION = HOLD`

`GITHUB_PUBLICATION = v0.1.0-preview (independent experimental repository)`

Users must follow the build and third-party installation instructions, obtain models separately, and configure model paths. This gate does not claim live setup, node registration, video quality, provider connectivity, or current-candidate automated GPU E2E success. The separately archived historical results and the user's manual acceptance remain accurately labeled.


## 2026-10-17 同步增补

[10月16日能力、修复及分级验收](docs/UPDATE_20261016.md)。长歌/音频起点/跨组接续源码已同步，默认跨组关闭；原12图和旧发布保留。公开包GPU和跨组GPU仍NOT_TESTED/HOLD；历史验收仅适用于其日期和所测范围。
