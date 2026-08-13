---
name: routing
description: "General Sol Advisor entrypoint for fail-closed routine, medium, hard, planning, and review routing."
---

# Sol Advisor routing

Call `get_setup_status` and `get_preferences` first. Schema-v1 state migrates
atomically to schema v2. Never change live preferences, install adapters, or use a
role until the user has explicitly asked for that action.

Call `resolve_route` with one task class and `currentRuntimeEvidence`. Inspector
evidence must state `evidenceSource="codex-rollout-inspector"`,
`executionContext="parent"`, and `agentIdentifier=null`. It compares the current
model, effort, observed runtime tier, and sandbox with the saved role. Treat a blocked
result as a stop. Do not infer missing evidence or select a fallback.

If the current route is exact and the task is not review, use the parent result. If it
differs, or the task is review, the result is `fresh_agent` and `spawn-required` until
separate `targetRuntimeEvidence` proves the generated identifier, model, effort, tier
when exposed, and sandbox. Target evidence must instead state
`executionContext="agent"` and the canonical nonempty generated identifier. A target
mismatch blocks.
Reviews are always fresh. `escalated` is true exactly for a fresh agent.

- Routine maps to `roles.routine`.
- Medium maps to compatibility storage `roles.high` and `sol_advisor_high` on
  Codex.
- Hard maps to `roles.hard`. A schema-v1 migrated hard role is unavailable until
  the four-role preview receives its separate consent and fresh runtime discovery
  proves the configured route.
- Planning and review map to `roles.advisor`; review always uses a fresh read-only
  agent when host evidence proves read-only isolation.

Machine tier defaults to `default` and presents as **Standard**. Output keeps requested,
saved, and observed tiers separate. Standard can report observed tier unavailable. Fast
presents as **Fast**, requests runtime tier `priority`, and is allowed only for one bounded
`routine` route whose configured role is exactly Luna / max. It has no fallback.
Fast blocks unless priority is observed. If that task expands, restart it as Luna/default.

Keep `fork_context=false` and parallelism at one. Enforce route budgets:

- Routine, medium, hard: 50 tools, 5M raw tokens, first compaction.
- Planning, review: 25 tools, 2.5M raw tokens, no compaction.
- Fast: 10 tools, 1M raw tokens, no compaction.

Return at most 8KB or 200 lines. Use a handoff of at most 2,000 tokens, batch
independent reads, and never carry raw logs or unchanged context. Escalate only when
the selected route changes.
