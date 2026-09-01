#!/bin/sh
# Emit only allowlisted routing metadata from one exact Codex rollout.

set -eu

usage() {
  cat <<'EOF'
Usage: inspect-agent-runtime.sh [--primary] [--sessions-dir DIR] THREAD_ID

Read the one rollout file whose filename ends with THREAD_ID and emit a compact JSON
object containing only safe routing metadata. Without --sessions-dir, the sessions
root is "$CODEX_HOME/sessions" when CODEX_HOME is already set, otherwise
"$HOME/.codex/sessions".

With --primary, inspect the latest turn of a primary session and require exact
gpt-5.6-sol with high effort.
EOF
}

fail() {
  printf '%s\n' "ERROR: $*" >&2
  exit 1
}

sessions_dir=''
primary=false
thread_id=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --sessions-dir)
      [ "$#" -ge 2 ] || fail "--sessions-dir requires a directory."
      [ -n "$2" ] || fail "--sessions-dir requires a non-empty directory."
      sessions_dir=$2
      shift 2
      ;;
    --primary)
      primary=true
      shift
      ;;
    -*)
      usage >&2
      exit 2
      ;;
    *)
      [ -z "$thread_id" ] || fail "only one THREAD_ID is allowed."
      thread_id=$1
      shift
      ;;
  esac
done

[ -n "$thread_id" ] || {
  usage >&2
  exit 2
}

if ! printf '%s\n' "$thread_id" | LC_ALL=C grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
  fail "THREAD_ID must be a lowercase UUID."
fi

if [ -z "$sessions_dir" ]; then
  if [ -n "${CODEX_HOME-}" ]; then
    sessions_dir=$CODEX_HOME/sessions
  else
    [ -n "${HOME-}" ] || fail "HOME is unset and CODEX_HOME was not supplied; pass --sessions-dir explicitly."
    sessions_dir=$HOME/.codex/sessions
  fi
fi

[ -d "$sessions_dir" ] || fail "sessions directory is unavailable."

tmp_base=${TMPDIR:-/tmp}
case "$tmp_base" in
  /*) ;;
  *) tmp_base=/tmp ;;
esac
matches_file=''

cleanup() {
  if [ -n "$matches_file" ] && [ -f "$matches_file" ]; then
    case "$matches_file" in
      "$tmp_base"/sol-advisor-runtime.*)
        rm -f "$matches_file"
        ;;
      *)
        printf '%s\n' "ERROR: refusing cleanup of unexpected temporary file." >&2
        ;;
    esac
  fi
}

trap cleanup 0 HUP INT TERM

matches_file=$(mktemp "$tmp_base/sol-advisor-runtime.XXXXXX") || fail "could not create a temporary match list."

# Match only the exact rollout filename suffix; do not inspect any rollout contents
# until exactly one filename has been found.
if ! find "$sessions_dir" -type f -name "rollout-*-$thread_id.jsonl" -print > "$matches_file"; then
  fail "could not enumerate rollout filenames under the sessions directory."
fi

match_count=$(awk 'END { print NR + 0 }' "$matches_file")
case "$match_count" in
  0) fail "no rollout filename matched the requested thread id." ;;
  1) ;;
  *) fail "multiple rollout filenames matched the requested thread id." ;;
esac

IFS= read -r rollout_file < "$matches_file" || fail "could not read the matched rollout filename."
[ -f "$rollout_file" ] || fail "matched rollout is unavailable."

# Primary sessions omit auxiliary-only role metadata. Read the latest turn so an
# in-thread model change supersedes older evidence. Emit only six allowlisted fields.
if [ "$primary" = true ]; then
  if ! primary_output=$(jq -ce -s --arg expected_thread_id "$thread_id" '
    def string_or_null:
      if type == "string" then . else null end;
    def lowercase_uuid:
      type == "string" and test("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$");

    [ .[] | select(.type == "session_meta") | .payload ] as $sessions |
    [ .[] | select(.type == "turn_context") | .payload ] as $turns |
    if ($sessions | length) != 1 then
      error("missing or ambiguous session metadata")
    elif ($turns | length) == 0 then
      error("missing turn context")
    else
      $sessions[0] as $session |
      $turns[-1] as $latest |
      ($session.id? | string_or_null) as $session_thread_id |
      ($session.agent_role? | string_or_null) as $agent_role |
      ($latest.turn_id? | string_or_null) as $turn_id |
      ($latest.model? | string_or_null) as $model |
      ($latest.effort? | string_or_null) as $effort |
      (($latest.model_provider? // $session.model_provider?) | string_or_null) as $model_provider |
      ($latest.cwd? | string_or_null) as $cwd |
      if $session_thread_id == null or $session_thread_id != $expected_thread_id then
        error("session metadata does not identify the requested thread")
      elif $agent_role != null and $agent_role != "" then
        error("session metadata identifies an auxiliary role")
      elif ($turn_id | lowercase_uuid | not) then
        error("missing or invalid current turn id")
      elif $model == null or $model == "" then
        error("missing model")
      elif $effort == null or $effort == "" then
        error("missing effort")
      elif $model_provider == null or $model_provider == "" then
        error("missing model provider")
      elif $cwd == null or $cwd == "" then
        error("missing working directory")
      else
        {
          thread_id: $session_thread_id,
          turn_id: $turn_id,
          model: $model,
          effort: $effort,
          model_provider: $model_provider,
          cwd: $cwd
        }
      end
    end
  ' "$rollout_file" 2>/dev/null); then
    fail "primary rollout metadata is missing, ambiguous, invalid, or incomplete."
  fi

  primary_model=$(printf '%s\n' "$primary_output" | jq -r '.model')
  primary_effort=$(printf '%s\n' "$primary_output" | jq -r '.effort')
  case "$primary_model:$primary_effort" in
    *[!A-Za-z0-9._:-]*) fail "primary model or effort contains unsupported characters." ;;
  esac
  if [ "$primary_model" != gpt-5.6-sol ] || [ "$primary_effort" != high ]; then
    fail "primary runtime mismatch: expected model=gpt-5.6-sol effort=high; observed model=$primary_model effort=$primary_effort."
  fi
  printf '%s\n' "$primary_output"
  exit 0
fi

# The jq program reads only the matched JSONL and constructs a new allowlisted object.
# It rejects absent or conflicting required routing values instead of inferring them.
if ! jq -ce -s --arg expected_thread_id "$thread_id" '
  def string_or_null:
    if type == "string" then . else null end;

  [ .[] | select(.type == "session_meta") | .payload ] as $sessions |
  [ .[] | select(.type == "turn_context") | .payload ] as $turns |
  if ($sessions | length) != 1 then
    error("missing or ambiguous session metadata")
  elif ($turns | length) == 0 then
    error("missing turn context")
  else
    $sessions[0] as $session |
    ($session.id? | string_or_null) as $session_thread_id |
    ($session.parent_thread_id? | string_or_null) as $parent_thread_id |
    ($session.agent_role? | string_or_null) as $agent_role |
    ($session.agent_path? | string_or_null) as $agent_path |
    ($session.model_provider? | string_or_null) as $model_provider |
    [ $turns[] | (.model? | string_or_null) ] as $models |
    [ $turns[] | (.effort? | string_or_null) ] as $efforts |
    [ $turns[] | ((.sandbox_policy? // {}) | .type? | string_or_null) ] as $sandbox_types |
    [ $turns[] | ((.permission_profile? // {}) | .type? | string_or_null) ] as $permission_types |
    [ $turns[] | (.cwd? | string_or_null) ] as $cwds |
    if $session_thread_id == null or $session_thread_id != $expected_thread_id then
      error("session metadata does not identify the requested thread")
    elif $agent_role == null or $agent_role == "" then
      error("missing agent role")
    elif any($models[]; . == null or . == "") then
      error("missing model")
    elif any($efforts[]; . == null or . == "") then
      error("missing effort")
    elif ($models | unique | length) != 1 then
      error("conflicting models")
    elif ($efforts | unique | length) != 1 then
      error("conflicting efforts")
    elif ($sandbox_types | unique | length) != 1 then
      error("conflicting sandbox policy types")
    elif ($permission_types | unique | length) != 1 then
      error("conflicting permission profile types")
    elif ($cwds | unique | length) != 1 then
      error("conflicting working directories")
    else
      {
        thread_id: $session_thread_id,
        parent_thread_id: $parent_thread_id,
        agent_role: $agent_role,
        agent_path: $agent_path,
        model_provider: $model_provider,
        model: $models[0],
        effort: $efforts[0],
        sandbox_policy_type: $sandbox_types[0],
        permission_profile_type: $permission_types[0],
        cwd: $cwds[0]
      }
    end
  end
' "$rollout_file" 2>/dev/null; then
  fail "rollout is missing, ambiguous, invalid, or inconsistent required routing metadata."
fi
