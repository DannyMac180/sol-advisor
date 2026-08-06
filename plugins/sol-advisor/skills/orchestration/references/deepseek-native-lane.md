# DeepSeek native-lane contract

This is the normative contract for Sol Advisor's capability-gated native DeepSeek
implementation lane. The role is installed by default, but installation is not routing
evidence. The primary GPT-5.6 Sol / High task remains the architect, verifier,
correction owner, and final acceptor, and every successful native implementation still
requires a fresh `sol_advisor_sol_reviewer` verdict.

## Required route

- Agent type: `sol_advisor_deepseek_implementer`
- Model: `deepseek/deepseek-v4-flash`
- Reasoning effort: `high`
- Spawn context: `fork_turns: none`
- Expected provider path: a routed provider such as OpenCodex; Sol Advisor does not
  install, start, configure, or authenticate that provider.

Use the provider's default multi-agent mode when it advertises this exact role and
model as compatible. Do not force a global v1 or v2 mode merely because the role file
is installed. A model catalog entry, an available `agent_type`, and observed runtime
routing are separate facts; never infer one from another.

## Selection and fallback

- If the user explicitly requires DeepSeek, select this lane. If the role, model,
  effort, or provider route is unavailable, inconsistent, or unobservable, stop without fallback.
- If the user explicitly requires Terra, select Terra without probing DeepSeek.
- If the user does not select an implementer, the primary may prefer DeepSeek only
  when the native tool advertises the exact role. If the spawn fails before any worker
  work begins with a clear unavailable-model, unavailable-provider, or
  surface-incompatible error, report the failed selection and use Terra.
- Never fallback after DeepSeek has edited files, produced implementation output, or
  returned ambiguous routing metadata. At that point stop, inspect repository state,
  and ask the user before choosing another implementation lane.
- Never describe the reported Terra selection as a DeepSeek run. A fallback changes
  the selected lane and must be stated in the final evidence.

## Runtime acceptance

After a successful spawn, inspect public native spawn/details metadata first. Accept
the worker report only when it identifies `sol_advisor_deepseek_implementer` and, when
exposed, `deepseek/deepseek-v4-flash` at `high`. If model or effort is omitted and the
local rollout is accessible, use the shipped runtime inspector. Public and local
evidence must agree when both exist.

An `unreadable_encrypted_agent_task` error is a routing failure, not implementation
output. For an automatic lane selection it permits the reported pre-work Terra
fallback above. For an explicitly requested DeepSeek lane it stops without fallback.
Always send a complete, self-contained five-part implementation specification and use
`fork_turns: none`; do not rely on inherited parent history.

## Verification and review

Treat every DeepSeek report as a claim. The primary must inspect the actual diff,
confirm the changed-file scope, and rerun every required verification command. Route
bounded corrections back through DeepSeek only after reconfirming its exact runtime
identity. After primary verification, spawn a new `sol_advisor_sol_reviewer` with
`fork_turns: none`. Any correction invalidates the previous verdict and requires a new
fresh review.
