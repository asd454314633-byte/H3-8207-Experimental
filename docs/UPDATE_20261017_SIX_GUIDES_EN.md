# Six isolated user keyframes for the 8207 V29 director (2026-10-17)

The six-segment director now supports one optional user image per segment. Each card can upload an image and place it by zero-based frame, frame counted back from the end, or seconds. The feature defaults off and each segment is saved and snapshotted independently.

For segment 4 at 243 frames, “88 frames from end” compiles to visible/model frame 155. At 362 frames it compiles to frame 274. Ordinary Native continuation adds the protected 39-frame prefix after resolving a visible frame; Clean Rebase and independent starts add no offset. The automatic Clean Rebase seam image remains at frame 0, while a user keyframe is added to the final BasicGuider conditioning at its selected frame.

`GUIDE_ROUTING=PASS`: 56 CPU checks, 11 PreBake regressions, real frontend persistence checks, and two full managed graphs accepted by the 8207 server's `execution.validate_prompt`. All six-off paths matched the previous compiler. `GUIDE_VISUAL_GPU=HOLD`: no GPU job was submitted; visual behavior awaits a user-run recording and review. Long-song and cross-group GPU claims retain their prior evidence scope.

Nine runtime source files are hash-mapped in the package. No private prompts, user images, histories, latents, cached data, logs, or local execution graphs are included. The update does not modify 8197 or the frozen v0.2.1 release.

Full Agent Pack: [https://github.com/asd454314633-byte/H3-8207-Experimental/releases/tag/v0.2.2-full-agent-pack](https://github.com/asd454314633-byte/H3-8207-Experimental/releases/tag/v0.2.2-full-agent-pack). ZIP SHA256: 39898ebe30fa3d1c0321310358b7081c43be416bef8891c3d85c96e54d11f11b.
