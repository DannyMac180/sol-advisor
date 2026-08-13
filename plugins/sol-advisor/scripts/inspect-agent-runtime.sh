#!/bin/sh
# Emit only allowlisted aggregate routing evidence for one native rollout.

set -eu

usage() {
  cat <<'EOF'
Usage: inspect-agent-runtime.sh THREAD_ID

Read the exact rollout file under the local Codex sessions root and emit only
allowlisted aggregate usage and route-evidence fields. This command accepts no path
arguments and never emits prompt, path, parent-thread, sandbox contents, or permission
data. It emits only the sandbox policy type.
EOF
}

fail() {
  printf '%s\n' "ERROR: $*" >&2
  exit 1
}

[ "$#" -eq 1 ] || { usage >&2; exit 2; }
thread_id=$1
printf '%s\n' "$thread_id" | LC_ALL=C grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' ||
  fail "THREAD_ID must be a lowercase UUID."

if [ -n "${CODEX_HOME-}" ]; then
  sessions_dir=$CODEX_HOME/sessions
else
  [ -n "${HOME-}" ] || fail "HOME is unset and CODEX_HOME was not supplied."
  sessions_dir=$HOME/.codex/sessions
fi
[ -d "$sessions_dir" ] && [ ! -L "$sessions_dir" ] || fail "local sessions directory is unavailable."

tmp_base=/tmp
matches_file=$(mktemp "$tmp_base/sol-advisor-runtime.XXXXXX") || fail "could not create temporary match list."
cleanup() { rm -f "$matches_file"; }
trap cleanup 0 HUP INT TERM

find "$sessions_dir" -type f -name "rollout-*-$thread_id.jsonl" -print > "$matches_file" ||
  fail "could not enumerate local rollout filenames."
match_count=$(awk 'END { print NR + 0 }' "$matches_file")
[ "$match_count" -eq 1 ] || fail "expected exactly one local rollout filename for the requested thread id."
IFS= read -r rollout_file < "$matches_file" || fail "could not read matched rollout filename."

# jq constructs a fresh allowlist. It never returns prompts, paths, messages, or
# thread identifiers other than the requested one.
jq -ce -s --arg thread_id "$thread_id" '
  def consistent($values; $label):
    ($values | map(select(type == "string" and length > 0)) | unique) as $unique |
    if ($unique | length) == 1 then $unique[0] else error("inconsistent " + $label) end;
  def median:
    sort as $values | ($values | length) as $n |
    if $n == 0 then null
    elif ($n % 2) == 1 then $values[$n / 2]
    else (($values[$n / 2 - 1] + $values[$n / 2]) / 2) end;
  . as $records |
  [ .[] | select(.type == "session_meta") | .payload ] as $sessions |
  [ .[] | select(.type == "turn_context") | .payload ] as $turns |
  [ .[] | select(.type == "event_msg" and .payload.type == "thread_settings_applied") | .payload.thread_settings.service_tier? | select(. != null) ] as $tiers |
  [ .[] | select(.type == "event_msg" and .payload.type == "token_count") | .payload.info ] as $token_infos |
  [ $token_infos[]?.total_token_usage?.total_tokens | select(type == "number" and . >= 0 and floor == .) ] as $raw_tokens |
  [ $token_infos[]?.last_token_usage?.input_tokens | select(type == "number" and . >= 0 and floor == .) ] as $input_rounds |
  [ .[] | select(.type == "response_item" and ((.payload.type? // "") | endswith("_call"))) ] | length as $tool_calls |
  [ $records[] | select(.type == "context_compacted" or (.type == "event_msg" and .payload.type == "context_compacted")) ] | length as $compactions |
  if ($sessions | length) == 0 or ($turns | length) == 0 then error("missing runtime evidence") else
    ($sessions | map(.id) | unique) as $ids |
    if $ids != [$thread_id] then error("session metadata does not match requested thread") else
    ($sessions | if (all(.parent_thread_id? == null) and all(.agent_role? == null)) then
      {context:"parent",role:null}
    elif (all(.parent_thread_id? != null) and all(.agent_role? | type == "string" and length > 0)) then
      {context:"agent",role:(map(.agent_role) | consistent(.; "agent role"))}
    else error("mixed or incomplete session provenance") end) as $provenance |
    ($turns | map(.model) | consistent(.; "model")) as $model |
    ($turns | map(.effort) | consistent(.; "effort")) as $effort |
    ($turns | map(.sandbox_policy.type) | consistent(.; "sandbox policy type")) as $sandbox |
    ($tiers | unique) as $unique_tiers |
    if ($unique_tiers | length) > 1 then error("inconsistent runtime service tier") else
    {thread_id:$thread_id,evidence_source:"codex-rollout-inspector",execution_context:$provenance.context,agent_identifier:$provenance.role,model:$model,effort:$effort,sandbox_policy_type:$sandbox,observed_runtime_tier:(if ($unique_tiers | length) == 0 then null else $unique_tiers[0] end),raw_tokens:(if ($raw_tokens | length) == 0 then 0 else ($raw_tokens | max) end),model_rounds:($input_rounds | length),median_input_tokens_per_round:($input_rounds | median),median_input_tokens_first_20:(if ($input_rounds | length) >= 20 then ($input_rounds[:20] | median) else null end),tool_calls:$tool_calls,compactions:$compactions}
    end end end
' "$rollout_file" 2>/dev/null || fail "rollout is missing, ambiguous, invalid, or lacks allowlisted aggregate evidence."
