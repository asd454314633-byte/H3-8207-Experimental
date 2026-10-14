# Physical feasibility and body continuity

This is execution planning, not safety filtering or visual recognition.

## Lightweight state ledger

Record only the current story's relevant values, using `UNKNOWN` or `NOT_RELEVANT` where facts are unavailable:

- body, torso and pelvis orientation
- left/right leg and arm state
- weight distribution
- person/person, person/surface and person/prop contacts
- prop owner
- camera side

The end ledger of one segment must exactly match the next segment's start ledger. When the story changes a value, show that change through the next segment's micro-timeline.

## Conflict handling

Flag impossible simultaneous requirements such as a fixed torso, camera directly behind, and continuous frontal eye contact; an occluded limb teleporting; an unexplained prop handoff; or contact partners swapping positions. Preserve the requested action and intensity. Resolve the path by adding preparation/transfer/settle states or choosing a compatible three-quarter camera limit.

Never substitute global phrases such as `perfect anatomy`, `no extra limbs`, or `no deformation`. Positive physical descriptions are allowed only when they express the actual plan, for example keeping seated weight supported while one leg changes position gradually.

## Camera and recommendations

For geometry/occlusion risk, favor visibility and moderate perspective while retaining intent-driven camera motion. Do not impose a global static camera.

When body-geometry risk is high and no explicit body/pose reference was supplied, show a non-blocking suggestion for a clear, sufficiently large body or target-pose reference. Avoid recommending a multi-panel character sheet as the only body reference. For fast full-body motion, a higher effective-resolution suggestion is also non-blocking. Never change resolution, model, sampler, steps, backend, or AddGuide automatically.

Body Integrity QA happens after rendering and is not prompt text. Review visible limb count, hip-to-thigh continuity, duplicated/fused limbs or arms, abrupt proportion changes, occlusion recovery, and prop contact. Failure reruns only the affected segment. Human review is acceptable; no vision model is required.
