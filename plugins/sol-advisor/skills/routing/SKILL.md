---
name: routing
description: "General Sol Advisor entrypoint for fail-closed routine, medium, hard, planning, and review routing."
---

# Sol Advisor routing

Call `get_setup_status` and `get_preferences` first. Schema-v1 state migrates
atomically to schema v2. Never change live preferences, install adapters, or use a
role until the user has explicitly asked for that action.

Call `resolve_route` with a task class first, without runtime evidence. It returns a
cryptographically random, task/profile/tier-bound, short-lived single-use `challenge`.
This result does not select or finalize a route. Then invoke the pathless inspector
exactly as `sh inspect-agent-runtime.sh --challenge <challenge> <thread-id>` and pass
its complete camelCase JSON object directly as `currentRuntimeEvidence` or
`targetRuntimeEvidence`, together with the same top-level `challenge`. Do not rename,
trim, or reconstruct fields. Treat a blocked result as a stop.

If the current route is exact and the task is not review, use the parent result. If it
differs, or the task is review, the result is `fresh_agent` and `spawn-required` until
separate `targetRuntimeEvidence` proves the generated identifier, model, effort, tier
when exposed, and sandbox. The active challenge remains in that output. The target
must use a different thread ID, a latest event at or after challenge issuance, no more
than the bounded future-clock skew, and the same unconsumed challenge. Replayed,
expired, old, unknown, or secret-bearing evidence blocks. `spawn-required` preserves
the active challenge. Accepted parent or target proof consumes it. Blocked provenance,
same-thread evidence, or a target mismatch invalidates it and requires a new route
challenge.
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

Before a generated-role spawn, inspect the actual native spawn tool. It must expose the
exact generated `agent_type` returned by the resolver. If the tool or type is absent,
stop immediately. Never search for it through a shell, retry, or use `codex exec` as a
fallback. Spawn with `fork_context=false` and parallelism one. Enforce route budgets:

- Routine, medium, hard: 50 tools, 5M raw tokens, first compaction.
- Planning, review: 25 tools, 2.5M raw tokens, no compaction.
- Fast: 10 tools, 1M raw tokens, no compaction.

Return at most 8KB or 200 lines. Use a handoff of at most 2,000 tokens, batch
independent reads, and never carry raw logs or unchanged context. Escalate only when
the selected route changes.
