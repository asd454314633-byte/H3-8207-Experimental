# H3-8207 Experimental

**MiniMax-H3 six-segment video generation with a Chinese ComfyUI director console** · `v0.1.0-preview` experimental pre-release

[中文版 README](README.md) · **[Download v0.1.0-preview](https://github.com/asd454314633-byte/H3-8207-Experimental/releases/tag/v0.1.0-preview)** · [Choose a workflow: 12-file guide](workflows/current/README.md) · [8197 frozen production repository](https://github.com/asd454314633-byte/H3-Chinese-Director)

Write a story as six independently editable prompts, submit video jobs, and continue from a real predecessor Latent. The project provides a Chinese interface, continuous-job scheduling, PreBake caching and result merging as an **experimental source preview**, separate from the 8197 production line.

**Explore:** [All experimental capabilities, modes, 48 tests and evidence limits](docs/CAPABILITIES_AND_EVIDENCE.md) · [12 workflow JSON selector](workflows/current/README.md) · [frozen 8197 production release](https://github.com/asd454314633-byte/H3-Chinese-Director).

### Experimental capabilities beyond the six-prompt panel

| Area | Implemented interface / experimental direction | Validated scope |
|---|---|---|
| Six-part storytelling | Independent draft, submission, continuous or independent execution, segment resume | Public code and workflow; **no current public GPU E2E** |
| Edit while jobs are queued | Separated **Story vs Execution** snapshots, per-attempt identity, queue isolation | CPU/JS contracts, **not a live browser/ComfyUI queue E2E** |
| Native latent continuity | Real preceding latent, receipt and SHA checks; spatial resampling of the video prefix when the sampling grid differs | **11 Native CPU tests PASS**; current GPU video quality not re-tested |
| **Voice timbre references** | Three reference-voice slots, optional source-video soundtrack, `<Audio N>` and speaker/role mapping, format and duration checks | Published Ref2VA / 8-step source interface; **current preview has no live GPU voice-clone-quality acceptance** |
| PreBake cache and recovery | Dependency-scoped cache preparation, identity validation and legitimate prior-version retention | **11 PreBake CPU tests PASS** |
| Model/reference choices | Ref2VA multi-reference, FL2VA single/first-last frame, alternative sampling, attention and audio/video routes | Branch existence is **not** proof that every combination passed live tests |
| Other experimental tracks | Guide/Pose/Depth, V2V/RV2V, optional image generation/editing/Qwen workflows | Partial/bypassed or independent; historical Qwen **4/4 GPU** not repeated |
| Multi-segment merge | Selection and merge hooks | **Mixed-resolution automatic merge remains HOLD** |

**Verified preview regression: 48 CPU/JavaScript PASS / 0 FAIL** (11 spatial Native + 11 PreBake + 9 release guards + 16 workflow helpers + 1 frontend/backend bridge). **193 sanitized JSON workflows** = 12 current + 181 history; these are *files statically checked*, **not GPU generations**. Public preview's complete six-segment GPU and browser/live queue E2E remain **NOT_TESTED**.

See [the complete evidence-scoped catalog](docs/CAPABILITIES_AND_EVIDENCE.md) and [publication gate](PUBLIC_RELEASE_GATE.md).


![Historical H3 Chinese director showcase cover](assets/showcase/showcase-cover.jpg)

## Real interface and video showcase

### Animated video preview

![Historical real H3 video animated preview](assets/showcase/demo-preview.gif)

**[▶ Open the complete MP4 demonstration](https://github.com/asd454314633-byte/H3-8207-Experimental/blob/main/assets/showcase/h3-six-segment-demo-github.mp4)**

This link opens the actual MP4 repository file page; use Download raw file to download it. It does not promise an embedded README video player.

### Six-segment Chinese editor

[![Redacted six-segment editor screenshot — click for original size](assets/showcase/six-segment-panel-redacted.png)](https://raw.githubusercontent.com/asd454314633-byte/H3-8207-Experimental/main/assets/showcase/six-segment-panel-redacted.png)

Click the screenshot for its original dimensions. Story text is redacted; the interface comes from a real recording.

> **Provenance and evidence boundary:** These four assets reuse historical real 8197 recordings and redacted demonstrations. They show the real interface and video output, **not same-version GPU E2E acceptance of the current public 8207 candidate**. Other features or captions appearing in the full recording do not automatically count as this project's acceptance results. No new operating screenshots were generated or fabricated.

## Core six-segment capabilities

| Capability | Behavior and boundary |
|---|---|
| Chinese interface and six-prompt management | Write, edit and manage each prompt separately. Manual writing needs no AI Director model. |
| Single-segment and continuous scheduling | Start a selected segment independently or continue from a valid predecessor. Edit future drafts and click execute to queue jobs while another job runs. |
| Previous-segment Latent continuation | Real Native masked continuation preserves predecessor identity, model and receipt checks. Independent start remains available without a valid predecessor. |
| Conditioning PreBake | Reuse valid conditioning and handle missing or stale caches according to submitted content and actual dependencies. Cache hits do not replace data validation. |
| Continuation state and execution receipts | Story, execution snapshots, task identity and successful results are recorded separately for recovery, retries and predecessor eligibility. |
| Six-segment automatic merge | Merge selected valid results without mixing other stories or old attempts. **Mixed-resolution automatic merge remains HOLD.** |

These are source/workflow capabilities. Historical success and current public-candidate acceptance are separated below; offline checks are not current GPU success.

## Experimental changes relative to 8197

8207 reuses a public 8197 baseline with experimental nodes and workflows. It is an independent line, not an automatic upgrade to production.

- **Story / Execution separation:** Story identity can stay stable while each submission has an independent snapshot. Later draft edits do not rewrite submitted work.
- **Editing and queueing during generation:** Keep editing unsubmitted prompts and submitting jobs. Queue waiting is separate from the 300-second execution budget.
- **Per-segment PreBake recovery:** Plan caches from actual submitted content and dependencies, preserving successful historical versions and real predecessor checks.
- **Explicitly audited spatial continuation:** For cross-resolution continuation, map the real predecessor's video Latent tail to the current sampling grid. Audio prefixes remain exact; same-grid continuation remains elementwise exact. The transform is recorded, without claiming raw tensor equality after resampling.
- **Experimental workflows and extensions:** H3 experimental orchestration and separate Qwen Image 2.1 image workflows have their own dependencies, models and evidence boundaries.

See the [current preview notes](docs/PREVIEW_RELEASE_NOTES.md). Older delta reports retain historical scope and do not establish dynamic acceptance of every experiment.

## Using the six-segment workflow

1. Prepare required nodes and models in a separate ComfyUI environment. Load a suitable JSON from [current workflows](workflows/current), then configure your own references and model paths.
2. Fill the six Chinese prompt editors and set reference slots, generation parameters and starting segment. Write manually or use the optional AI Director to draft prompts.
3. Choose independent generation or real continuation and execute the selected segment. Jobs can still be queued while another runs. Submitted jobs retain fixed snapshots; edits apply to the next submission.
4. For continuation, use a matching successful predecessor Latent and receipt. Resume from a valid position after failure and preserve historical successes when redoing a segment. Check selected result versions and video dimensions before merging.

Arbitrary historical videos or Latents are not valid predecessors. Cross-resolution Native continuation and mixed-resolution output merging are separate issues; the latter still requires a common output canvas.

## AI Director, Qwen and the six prompt editors

| Layer | Role | Relationship to six-segment video |
|---|---|---|
| **H3 six-segment director console** | Core video control: prompts, generation, continuation and results. | Manual prompt editing does not require an AI Director. |
| **Optional AI Director** | Assist with drafting or improving story prompts. | Different compatible language-model services can be used; no single model is mandatory. |
| **MiniMax-H3 internal Qwen3-VL encoder** | A required internal component of the H3 video model stack. | Distinct from the optional AI Director and Qwen Image. |
| **Qwen Image 2.1** | Separate experimental text-to-image, single-image edit, multi-image edit and background-removal workflows. | **Not a prerequisite for H3 six-segment video.** Its acceptance gates do not block the six prompt editors. |

## Installation, downloads and source reconstruction

- **[Release downloads and SHA256 attachments](https://github.com/asd454314633-byte/H3-8207-Experimental/releases/tag/v0.1.0-preview):** Source ZIP, complete file manifest and `SHA256SUMS.txt`. The existing tag/assets remain unchanged; homepage changes on main do not alter that frozen source archive.
- **[Workflow selector: all 12 JSON files](workflows/current/README.md):** **wf_05** is the six-segment H3 video workflow; most other files are independent image experiments. Select by actual purpose, not numeric order. Open the relevant file with GitHub Raw / Download; replace sanitized placeholders and paths.
- **[Reconstruction and configuration guide](REPRODUCIBILITY_REPORT.md):** [Pinned versions](config/baseline.lock.json), [rebuild script](scripts/rebuild/rebuild_from_8197.py), [dependency setup script](scripts/setup/install_deps.py) and [model-path example](config/examples/extra_model_paths.example.yaml). Use separate empty directories; do not overwrite production.
- **[Dependency sources](config/third_party_nodes.json)** and [locked versions](config/third_party_nodes.lock.json): Obtain model weights, third-party runtime dependencies and optional services separately. Source acquisition/reconstruction is not runtime installation acceptance.

No model weights, private references, runtime caches or ready-made personal environment are bundled. Read older reconstruction blockers together with the [R2 corrections](docs/BLOCKER_RESOLUTION.md), [current publication gate](PUBLIC_RELEASE_GATE.md) and [preview notes](docs/PREVIEW_RELEASE_NOTES.md).

## Version-scoped acceptance and limitations

| Scope | Evidence and result |
|---|---|
| **8197 V29 production** | Historical Agent-automated six-segment generation and automatic merge have real **PASS** records. They do not transfer to this candidate. |
| **Historical 8207 experimental environment** | User-confirmed successful manual acceptance and partial automated GPU evidence retain their original versions and scope. |
| **Current sanitized public 8207 candidate** | `EXPERIMENTAL_PUBLICATION_READY = PASS`; `GPU E2E = NOT_TESTED`; `PRODUCTION_PROMOTION = HOLD`. |
| **Qwen Image 2.1** | Four historical GPU **PASS** results remain valid; current-candidate dynamic validation is `NOT_RETESTED`, separate from H3 six-segment acceptance. |

`NOT_TESTED` means the current public candidate has not repeated a **complete same-version GPU E2E** test. It does not mean six-segment generation never succeeded. The recorded 48 CPU/JavaScript checks, static integrity and pinned-source reconstruction passed; they do not establish current-candidate live browser, queue or video E2E acceptance. This homepage update adds no GPU acceptance.

**Known limitations:** Mixed-resolution automatic merge remains **HOLD** and needs an explicit common output canvas. Complete current-candidate six-segment GPU E2E is untested; current Qwen dynamic validation has not been repeated; full runtime equivalence remains HOLD. Configure required sources, models and optional services before using their respective features.

Evidence: [Publication gate](PUBLIC_RELEASE_GATE.md) · [Preview notes](docs/PREVIEW_RELEASE_NOTES.md) · [Recorded preview offline checks](manifests/preview_validation.json).

## Licenses, provenance and privacy

Independent project code is declared under [MIT](LICENSE). Third-party components retain their own licenses and attribution; the model, host and upstream nodes are not collectively claimed as original project code or MIT. ComfyUI host patches follow GPL-3.0; workflow-template derivatives and vendored nodes retain their respective sources and notices. No official MiniMax or ComfyUI endorsement is implied.

Read [Third-party notices](THIRD_PARTY_NOTICES.md), [license report](THIRD_PARTY_LICENSE_REPORT.md), [GPL patch license](overlays/LICENSE-GPL-3.0.txt) and [workflow-template license](licenses/workflow_templates-MIT.txt). Model use is subject to each model's own license.

Private paths, original story text, input references, ledgers, caches, logs, secrets and model weights are excluded. The four historical showcase assets are redacted and retain their original bytes. See [Sanitization report](PRIVACY_SANITIZATION_REPORT.md) and [Security and privacy](docs/SECURITY_AND_PRIVACY.md).

## 中文文档

[阅读完整中文版 README →](README.md)
