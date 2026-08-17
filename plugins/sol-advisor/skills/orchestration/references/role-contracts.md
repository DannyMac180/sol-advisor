# Native Codex role contracts

Use these contracts with Sol Advisor's namespaced, role-pinned native custom agents.
They do not launch a nested Codex CLI or change global default-agent routing. Adapt
every placeholder without removing a required field.

For task-scoped preflight, runtime evidence, sandbox interpretation, and maintainer
commands, use [operations.md](operations.md).

## Selective route and required preflight

Before the first task tool call, the root emits one machine-auditable route:

~~~text
SELECTIVE ROUTE
mode: solo | delegate | audit | full
risk: <concise, task-specific rationale>
~~~

Solo is the default; one auxiliary is the default maximum. Full is an explicit broad
or high-risk exception. A later route declaration may only escalate after newly
observed risk justifies it and supplies that evidence; never silently downgrade.

Confirm Sol / High in the primary session, then preflight only auxiliaries selected by
the route: none for solo; Luna / Max, Terra / High, or DeepSeek / Max for delegate;
fresh Sol / High for audit; and one selected implementer plus fresh Sol reviewer for full. Cache each
successful check only for the task. After spawning, complete the selected role's
routing and reviewer-isolation checks before accepting the result:

1. Require the selected exact native role and fresh-context spawn contract.
2. Observe the selected role, model, and effort through public spawn/details metadata
   first, using the local runtime inspector only for omitted fields. Accept Luna /
   Max for bounded delegate/full implementation, Terra / High for higher-risk
   delegate/full implementation, DeepSeek / Max for bounded delegate/full implementation
   only when its exact routed capability is verified, and Sol / High for audit/full review.
3. For the reviewer, capture actual sandbox policy and permission profile types.

A missing, stale, unsafe, conflicting, unavailable, inconsistent, or unobservable
role/model/effort stops the native lane. Never silently fall back. Model and effort
are pinned by custom-agent TOML, so omit native per-spawn overrides.

## Shared implementation contract

Every Luna, DeepSeek, or Terra prompt must contain all five sections:

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

## Exact mode contracts

- `solo`: root plans, implements, tests, and self-reviews. Spawn no auxiliary.
- `delegate`: one selected Luna / Max, Terra / High, or DeepSeek / Max implementer
  executes the complete five-part specification. The root verifies. Do not spawn a
  fresh reviewer.
- `audit`: root implements and verifies. A fresh read-only Sol / High reviewer inspects
  the accumulated diff. Spawn no implementer. On `fix-first`, the root implements the
  correction, re-verifies, and obtains a new fresh reviewer.
- `full`: use only for an explicit broad or high-risk exception. One selected Luna /
  Max, Terra / High, or DeepSeek / Max implementer executes the complete specification,
  the root verifies, and a fresh read-only Sol / High reviewer inspects the accumulated diff.
  On `fix-first`, the selected implementer handles the correction, the root
  re-verifies, and a new fresh reviewer inspects the result.

Auxiliary work substitutes for root work; it must not duplicate it. A route can
escalate only with newly observed, recorded risk; it never silently downgrades.
Solo and delegate have no fresh reviewer or review-driven correction unless a newly
observed, risk-evidenced route escalation is declared; never silently add one.

## Luna / Max - bounded delegate/full implementation lane

Use this lane only when a declared delegate or full route selects it for bounded,
fully specified work. The installed role pins GPT-5.6 Luna at max reasoning. It must
surface ambiguity and failed checks rather than redesigning the architecture. A first
result that demonstrates newly observed judgment-heavy, high-risk, wide-blast-radius,
or misclassified work may justify a declared Terra escalation; do not force a retry
first. If the specification itself was incomplete or wrong, return a precise
correction for one corrected Luna attempt. That retry is not a prerequisite for Terra.

Spawn exactly:

~~~text
agent_type: sol_advisor_luna_implementer
fork_turns: none
~~~

Do not attach per-spawn model or reasoning fields. Prompt:

~~~text
ROLE
Act as Sol Advisor's default routine implementation worker. Execute the supplied
specification within the settled architecture, preserve every stated interface and
constraint, and surface ambiguity instead of redesigning the architecture.

<paste and complete the Shared implementation contract>
~~~

## DeepSeek V4 Flash / Max - capability-gated implementation lane

Read [deepseek-native-lane.md](deepseek-native-lane.md) before selecting this role.
Use it only for bounded, fully specified work within a settled architecture when a
declared delegate or full route selects DeepSeek and public runtime metadata verifies
the exact role, model, and effort. In `full`, the implementation packet must remain
bounded even when broader task risk requires fresh review. An explicit DeepSeek request fails
closed when that evidence is missing or inconsistent. An automatic pre-work routing
failure may be reported before selecting Terra under the DeepSeek contract.

Spawn exactly:

~~~text
agent_type: sol_advisor_deepseek_implementer
fork_turns: none
~~~

The installed role pins `deepseek/deepseek-v4-flash` at max reasoning. Do not attach
per-spawn model or reasoning fields. Prompt:

~~~text
ROLE
Act as Sol Advisor's capability-gated DeepSeek implementation worker. Resolve the
supplied specification within the settled architecture, preserve every stated
interface and constraint, and surface ambiguity instead of redesigning the architecture.

<paste and complete the Shared implementation contract>
~~~

## Terra / High - higher-risk delegate/full implementation lane

Use this lane only when a declared delegate or full route selects judgment-heavy,
high-risk, context-heavy, or wide-blast-radius work, including risk revealed by a
first Luna result. The installed role pins GPT-5.6 Terra at high reasoning. A
corrected Luna attempt is reserved for a specification error and is not a prerequisite
for Terra.

Spawn exactly:

~~~text
agent_type: sol_advisor_terra_implementer
fork_turns: none
~~~

Do not attach per-spawn model or reasoning fields. Prompt:

~~~text
ROLE
Act as Sol Advisor's explicit high-complexity escalation worker. Resolve the supplied
specification within the settled architecture, preserve every stated interface and
constraint, and surface ambiguity instead of redesigning the architecture.

<paste and complete the Shared implementation contract>
~~~

## Fresh Sol / High - requested-read-only audit/full reviewer

Only for an audit or full route, after parent verification, spawn a new native thread
exactly:

~~~text
agent_type: sol_advisor_sol_reviewer
fork_turns: none
~~~

The installed role pins Sol / High and requests a read-only sandbox. Do not attach
per-spawn model or reasoning fields. Observe the actual role, pin, sandbox policy, and
permission profile before accepting its verdict.

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
