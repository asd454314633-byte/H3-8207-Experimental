# Structured Director Plan contract

Each segment contains:

- `segment`, `duration`, `segment_objective`
- `start_state`, `beats[]`, `new_action`
- `performance`, `blocking`, `interaction`, `camera`
- `reference_usage[]`
- `dialogue`, `dialogue_timing`
- `ambience`, `physical_sounds`, `non_verbal_vocals`, `music`
- `end_state`, `continuity_out`
- `body_state_start`, `body_state_end`
- `micro_timeline[]`: `phase`, `action`, `state_change`
- `physical_conflicts[]`, `conflict_resolution`, `physical_continuity_notes[]`
- `anatomy_camera_notes`
- `render_risk`: `body_geometry`, `occlusion`, `fast_full_body_motion`
- `planning_advisories[]` (derived, non-blocking UI information)
- `user_display_zh`: `objective`, `start_state`, `action_progression`, `blocking`, `camera`, `dialogue`, `sound`, `reference_usage`, `end_state`

For two or more people, blocking must make initiator, reactor, positions, orientations, attention, distance change, speaker/listener and non-speaker reaction unambiguous.

Beats are complexity-driven, not fixed. A simple ten-second segment may need one or two; a complex segment may need two to four or more when executable timing permits.

Continuity out records only the state needed by the next segment: position, orientation, interaction, changed props or wardrobe, dialogue progress, camera/scene state, and unfinished action.

Low-risk motion should remain concise. Detailed micro-timeline and positive body-state language enter the compiled H3 prompt only for medium/high geometry or occlusion risk.
