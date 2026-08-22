#!/bin/sh
# Emit advisory model context only for allowlisted Sol Advisor commands.

input=$(cat) || exit 0

# Codex currently ignores UserPromptSubmit matchers, so enforce the command allowlist
# here. Ignore malformed payloads, unrelated prompts, and the configuration command.
model=$(printf '%s\n' "$input" | jq -er '
  select(type == "object") |
  select(.hook_event_name == "UserPromptSubmit") |
  select((.prompt | type) == "string") |
  select((.model | type) == "string" and .model != "") |
  select(.prompt | test("(^|[[:space:]])\\$sol-advisor:configure-model-hook([[:space:]]|$)") | not) |
  select(.prompt | test("(^|[[:space:]])\\$sol-advisor:orchestration([[:space:]]|$)")) |
  .model
' 2>/dev/null) || exit 0

# Reject unsafe model text before adding it to developer context.
case "$model" in
  ''|*[!A-Za-z0-9._-]*) exit 0 ;;
esac

if [ "$model" = gpt-5.6-sol ]; then
  printf '%s\n' 'Sol Advisor model check: active model is gpt-5.6-sol. This evidence covers the model only; complete the primary-session reasoning-effort check before orchestration.'
else
  printf '%s\n' "Sol Advisor model mismatch: active model is $model, but Sol Advisor requires gpt-5.6-sol. Select it with /model, verify it with /status, then complete the primary-session gate."
fi

exit 0
