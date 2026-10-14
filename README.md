# H3-8207 Experimental

[v0.1.0-preview](https://github.com/asd454314633-byte/H3-8207-Experimental/releases/tag/v0.1.0-preview) · experimental, source-only pre-release.

![Historical redacted showcase](assets/showcase/showcase-cover.jpg)

[Video demonstration](assets/showcase/h3-six-segment-demo-github.mp4) · [animated preview](assets/showcase/demo-preview.gif) · [redacted six-segment panel](assets/showcase/six-segment-panel-redacted.png)

These four assets reuse historical 8197 demonstrations. They are not proof that this 8207 preview passed GPU end-to-end acceptance.

This preview adds immutable Story/Execution snapshots, editable queued work, per-segment cache planning, and explicitly audited cross-resolution Native latent continuation. [Release notes and limitations](docs/PREVIEW_RELEASE_NOTES.md).

# H3-8207 Experimental

H3 Chinese Director experimental source package. **EXPERIMENTAL_PUBLICATION_READY = PASS** for an experimental, source-only release. This status does not claim production readiness or current-candidate automated GPU end-to-end acceptance.

The package separates four layers:

1. **H3 six-segment generation** is the core video workflow. Users may enter the six segment prompts manually.
2. **AI Director** is optional. It can help draft or coordinate segment prompts through a compatible language model provider; no single provider is required.
3. **MiniMax-H3's internal Qwen3-VL encoder** is part of the H3 model stack used by H3 workflows. It is distinct from the standalone Qwen Image 2.1 image-generation model.
4. **Qwen Image 2.1** is a separate optional set of four still-image workflows: text-to-image, single-image edit, multi-image edit, and background removal. It is not a prerequisite for H3 six-segment video generation.

## Acceptance status

- Historical evidence is version-scoped: 8197 V29 has an automated six-segment generation-and-merge `PASS`; the 8207 historical experimental environment has user-confirmed manual acceptance plus partial automated GPU evidence. These records remain in the private audit with their original limits.
- Current-candidate CPU contract, source reconstruction, integrity and release-guard checks passed within their recorded scope. They do not establish current-candidate video generation or live UI/queue behavior.
- The four Qwen Image 2.1 workflows have historical GPU `PASS` records. The sanitized workflows in this candidate have not been dynamically revalidated: `CURRENT_CANDIDATE_QWEN_GPU = NOT_RETESTED`.
- `GPU E2E = NOT_TESTED` refers specifically to a complete same-version retest of the current 8207 sanitized release candidate. It does not erase the historical 8197 PASS or partial 8207 GPU evidence, and it is not reported as a current-candidate PASS.

See [Feature and Evidence Matrix](docs/FEATURE_MATRIX.md), [Publication Gate](PUBLIC_RELEASE_GATE.md), [Build and Reproducibility](REPRODUCIBILITY_REPORT.md), [Blocker Resolution](docs/BLOCKER_RESOLUTION.md), [Third-Party Notices](THIRD_PARTY_NOTICES.md), and [Privacy Sanitization](PRIVACY_SANITIZATION_REPORT.md).

The source package contains no model weights, private reference media, or runtime caches. Each third-party component retains its own license and notices. The experimental readiness decision is limited to the audited source package, its documented reconstruction path, and the evidence distinctions above. No production promotion is claimed. This repository is the independent experimental preview.
