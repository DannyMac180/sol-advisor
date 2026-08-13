# Portable entry and capability matrix

Use saved setup preferences and observable host capabilities. Never translate model
names, enumerate a supposedly universal catalog, guess tools, or infer behavior from
manifest conformance.

## Entry sequence

1. Call `get_setup_status`. Missing, schema-old, or corrupt state routes to the parent
   `setup` interview before orchestration.
2. Call `get_preferences` and keep the orchestrator on the parent chat's inherited
   model and effort.
3. Determine whether the current surface exposes the exact installed native role
   names and relevant routing/sandbox evidence.
4. If native bindings are unavailable, use prompt-only advisory behavior and state
   precisely which model, effort, cost-tier, or read-only properties are unenforceable.

| Client/surface | Adapter capability | Important limit |
|---|---|---|
| Codex CLI | Model + per-agent effort; advisor requests read-only | Only observed sandbox evidence proves isolation |
| Cursor | Model and optional native effort syntax; readonly request | Host behavior must be observed |
| VS Code / GitHub Copilot | Model only | Effort and parent cost tier are session constraints |
| Kiro IDE/CLI | Model only | Effort is session/per-model, not per-agent |
| ChatGPT Work web, Kiro web/mobile, skills-only surfaces | Parent-chat prompt guidance only; no stored native profile | No enforceable native role binding claimed |

The retained Codex native compatibility lane is available only when the user's current
request explicitly opts into it and its separately installed roles and routing preflight
pass. It is never a fallback. The Luna / Max app-task lane is separate,
current-request opt-in only, and never a fallback.
