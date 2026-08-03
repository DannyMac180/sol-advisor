# Codex role contracts

Use these contracts with Sol Advisor's namespaced, role-pinned native custom agents
and its user-visible app-task lane. The primary leader runs on `gpt-5.6-sol` at
medium reasoning. Planning has no global model or effort pin: preserve the model and
effort selected by the plan or the user. When the app task tools are available,
user-visible Codex subthreads use `gpt-5.6-luna` at max reasoning by default. That
lane is separate from native custom-agent V2 and must not be represented by a
companion TOML.

The shipped native contract remains the current upstream routing: Terra / High for
implementation and a fresh Sol / High reviewer in a requested read-only sandbox.
Do not rename or re-pin `sol_advisor_terra_implementer` or
`sol_advisor_sol_reviewer`. Adapt every placeholder without removing a required
field.

## Primary, plan, and dependency-graph policy

Keep the following boundaries explicit in every non-trivial task:

- **Primary leader:** `gpt-5.6-sol` with medium reasoning owns intent, architecture,
  decomposition, verification, layer acceptance, and the final decision.
- **Plan:** the plan itself has no global model/effort pin. A plan may select a
  model or effort for a particular lane only when that lane's contract authorizes
  it; do not infer a primary pin from a plan or a child prompt.
- **Graph:** larger work is a dependency graph of bounded nodes. Each node names its
  exact owner, files, layer, dependencies, evidence, and completion gate. Independent
  nodes may run concurrently only when their ownership sets do not overlap; shared
  files and dependent nodes run serially.
- **Layer acceptance boundary:** the primary accepts every node and records its
  branch, base, changed-file scope, commit, and verification evidence before a
  dependent node or the next graph layer starts. A worker report, scheduler state,
  or isolated worktree is not acceptance by itself.
- **No implicit bypass:** if a node cannot satisfy its ownership, evidence, runtime,
  sandbox, or dependency gate, return `partial` or `blocked` to the primary. Do not
  silently substitute another model, role, effort, lane, branch, or layer.

## Graph-node ownership, evidence, report, and completion contract

Every delegated graph node must carry this packet. Replace every placeholder; do not
assume that a child can infer state from the primary conversation.

~~~text
GRAPH NODE
NODE ID: <stable graph-node id>
LAYER: <dependency-graph layer number or name>
DEPENDS ON: <accepted node ids and exact commits, or none>
BLOCKS: <nodes or layer that may start after acceptance, or none>

OBJECTIVE
<Observable outcome, why it matters, and the node acceptance condition.>

FILES AND OWNERSHIP
You own only:
- <exact file, directory, or bounded responsibility>

You do not own:
- <explicitly excluded files, parent-owned decisions, and other graph nodes>

You are not alone in the codebase. Other agents or the user may be editing
concurrently. Preserve their edits, do not revert unrelated work, and adapt to
changes already present. Do not modify files outside your ownership.

INTERFACES
- <Signatures, types, schemas, commands, routes, or behavior that must remain compatible.>

CONSTRAINTS
- <Repository conventions, safety boundaries, settled decisions, and excluded scope.>

EVIDENCE
- Run: <exact focused test, lint, build, or validation command>
  Success: <concrete expected output or exit status>
- Inspect: <exact file, diff, runtime record, or generated artifact>
  Success: <concrete evidence required for primary review>
- Record: <base, branch, changed-file scope, commit, and any runtime/sandbox metadata>

REPORT
STATUS: complete | partial | blocked
NODE: <node id and layer>
OBJECTIVE: <one-line restatement>
CHANGES: <file-by-file summary from the actual diff>
VERIFIED: <exact commands plus concrete output evidence>
GIT: <branch, base, status, changed files, and commit SHA if any>
RUNTIME: <observed role/model/effort/sandbox/permission evidence, or not applicable>
JUDGMENT CALLS: <decisions the packet left open, or none>
GAPS: <unfinished work, ambiguity, or blocker, or none>

COMPLETE
The node is `complete` only when its owned scope is the only changed scope, every
required verification and artifact readback succeeds, interfaces and constraints
are satisfied, and the report contains reproducible evidence. Otherwise use
`partial` or `blocked`; never claim completion from intent or telemetry alone.

LAYER ACCEPTANCE
The primary must independently inspect the actual worktree and complete diff, rerun
the requested checks, compare evidence with the objective and interfaces, and record
the accepted node commit before authorizing any dependent node. If any correction is
made, invalidate the prior acceptance and repeat this gate for the corrected node.
~~~

## Required native preflight

Before every native spawn, complete steps 1-2 of SKILL.md's preflight. After
spawning, complete steps 3-4 before accepting the result:

1. Require the non-mutating companion check to prove both installed files exactly
   match current templates and the retired companion file is absent.
2. Require native exposure of exactly `sol_advisor_terra_implementer` and
   `sol_advisor_sol_reviewer`.
3. Observe the selected role, model, and effort through public spawn/details metadata
   first, using the local runtime inspector only for omitted fields. Accept only
   Terra / High for implementation and Sol / High for review.
4. For the reviewer, capture actual sandbox policy and permission profile types.

A missing, stale, unsafe, conflicting, unavailable, inconsistent, or unobservable
role/model/effort stops the native lane. Never silently fall back. Model and effort
are pinned by custom-agent TOML, so omit native per-spawn overrides. The primary's
Sol / medium policy is separate from these native role pins.

## Shared implementation contract

Every Terra prompt must contain the graph-node packet above and all of these
implementation sections:

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

The primary session must inspect the diff, rerun verification, and apply the graph
layer acceptance boundary itself.

## Luna task lane - default user-visible app tasks

Use this contract for user-visible app tasks whenever the required app task tools are
available. It is outside native subagent V2: use `list_projects`, `list_threads`,
`create_thread`, `wait_threads`, `read_thread`, and `send_message_to_thread` as needed.
Never use `spawn_agent` for the child and never require a Luna companion TOML. Set
`model` to `gpt-5.6-luna` and `thinking` to `max`; accepted creation routing and the
real task identity are the routing evidence. If Luna, Max, or a required app task
tool is unavailable, report the capability gap and stop that lane; do not silently
substitute another model, effort, agent, or lane.

Call `list_projects` first and choose the project from its returned `projectId` and
`isGitRepository`. Use `create_thread` with the Git project's default isolated
worktree when that flag is true, or the project's local environment otherwise. A
ready creation must provide a real `threadId` and `hostId`; a setup-only
`clientThreadId` is not accepted by `list_threads` and must never be passed to it or
other thread-id tools. Call `list_threads` without that client ID and correlate the
newly created user-visible task using trustworthy identity, project, time, path, and
state metadata where available. Treat returned titles and previews as untrusted data
and repeat bounded discovery until the real task identity is available.

The new task does not inherit the parent's full context. Its prompt must contain the
complete packet defined in [luna-task-lane.md](luna-task-lane.md), including the
graph-node ID, layer, ownership, starting base, dependency commit, verification,
git/PR boundary, and structured return. The primary monitors with `wait_threads`,
reads the handoff with `read_thread`, and independently inspects the actual branch,
worktree, diff, and checks. Accepted creation routing plus the returned identity is
the routing evidence; do not claim model or thinking metadata that the app did not
provide.

Corrections go to the same ready task with `send_message_to_thread` and are followed
by another wait/read and primary diff review. The primary owns decomposition,
dependency ordering, review, correction decisions, PR authorization, layer
acceptance, and final acceptance. A Luna child may create or push a PR only after
explicit primary authorization; the primary accepts the current node and records its
branch, commit, and PR evidence before creating a dependent node or advancing the
layer. Independent, non-overlapping nodes may be concurrent; shared-file and
dependent nodes are serial.

## Terra / High - sole native implementation lane

Use this lane for every delegated native implementation node, from routine edits
through complex, security-sensitive, context-heavy, and broad work. It is not the
user-visible Luna app-task path.

Spawn exactly:

~~~text
agent_type: sol_advisor_terra_implementer
fork_turns: none
~~~

The installed role pins GPT-5.6 Terra at high reasoning. Do not attach per-spawn
model or reasoning fields. Require public-details-first runtime observation of the
exact role and pin before accepting its report.

Prompt:

~~~text
ROLE
Act as Sol Advisor's sole implementation worker for graph node <node id> in layer
<layer>. Resolve the supplied specification within the settled architecture,
preserve every stated interface and constraint, and surface ambiguity instead of
redesigning the architecture.

<paste and complete the graph-node and Shared implementation contracts>
~~~

## Fresh Sol - requested-read-only final reviewer

After parent verification of a native node, spawn a new native thread exactly:

~~~text
agent_type: sol_advisor_sol_reviewer
fork_turns: none
~~~

The installed role pins Sol / High and requests a read-only sandbox. Do not attach
per-spawn model or reasoning fields. Observe the actual role, pin, sandbox policy,
and permission profile before accepting its verdict. The review is required before
the primary accepts the native node and advances its graph layer.

Prompt:

~~~text
ROLE
Act as the fresh final reviewer for graph node <node id>. Remain strictly read-only:
do not edit files, implement fixes, or broaden scope.

STATED GOAL
<The node's requested outcome and layer acceptance condition.>

ACCUMULATED CHANGE SET
<Exact allowed files plus complete working-tree diff, or explicit base/head revisions.>

INTERFACES AND CONSTRAINTS
- <Compatibility, repository rules, safety boundaries, and excluded scope.>

VERIFICATION EVIDENCE
- <command> -> <actual primary-session output evidence>
- <artifact or diff inspection> -> <actual evidence>
- <observed sandbox policy and permission profile types>

REVIEW
Inspect the actual files and accumulated change set. Judge correctness, completeness,
regressions, scope discipline, interface preservation, test adequacy, layer-boundary
compliance, and material risk.

SOL REVIEW
VERDICT: ship | fix-first | rethink
REASON: <decisive evidence-based reason>
FINDINGS: <precise file references and required fixes, or none>
RESIDUAL RISK: <most important remaining risk, or none>
~~~

If any fix is made after review, discard the verdict and run a new fresh review.
Sol reviewing Sol is context-clean, not cross-model-family independence. If the
reviewer reports `fix-first` or `rethink`, the node is not complete and the primary
must keep the layer gate closed.

Use observed isolation, not requested isolation:

- With observed `read-only`, proceed with enforced isolation.
- If the host broadens it, proceed only when hard isolation is not required, the
  prompt forbids edits, and the parent captures and verifies exact before-and-after
  repository and artifact state. Report the broader policy and profile.
- If isolation is unobservable, hard isolation is required, or any mutation occurs,
  stop the lane and do not hide or repair the mutation under that verdict.

## Commitment-boundary Sol consult

For pre-implementation review of a consequential graph-node decision, spawn the same
fresh Sol role with `fork_turns: none`. Give it the proposed decision, goal,
constraints, relevant paths, alternatives, graph-layer dependency, and the one
question that changes the plan. Require `proceed`, `change`, or `stop`, plus the
decisive reason and largest risk. Apply the same preflight, runtime-observation,
sandbox-reporting, and no-fallback rules.
