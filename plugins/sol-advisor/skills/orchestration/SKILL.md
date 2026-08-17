---
name: orchestration
description: "Codex-native risk-gated selective routing with optional DeepSeek delegation, targeted audit, and exceptional full review."
---

# Sol Advisor Orchestration

Act as the architect. Own the user's intent, architecture, route choice, decomposition,
implementation or delegation, parent verification, escalation decisions, and final
acceptance. Selective routing has four exact modes: `solo`, `delegate`, `audit`, and
`full`. Solo is the default. One auxiliary agent is the default maximum; full is an
explicit broad or high-risk exception.

Read [references/role-contracts.md](references/role-contracts.md) before the first
delegation. When selecting DeepSeek, also read
[references/deepseek-native-lane.md](references/deepseek-native-lane.md). Use
[references/operations.md](references/operations.md) for exact spawn, preflight,
runtime-evidence, isolation, and maintainer procedures.

## Confirm the primary session

Run the primary Codex session on gpt-5.6-sol with high reasoning. Verify the current
model and effort when runtime metadata exposes them. If either differs, tell the user
to select Sol / High and stop before delegation. If runtime metadata does not expose
them, ask the user to confirm Sol / High and stop until confirmed. A skill cannot
change the primary model itself; never assume or claim this prerequisite is satisfied.

## Declare the route before task tools

Before the first task tool call, emit one machine-auditable declaration:

~~~text
SELECTIVE ROUTE
mode: solo | delegate | audit | full
risk: <concise, task-specific rationale>
~~~

No task tool call may precede this declaration. Choose `solo` unless a stated risk
justifies another mode. A later declaration may only escalate the route when newly
observed risk justifies it; never silently downgrade. Record the evidence for an
escalation. Details and the task-scoped preflight matrix are in operations.md.

## Preflight selected auxiliaries only

Confirm Sol / High in the primary session. Preflight only an auxiliary selected by the
declared route: none for solo; Luna / Max, Terra / High, or capability-gated DeepSeek /
Max for delegate; fresh Sol / High for audit; and the selected implementer plus fresh
Sol reviewer for full. Public metadata for role, model, and effort is authoritative. If
it omits a model or effort, use the local inspector only for that omitted field. Missing,
conflicting, unavailable, or unobservable evidence stops the affected lane; never
silently substitute a role, model, effort, or reviewer.

## Route delivery without duplication

- `solo`: root plans, implements, tests, and self-reviews; spawn no auxiliary.
- `delegate`: select Luna / Max or capability-gated DeepSeek / Max for bounded, fully
  specified work, and Terra / High for judgment-heavy, high-risk, context-heavy, or
  wide-blast-radius work. Select DeepSeek only when its exact routed capability is
  verified. The selected implementer
  executes the complete spec; root verifies; do not request a fresh review.
- `audit`: root implements and verifies; a fresh read-only Sol / High reviewer reviews
  the accumulated diff; spawn no implementer.
- `full`: only for an explicit broad or high-risk exception. Select one implementer,
  root verifies, then a fresh read-only Sol / High reviewer reviews.

Auxiliary work must substitute for root work, not duplicate it. A Luna result may
justify escalation to Terra / High only when it reveals newly observed complexity,
risk, wide blast radius, or misclassification. A corrected Luna attempt is reserved
for a specification error and is not a prerequisite for Terra. Any route change must
be declared and evidenced; do not silently downgrade.

## Capability-gated DeepSeek implementation

DeepSeek is an optional native implementer for bounded, fully specified implementation
work in declared `delegate` and `full` routes. A `full` route may use it only when the
implementation packet remains bounded within a settled architecture and the broader
task risk is handled by parent verification plus fresh review.
The installed `sol_advisor_deepseek_implementer` role pins
`deepseek/deepseek-v4-flash` at max reasoning, but installation alone is not routing
evidence. Confirm the exact role, model, and effort through public native metadata
before accepting the lane. An explicit DeepSeek request fails closed when that route
is unavailable or unobservable.

When the primary selects DeepSeek automatically and the spawn fails before worker work
begins with a clear provider or surface error, report the failed selection, preflight
Terra / High, and use Terra only if that check succeeds. Never fall back after DeepSeek
has edited files, produced implementation output, or returned ambiguous routing
metadata. Follow the complete
[DeepSeek native-lane contract](references/deepseek-native-lane.md).

## Keep architect work in the primary session

Keep these responsibilities in the primary session:

- Resolve requirements and material ambiguity.
- Choose architecture, interfaces, decomposition, and selective route.
- Write the complete five-part worker specification for any selected implementer.
- Inspect the actual diff and rerun verification.
- Decide whether newly observed risk warrants escalation.
- Judge the reviewer verdict when the route includes review and accept the deliverable.

Every worker prompt must contain OBJECTIVE, FILES AND OWNERSHIP, INTERFACES,
CONSTRAINTS, VERIFICATION, and the structured implementation return in
[the role contracts](references/role-contracts.md). State the exact owned files,
preserve concurrent edits, and never silently widen scope.

Treat worker reports as claims. Confirm the complete diff, changed-file scope, requested
checks, and artifact/runtime evidence in the parent session. Do not duplicate the
selected implementer's work in the primary session.

## Review only when the route includes it

For `audit` and `full`, after parent verification, spawn a new native Sol / High
reviewer. The reviewer must remain behaviorally read-only, inspect the actual
accumulated diff, and return exactly ship, fix-first, or rethink. A reviewer never
implements its own fixes. `solo` and `delegate` do not receive a fresh reviewer.

- ship: report completion with the verification evidence.
- fix-first applies only to `audit` and `full`:
  - audit: the root implements the required correction, re-verifies, and obtains a new
    fresh reviewer.
  - full: the selected implementer handles the required correction, the root
    re-verifies, and a new fresh reviewer reviews.
  - solo and delegate: no fresh reviewer is added unless a newly observed,
    risk-evidenced route escalation is declared; never silently add one.
- rethink: revise the architecture and do not report completion.

Any implementation correction invalidates the prior verdict. Apply the observed sandbox
and permission profile rules in the operations reference; never claim enforced
read-only isolation when it was not observed.
