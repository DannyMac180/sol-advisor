---
name: configure-model-hook
description: "Experimental, advisory setup for Sol Advisor's primary Sol / High defaults and bundled active-model observation hook."
---

# Configure the experimental model hook

Use this command to inspect the active Sol Advisor model gate, review the advisory
hook, and optionally set Sol / High defaults for future threads.

Start with this prominent notice before any tool call:

> **Experimental and advisory:** this command inspects evidence and can optionally
> update future-session defaults. It cannot change the turn already in progress, prove
> reasoning effort through the hook, or authorize Sol Advisor orchestration.

## Inspect before suggesting changes

Complete both inspections before you suggest a change.

1. Inspect complete host-provided runtime metadata when it explicitly exposes the
   active model and reasoning effort.
2. If either field is unavailable, resolve
   `../../scripts/inspect-agent-runtime.sh` relative to this skill and run `--primary`
   with the current exact thread ID. Treat unavailable or mismatch output as evidence,
   not permission to proceed.
3. Resolve the user configuration as `$CODEX_HOME/config.toml` when `CODEX_HOME` is
   already set, otherwise `$HOME/.codex/config.toml`.
4. Inspect only the top-level `model` and `model_reasoning_effort` values and whether
   the file is absent, regular, or unsafe. Parse an existing file as TOML, and do not
   print unrelated settings.
5. Report runtime evidence separately from configuration. Never use `config.toml` as
   proof of the active session.

After both inspections, recommend the smallest applicable correction. For the current
TUI session, tell the user to select `gpt-5.6-sol` with high reasoning through `/model`,
then verify it through `/status`. The skill and hook cannot make that in-session change.

## Require separate approval for user defaults

Do not change user defaults without a new, explicit approval. If either user-level
default differs or is absent, ask separately for explicit approval to edit exactly
these top-level assignments, then stop until the user replies:

~~~toml
model = "gpt-5.6-sol"
model_reasoning_effort = "high"
~~~

Approval to inspect, run the command, trust the hook, or remediate the current session
does not authorize a user-configuration edit. Never cache approval across turns or
threads.

After explicit approval:

1. Confirm that the target is absent or a regular file; refuse symlinks and nonregular
   files.
2. For a missing file, create only the two approved assignments.
3. For an existing file, parse it first and preserve every unrelated byte while you
   change or insert only unambiguous top-level assignments.
4. If comments, duplicate-looking keys, dotted keys, table placement, invalid TOML,
   permissions, concurrent changes, or other structure makes a minimal edit uncertain,
   stop and give manual instructions instead of rewriting or reformatting the file.
5. Re-parse the result and report only the two relevant values.

Configuration defaults apply to future threads. They do not change the current
session, so `/model` remains necessary here.

## Review the bundled hook and automation alternatives

The bundled hook adds model-only advisory context to explicitly allowlisted
AI-execution commands. Direct the user to `/hooks` to review the exact
`UserPromptSubmit` definition, trust it, disable it, or re-enable it. Explain that the
hook currently allows `$sol-advisor:orchestration`, skips this configuration command
and unrelated prompts. It never blocks or changes a model. It supplies no
reasoning-effort proof and never authorizes orchestration.

Offer these supported automation paths when useful:

- Start a TUI with explicit overrides:
  `codex --model gpt-5.6-sol -c 'model_reasoning_effort="high"'`.
- For App Server clients, set `"model": "gpt-5.6-sol"` and
  `"effort": "high"` in the `turn/start` parameters.

End with the evidence that applies to the current thread, the settings that affect
future threads, and one specific remaining user action, if any.
