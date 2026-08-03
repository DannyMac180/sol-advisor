---
name: orchestration
description: "Codex-native architect and delegation workflow using one separately installed GPT-5.6 Terra custom agent at high reasoning for all implementation and a fresh GPT-5.6 Sol reviewer at high reasoning with a requested read-only profile. Use for delegated implementation, multi-task builds, features, bug fixes, refactors, migrations, five-part implementation specs, parent verification, commitment-boundary advice, and final independent-context Sol review."
---

# Sol Advisor Orchestration

Act as the architect. Own the user's intent, architecture, decomposition, complete
implementation specification, parent verification, and final acceptance. Delegate all
implementation to the native Terra / High role, then require a fresh Sol verdict before
reporting the deliverable complete. These are native Codex custom-agent threads, not a
nested Codex CLI wrapper or a global default-subagent setting.

Read [references/role-contracts.md](references/role-contracts.md) before the first
delegation in a session.

## Confirm the primary session

Run the primary Codex session on gpt-5.6-sol with high reasoning. Verify the current
model and effort when runtime metadata exposes them. If either differs, tell the user
to select Sol / High and stop before delegation. If runtime metadata does not expose
them, ask the user to confirm Sol / High and stop until confirmed. A skill cannot
change the primary model itself; never assume or claim this prerequisite is satisfied.

## Preflight the companion custom agents

The two role files are user-owned native custom-agent TOML files. Installing or
updating the plugin does not automatically register them. Install them separately and
start a fresh Codex task so native discovery sees the current profiles.

Before every delegation, complete steps 1-2. After spawning a lane, complete steps
3-4 before accepting its result:

1. Resolve `../../scripts/install-agents.sh` relative to this SKILL.md and run its
   non-mutating exactness check:

   ~~~sh
   skill_dir=<directory-containing-this-SKILL.md>
   installer="$skill_dir/../../scripts/install-agents.sh"
   sh "$installer" --check
   ~~~

   It must exit zero. This proves Terra and Sol match the shipped templates exactly
   and the retired Luna companion file is absent. If the check reports a missing,
   stale, unsafe, or conflicting file, stop the affected lane. Give the user the
   installer path and reported destination. Never work around failure with another
   agent, model, or effort.

2. Inspect the native spawn tool's available `agent_type` entries. Both exact names
   must be exposed:

   - `sol_advisor_terra_implementer`
   - `sol_advisor_sol_reviewer`

   If either is missing, tell the user to install/check the companion files, start a
   fresh task, and update Codex if the name remains unavailable. Do not substitute a
   built-in or similarly named role.

Immediately after steps 1-2 and immediately before the native `spawn_agent` call,
record the UTC cutoff used to distinguish this new rollout from an older reused path:

~~~sh
runtime_since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
~~~

3. Treat exact templates plus observed runtime routing as an acceptance gate. Inspect
   public native spawn/details metadata first. It must identify the selected custom
   role. When it exposes model or effort, compare them with the role pin.

   If public details omit model or effort and the local rollout is accessible, resolve
   `../../scripts/inspect-agent-runtime.sh` relative to this SKILL.md and run:

   ~~~sh
   skill_dir=<directory-containing-this-SKILL.md>
   runtime_inspector="$skill_dir/../../scripts/inspect-agent-runtime.sh"
   # Capture the canonical /root/<task> path returned by the completed native spawn.
   agent_path=<canonical-path-returned-by-spawn_agent>
   # Reuse the runtime_since recorded immediately before that spawn.
   sh "$runtime_inspector" --agent-path "$agent_path" --since "$runtime_since"
   ~~~

   The helper's allowlisted output is the authoritative local fallback for omitted
   model and effort. If public and local values both exist, they must agree. Accepted
   values are Terra / high for implementation and Sol / high for review. Missing,
   inconsistent, unavailable, or unobservable routing stops that lane.
   Its positional lowercase UUID interface remains available for compatibility.

4. For every Sol review, capture the observed sandbox policy type and permission
   profile type. The shipped reviewer requests read-only sandboxing, but the host may
   broaden it. Never call the review OS-enforced read-only unless the observed sandbox
   policy type is `read-only`.

The custom-agent TOML, not the spawn call, pins model and effort. Never add per-spawn
model or reasoning overrides.

## Keep architect work in the primary session

Keep these responsibilities in the primary session:

- Resolve requirements and material ambiguity.
- Choose architecture, interfaces, and decomposition.
- Write the complete five-part implementation specification.
- Inspect the actual diff and rerun verification.
- Judge reviewer feedback and accept the deliverable.

Do not type implementation code, tests, boilerplate, or mechanical configuration in
the primary session when the Terra lane can do it. If its result is wrong, correct the
specification and delegate the fix. Do not silently repair a failed worker patch.

## Route every implementation through Terra / High

Use the same role for routine features, mechanical edits, difficult debugging,
security-sensitive work, non-trivial algorithms, and broad refactors. There is no
second implementation or fallback lane.

Spawn exactly:

~~~text
agent_type: sol_advisor_terra_implementer
fork_turns: none
~~~

The installed role pins GPT-5.6 Terra at high reasoning. Omit per-spawn model and
reasoning fields. Confirm role, model, and effort using the public-details-first
procedure before accepting work.

Routing rules:

- Give each worker one owned file set or bounded responsibility.
- State that it is not alone in the codebase, must preserve other edits, and must
  adapt to concurrent changes.
- Run independent non-overlapping work concurrently only when useful. Keep shared-file
  edits and dependency chains serial.
- Give a failed lane a corrected specification; never repeat an unchanged prompt.
- Never silently substitute a role, model, or reasoning level.

## Verify every implementation

Treat worker reports as claims. Before acceptance:

1. Inspect the working tree and complete diff.
2. Confirm only in-scope files changed.
3. Rerun the specification's verification commands in the primary session.
4. Compare the evidence with the objective, interfaces, and constraints.
5. Delegate corrections when the evidence or diff is wrong.

## Consult Sol at commitment boundaries

Before a consequential architecture, migration, public API, or wide refactor, spawn a
fresh reviewer using the commitment-boundary packet from the role contracts:

~~~text
agent_type: sol_advisor_sol_reviewer
fork_turns: none
~~~

The role pins Sol / High and requests read-only isolation. Omit per-spawn model and
reasoning fields. Observe actual routing, sandbox, and permission metadata. The
primary session remains responsible for the decision.

## Require the final Sol review

After implementation and parent verification, always spawn a new, fresh reviewer:

~~~text
agent_type: sol_advisor_sol_reviewer
fork_turns: none
~~~

Use the final-review packet from the role contracts. Instruct the reviewer to remain
behaviorally read-only, inspect the actual files and accumulated diff, and return
exactly `ship`, `fix-first`, or `rethink`.

- `ship`: report completion with verification evidence.
- `fix-first`: delegate the required fixes, verify again, and obtain a new review.
- `rethink`: revise architecture and do not report completion.

Never let the reviewer implement its own fixes. A Sol-on-Sol review is context-clean,
not model-family-independent.

Apply the observed sandbox policy:

- If it is `read-only`, isolation is enforced.
- If the host broadens it, proceed only when hard isolation is not required, the
  prompt forbids edits, and the parent captures and verifies exact before-and-after
  repository and artifact state. Report the observed sandbox and permission profile.
- If hard isolation is required, the sandbox is unobservable, or any mutation occurs,
  stop the review. Do not claim read-only isolation or hide the mutation.
