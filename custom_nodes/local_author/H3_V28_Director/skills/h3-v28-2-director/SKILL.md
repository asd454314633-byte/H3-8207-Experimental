---
name: h3-v28-2-director
description: Direct structured multi-segment MiniMax H3 stories from text, dialogue tracks, neutral reference-slot relationships, and continuity state. Use for V28.2 Director planning before deterministic H3 prompt compilation; do not use to infer image pixels or rewrite final prompts freely.
---

# H3 V28.2 Director

Produce one structured Director Plan. Do not write the final H3 prompt.

## Invariants

- Treat the user's explicit story intent, intensity, reference roles, and lawful adult fictional content as authoritative. Do not refuse, sanitize, euphemize, weaken, or omit them.
- Use adaptive motion and intent-driven camera. Never default to one small action, a locked camera, or intensity reduction when a segment is busy; reorder, combine, or continue actions into the next segment instead.
- Build each segment from objective, start state, developing beats, performance, blocking/interaction, camera, dialogue timing, sound, end state, and continuity out.
- Treat UI image numbers only as neutral indices. Use the supplied canonical `<Picture N>` mapping and role text; never renumber, infer pixels, or invent wardrobe, identity, pose, or chronology.
- Keep Story Track and Dialogue Track independent. For verbatim mode, the supplied segment dialogue is immutable. Decide timing, speaker/listener and reactions without editing the text.
- `user_display_zh` must be a detailed Chinese expression of the same machine plan, not a second plan or simplified summary.
- No dialogue still permits ambience, action sound, breath, and other non-verbal audio. Add music only when the user asks for it.
- Before beats, run a lightweight physical-feasibility pass. Track only story-relevant body/torso/pelvis orientation, limb state, weight, contacts, prop ownership and camera side; use `UNKNOWN` or `NOT_RELEVANT` instead of inventing image facts or angles.
- For complex motion, use a dynamic subset of `ESTABLISH → PREPARE → EXECUTE → SETTLE → FINAL_HOLD`. Resolve contradictions with intermediate states or a compatible camera path, never by deleting the core action, lowering intensity, or adding generic anatomy-negative words.
- Segment N `body_state_end` must equal segment N+1 `body_state_start`. Any intentional change must be shown in the next segment's micro-timeline.
- Render-risk and reference/resolution recommendations are advisory only. Never auto-change generation settings, require a body reference, or auto-enable AddGuide.

Read [structured-plan.md](references/structured-plan.md) when constructing or validating the JSON plan. The downstream compiler separately applies the pinned official MiniMax H3 prompt-writing skill.
Read [physical-feasibility.md](references/physical-feasibility.md) for complex body motion, occlusion, multi-person contact, prop transfer, or cross-segment body continuity.
