#!/bin/sh
# Emit only allowlisted aggregate routing evidence for one native rollout.

set -eu

usage() {
  cat <<'EOF'
Usage: inspect-agent-runtime.sh --challenge CHALLENGE THREAD_ID

Read the exact rollout file under the local Codex sessions root and emit only
allowlisted aggregate usage and route-evidence fields. This command accepts no path
arguments and never emits prompts, paths, raw rollout data, sandbox contents, or
permission data. Agent evidence emits only its exact allowlisted parent thread UUID;
parent evidence emits `parentThreadId: null`. It emits only the sandbox policy type.
Pass the exact unconsumed challenge from
resolve_route; the camelCase JSON object can be supplied directly as runtime evidence.
EOF
}

fail() {
  printf '%s\n' "ERROR: $*" >&2
  exit 1
}

[ "$#" -eq 3 ] && [ "$1" = "--challenge" ] || { usage >&2; exit 2; }
challenge=$2
thread_id=$3
printf '%s\n' "$challenge" | LC_ALL=C grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' ||
  fail "CHALLENGE must be a lowercase UUID issued by resolve_route."
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
jq -ce -s --arg challenge "$challenge" --arg thread_id "$thread_id" '
  def exact_string:
    type == "string" and length > 0 and . == gsub("^[[:space:]]+|[[:space:]]+$"; "") and (contains("\\r") | not) and (contains("\\n") | not) and (contains("\\u0000") | not);
  def consistent_exact($values; $label):
    if ($values | all(exact_string)) then
      ($values | unique) as $unique |
      if ($unique | length) == 1 then $unique[0] else error("inconsistent " + $label) end
    else error("incomplete " + $label) end;
  def exact_uuid:
    type == "string" and test("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$");
  def allowed_agent_role:
    . == "sol_advisor_routine" or . == "sol_advisor_high" or . == "sol_advisor_hard" or . == "sol_advisor_advisor";
  def median:
    sort as $values | ($values | length) as $n |
    if $n == 0 then null
    elif ($n % 2) == 1 then $values[$n / 2]
    else (($values[$n / 2 - 1] + $values[$n / 2]) / 2) end;
  . as $records |
  [ .[] | select(.type == "session_meta") | .payload ] as $sessions |
  [ .[] | select(.type == "turn_context") | {payload:.payload,timestamp:(.timestamp? // .payload.timestamp?)} ] as $turns |
  [ .[] | select(.type == "event_msg" and .payload.type == "thread_settings_applied") | .payload.thread_settings.service_tier? | select(. != null) ] as $tiers |
  [ .[] | select(.type == "event_msg" and .payload.type == "token_count") | .payload.info ] as $token_infos |
  [ $token_infos[]?.total_token_usage?.total_tokens | select(type == "number" and . >= 0 and floor == .) ] as $raw_tokens |
  [ $token_infos[]?.last_token_usage?.input_tokens | select(type == "number" and . >= 0 and floor == .) ] as $input_rounds |
  [ .[] | select(.type == "response_item" and ((.payload.type? // "") | endswith("_call"))) ] | length as $tool_calls |
  [ $records[] | select(.type == "context_compacted" or (.type == "event_msg" and .payload.type == "context_compacted")) ] | length as $compactions |
  if ($sessions | length) == 0 or ($turns | length) == 0 then error("missing runtime evidence") else
    if ($turns | any((.timestamp | type != "string") or (.timestamp | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?Z$") | not))) then error("invalid authoritative turn timestamp") else
    ($turns | map({value:.timestamp,epoch:(.timestamp | sub("\\.[0-9]+Z$";"Z") | fromdateiso8601)}) | max_by(.epoch).value) as $latest_event_at |
    ($sessions | map(.id) | unique) as $ids |
    if $ids != [$thread_id] then error("session metadata does not match requested thread") else
    ($sessions | if (all(.parent_thread_id? == null) and all(.agent_role? == null)) then
      {context:"parent",role:null,parentThreadId:null}
    elif (all(.parent_thread_id? | exact_uuid) and all(.agent_role? | allowed_agent_role)) then
      {context:"agent",role:(map(.agent_role) | consistent_exact(.; "agent role")),parentThreadId:(map(.parent_thread_id) | consistent_exact(.; "parent thread"))}
    else error("mixed or incomplete session provenance") end) as $provenance |
    ($turns | map(.payload.model) | consistent_exact(.; "model")) as $model |
    ($turns | map(.payload.effort) | consistent_exact(.; "effort")) as $effort |
    ($turns | map(.payload.sandbox_policy.type) | consistent_exact(.; "sandbox policy type")) as $sandbox |
    ($tiers | unique) as $unique_tiers |
    if ($unique_tiers | length) > 1 then error("inconsistent runtime service tier") else
    {challenge:$challenge,threadId:$thread_id,parentThreadId:$provenance.parentThreadId,latestEventAt:$latest_event_at,evidenceSource:"codex-rollout-inspector",executionContext:$provenance.context,agentIdentifier:$provenance.role,model:$model,effort:$effort,sandboxPolicyType:$sandbox,observedRuntimeTier:(if ($unique_tiers | length) == 0 then null else $unique_tiers[0] end),rawTokens:(if ($raw_tokens | length) == 0 then 0 else ($raw_tokens | max) end),modelRounds:($input_rounds | length),medianInputTokensPerRound:($input_rounds | median),medianInputTokensFirst20:(if ($input_rounds | length) >= 20 then ($input_rounds[:20] | median) else null end),toolCalls:$tool_calls,compactions:$compactions}
    end end end end
' "$rollout_file" 2>/dev/null || fail "rollout is missing, ambiguous, invalid, or lacks allowlisted aggregate evidence."
