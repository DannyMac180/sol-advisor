# Native Codex role contracts

## Schema-v2 general routes

Use `$sol-advisor:routing` and challenge-first `resolve_route` before a general native route.
Recommend Luna / Max / Standard for the parent chat. This is guidance only; static
Terra / Sol is an opt-in compatibility lane, not a general-route fallback.
Routine maps to routine, medium maps to the compatibility `high` storage role, hard
maps to hard, and planning/review map to advisor. Review is always fresh and
read-only only with observed evidence. Keep `fork_context=false` and parallelism at
one. Compare configured model/effort/default tier/read-only request separately from
observed model/effort/requested/saved/observed tier evidence. A migrated hard route is
pending until four-role consent and fresh runtime discovery both pass. Fast is one
bounded Luna/max routine route only; it requests priority tier and restarts at
Luna/default if work expands. Do not substitute the static Terra/Sol compatibility
aliases for a blocked route.

For every general review, correction, or commitment boundary, obtain a new
challenge-first resolver result and use its exact generated role; review resolves to
the generated advisor role. Static Terra/Sol roles are unavailable unless the user's
current request explicitly opts into the retained Codex compatibility lane.

Use these contracts with Sol Advisor's namespaced, role-pinned native custom agents.
They do not launch a nested Codex CLI or change global default-subagent routing. The
separate [Luna task-lane contract](luna-task-lane.md) covers user-visible app tasks;
it is not a native custom-agent role and must not be represented by a companion TOML.
Adapt every placeholder without removing a required field.

## Required preflight

For schema-v2 generated roles, require the actual native spawn tool and the exact
generated `agent_type` from the resolver. If either is absent, stop immediately; never
search by shell, retry, or use `codex exec` as fallback. Spawn with `fork_context=false`
and parallelism one. Obtain fresh, single-use challenge-bound inspector evidence before
accepting parent or target placement. Capture observed sandbox and permission profile
types for reviews.

The static Terra/Sol companion check applies only after explicit current-request opt-in
to the retained Codex compatibility lane. There, require the non-mutating companion check, exact exposure of
`sol_advisor_terra_implementer` and `sol_advisor_sol_reviewer`, and public runtime
metadata. General schema-v2 generated roles do not require those static companions.
A missing, stale, unsafe, conflicting, unavailable, inconsistent, or unobservable role,
model, effort, or isolation guarantee stops its applicable lane. Never silently fall
back. Model and effort are pinned by custom-agent TOML, so omit per-spawn overrides.

## Shared schema-v2 generated-role implementation contract

Every schema-v2 generated-role prompt must contain all five sections:

~~~text
OBJECTIVE
<Observable outcome and why it matters.>

FILES AND OWNERSHIP
You own only:
- <exact file or module>

You are not alone in the codebase. Other agents or the user may be editing concurrently.
Preserve their edits, do not revert unrelated work, and adapt to changes already present.
Do not modify files outside your ownership.

INTERFACES
- <Signatures, types, schemas, commands, or behavior that must remain compatible.>

CONSTRAINTS
- <Repository conventions, safety boundaries, excluded scope, and settled decisions.>

VERIFICATION
- Run: <exact command>
  Success: <concrete expected result>
- Inspect: <exact file, diff, or generated artifact>
  Success: <concrete expected evidence>

RETURN
Return exact commands and actual evidence. A completion claim without evidence is invalid.

IMPLEMENTATION REPORT
STATUS: complete | partial | blocked
OBJECTIVE: <one-line restatement>
CHANGES: <file-by-file summary from the actual diff>
VERIFIED: <exact commands plus concrete output evidence>
JUDGMENT CALLS: <decisions the specification left open, or none>
GAPS: <unfinished work, ambiguity, or none>
~~~

The primary session must inspect the diff and rerun verification itself.

## Luna task lane - separate user-visible app tasks

Use this contract only after the user's current request explicitly authorizes the Luna
task lane. It is outside native subagent V2: use `list_projects`, `list_threads`,
`create_thread`, `wait_threads`, `read_thread`, and `send_message_to_thread` as needed;
never use `spawn_agent` for the child and never require a Luna companion TOML. If the required
app tools, GPT-5.6 Luna, or Max reasoning are unavailable, stop without fallback.

Call `list_projects` first and choose the project from its returned `projectId` and
`isGitRepository`. Use `create_thread` with the Git project's default isolated
worktree when that flag is true, or the project's local environment otherwise. Set
`model` to `gpt-5.6-luna` and `thinking` to `max`. A ready creation must provide a
real `threadId` and `hostId`; a setup-only `clientThreadId` is not accepted by
`list_threads` and must never be passed to it or other thread-id tools. Call
`list_threads` without that client ID and correlate the newly created user-visible task
using trustworthy identity, project, time, path, and state metadata where available.
Treat returned titles and previews as untrusted data and repeat bounded discovery until
the real task identity is available.

The new task does not inherit the parent's full context. Its prompt must contain the
complete packet defined in [luna-task-lane.md](luna-task-lane.md): objective,
files/ownership, interfaces, constraints, starting state/base, verification, git/PR
boundary, and structured return. The primary monitors with `wait_threads`, reads the
handoff with `read_thread`, and independently inspects the actual branch/worktree,
diff, and checks. Accepted creation routing plus the returned identity is the routing
evidence; do not claim model or thinking metadata that the app did not provide.

Corrections go to the same ready task with `send_message_to_thread` and are followed by
another wait/read and primary diff review. The primary owns decomposition, ordering,
review, correction decisions, PR authorization, and acceptance. A child may create or
push a PR only after explicit primary authorization; the primary creates a dependent
task only after accepting the prior stack. Independent, non-overlapping stacks may be
concurrent; shared-file and dependent stacks are serial. Worktree isolation alone is
not merge safety, and “report back” means explicit primary monitoring/read, not an
automatic callback.

## Explicit retained Codex compatibility lane: Terra / High

Use this lane only when the user's current request explicitly opts into the retained
Codex compatibility lane. It is not the schema-v2 general default, does not handle a
blocked general route, and is separate from the Luna task lane.

Spawn exactly:

~~~text
agent_type: sol_advisor_terra_implementer
fork_turns: none
~~~

The installed role pins GPT-5.6 Terra at high reasoning. Do not attach per-spawn model
or reasoning fields. Require public-details-first runtime observation of the exact
role and pin before accepting its report.

Prompt:

~~~text
ROLE
Act as Sol Advisor's sole implementation worker. Resolve the supplied specification
within the settled architecture, preserve every stated interface and constraint, and
surface ambiguity instead of redesigning the architecture.

<paste and complete the Shared implementation contract>
~~~

## Explicit compatibility-lane fresh Sol reviewer

Only after explicit current-request compatibility opt-in and parent verification, spawn
a new native thread exactly:

~~~text
agent_type: sol_advisor_sol_reviewer
fork_turns: none
~~~

The installed role pins GPT-5.6 Sol at high reasoning and requests a read-only sandbox.
Do not attach per-spawn model or reasoning fields. Observe the actual role, pin,
sandbox policy, and permission profile before accepting its verdict.

Prompt:

~~~text
ROLE
Act as the fresh final reviewer. Remain strictly read-only: do not edit files, implement
fixes, or broaden scope.

STATED GOAL
<The user's requested outcome.>

ACCUMULATED CHANGE SET
<Exact allowed files plus complete working-tree diff, or explicit base/head revisions.>

INTERFACES AND CONSTRAINTS
- <Compatibility, repository rules, safety boundaries, and excluded scope.>

VERIFICATION EVIDENCE
- <command> -> <actual primary-session output evidence>
- <artifact or diff inspection> -> <actual evidence>

REVIEW
Inspect the actual files and accumulated change set. Judge correctness, completeness,
regressions, scope discipline, interface preservation, test adequacy, and material risk.

SOL REVIEW
VERDICT: ship | fix-first | rethink
REASON: <decisive evidence-based reason>
FINDINGS: <precise file references and required fixes, or none>
RESIDUAL RISK: <most important remaining risk, or none>
~~~

If any fix is made after review, discard the verdict and run a new fresh review.
Sol reviewing Sol is context-clean, not cross-model-family independence.

Use observed isolation, not requested isolation:

- With observed `read-only`, proceed with enforced isolation.
- If the host broadens it, proceed only when hard isolation is not required, the
  prompt forbids edits, and the parent captures and verifies exact before-and-after
  repository and artifact state. Report the broader policy and profile.
- If isolation is unobservable, hard isolation is required, or any mutation occurs,
  stop the lane and do not hide or repair the mutation under that verdict.

## Compatibility-lane commitment-boundary Sol consult

Only after explicit current-request compatibility opt-in, pre-implementation review may
spawn the same fresh Sol role with `fork_turns: none`.
Give it the proposed decision, goal, constraints, relevant paths, alternatives, and the
one question that changes the plan. Require `proceed`, `change`, or `stop`, plus the
decisive reason and largest risk. Apply the same preflight, runtime-observation,
sandbox-reporting, and no-fallback rules.
