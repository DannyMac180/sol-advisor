---
name: orchestration
description: "Codex-native risk-gated selective routing: default solo delivery, targeted native delegation or audit, and exceptional full review."
---

# Sol Advisor Orchestration

Act as the architect. Own the user's intent, architecture, route choice, decomposition,
implementation or delegation, parent verification, escalation decisions, and final
acceptance. Selective routing has four exact modes: `solo`, `delegate`, `audit`, and
`full`. Solo is the default. One auxiliary agent is the default maximum; full is an
explicit broad or high-risk exception.

Read [references/role-contracts.md](references/role-contracts.md) before the first
delegation. Use [references/operations.md](references/operations.md) for exact spawn,
preflight, runtime-evidence, isolation, and maintainer procedures.

## Verify the primary session

Run the primary Codex session on gpt-5.6-sol with high reasoning. Use complete
host-provided runtime metadata when it exposes both fields for the current session. If
either field is unavailable, emit the route declaration below before using task tools,
then inspect the exact current rollout:

~~~sh
skill_dir=<directory-containing-this-SKILL.md>
runtime_inspector="$skill_dir/../../scripts/inspect-agent-runtime.sh"
sh "$runtime_inspector" --primary "$CODEX_THREAD_ID"
~~~

The inspector reports the latest applied `turn_id`; a UI change made during a running
turn becomes runtime evidence only after Codex starts and records the next turn.

Continue without prompting when the result verifies exact Sol / High. If the current
thread ID is unavailable, inspection fails, or either field differs, stop and tell the
user to select Sol / High before retrying. Do not accept configured defaults, previous
threads, auxiliary metadata, or manual attestation as active-session evidence. A skill
cannot change the primary model itself.

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

No local primary-runtime inspection may precede this declaration. When host metadata
is incomplete, state in `risk` that primary evidence is pending local inspection.

## Preflight selected auxiliaries only

Verify Sol / High in the primary session as described above. Preflight only an
auxiliary selected by the declared route: none for solo; Luna / Max or Terra / High for
delegate; fresh Sol / High for audit; and the selected implementer plus fresh Sol
reviewer for full. Public metadata for the selected auxiliary's role, model, and effort
is authoritative. If it omits a model or effort, use the local inspector only for that
omitted field. Missing, conflicting, unavailable, or unobservable evidence stops the
affected lane; never silently substitute a role, model, effort, or reviewer.

## Route delivery without duplication

- `solo`: root plans, implements, tests, and self-reviews; spawn no auxiliary.
- `delegate`: select Luna / Max for bounded, fully specified work, or Terra / High for
  judgment-heavy, high-risk, context-heavy, or wide-blast-radius work. The selected
  implementer executes the complete spec; root verifies; do not request a fresh review.
- `audit`: root implements and verifies; a fresh read-only Sol / High reviewer reviews
  the accumulated diff; spawn no implementer.
- `full`: only for an explicit broad or high-risk exception. Select one implementer,
  root verifies, then a fresh read-only Sol / High reviewer reviews.

Auxiliary work must substitute for root work, not duplicate it. A Luna result may
justify escalation to Terra / High only when it reveals newly observed complexity,
risk, wide blast radius, or misclassification. A corrected Luna attempt is reserved
for a specification error and is not a prerequisite for Terra. Any route change must
be declared and evidenced; do not silently downgrade.

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
