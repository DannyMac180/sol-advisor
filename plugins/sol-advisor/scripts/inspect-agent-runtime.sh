#!/bin/sh
# Emit only allowlisted routing metadata from one exact native subagent rollout.

set -eu

usage() {
  cat <<'EOF'
Usage: inspect-agent-runtime.sh [--sessions-dir DIR] THREAD_ID
       inspect-agent-runtime.sh [--sessions-dir DIR] --agent-path PATH --since RFC3339

Read one exact rollout selected by its lowercase UUID, or resolve one canonical native
agent path created at or after an RFC3339 cutoff. Emit a compact JSON object containing
only safe routing metadata. Without --sessions-dir, the sessions root is
"$CODEX_HOME/sessions" when CODEX_HOME is already set, otherwise
"$HOME/.codex/sessions".
EOF
}

fail() {
  printf '%s\n' "ERROR: $*" >&2
  exit 1
}

usage_fail() {
  usage >&2
  exit 2
}

# jq represents an instant as integer UTC base seconds, a leap phase, and a
# trailing-zero-trimmed fractional string to avoid epoch floating-point rounding.
timestamp_jq='
def leap_year($year):
  (($year % 4 == 0) and (($year % 100 != 0) or ($year % 400 == 0)));

def days_in_month($year; $month):
  if $month == 2 then (if leap_year($year) then 29 else 28 end)
  elif ($month == 4 or $month == 6 or $month == 9 or $month == 11) then 30
  else 31
  end;

# Days since 0000-03-01 in the proleptic Gregorian calendar. Integer arithmetic only.
def days_from_civil($year; $month; $day):
  ($year - (if $month <= 2 then 1 else 0 end)) as $y |
  ($y / 400 | floor) as $era |
  ($y - ($era * 400)) as $yoe |
  ($month + (if $month > 2 then -3 else 9 end)) as $mp |
  (((153 * $mp + 2) / 5 | floor) + $day - 1) as $doy |
  ($yoe * 365 + ($yoe / 4 | floor) - ($yoe / 100 | floor) + $doy) as $doe |
  ($era * 146097 + $doe);

def civil_from_days($days):
  ($days / 146097 | floor) as $era |
  ($days - ($era * 146097)) as $doe |
  (($doe - ($doe / 1460 | floor) + ($doe / 36524 | floor) - ($doe / 146096 | floor)) / 365 | floor) as $yoe |
  ($yoe + ($era * 400)) as $year |
  ($doe - ($yoe * 365) - ($yoe / 4 | floor) + ($yoe / 100 | floor)) as $doy |
  ((5 * $doy + 2) / 153 | floor) as $month_prime |
  ($doy - ((153 * $month_prime + 2) / 5 | floor) + 1) as $day |
  ($month_prime + (if $month_prime < 10 then 3 else -9 end)) as $month |
  {year: ($year + (if $month <= 2 then 1 else 0 end)), month: $month, day: $day};

def padded($width):
  tostring as $text | ($width - ($text | length)) as $padding |
  if $padding > 0 then ("0" * $padding) + $text else $text end;

def rfc3339_instant($value):
  ($value | capture("^(?<year>[0-9]{4})-(?<month>[0-9]{2})-(?<day>[0-9]{2})[Tt](?<hour>[0-9]{2}):(?<minute>[0-9]{2}):(?<second>[0-9]{2})(?<fraction>\\.[0-9]+)?(?<zone>[Zz]|[+-][0-9]{2}:[0-9]{2})$")) as $parts |
  ($parts.year | tonumber) as $year |
  ($parts.month | tonumber) as $month |
  ($parts.day | tonumber) as $day |
  ($parts.hour | tonumber) as $hour |
  ($parts.minute | tonumber) as $minute |
  ($parts.second | tonumber) as $second |
  if $month < 1 or $month > 12 then error("invalid month")
  elif $day < 1 or $day > days_in_month($year; $month) then error("invalid day")
  elif $hour > 23 or $minute > 59 or $second > 60 then error("invalid time")
  else
    ($parts.zone) as $zone |
    (if $zone == "Z" or $zone == "z" then 0
     elif $zone == "-00:00" then error("unknown offset")
     else
       ($zone | capture("^(?<sign>[+-])(?<hour>[0-9]{2}):(?<minute>[0-9]{2})$")) as $offset |
       ($offset.hour | tonumber) as $offset_hour |
       ($offset.minute | tonumber) as $offset_minute |
       if $offset_hour > 23 or $offset_minute > 59 then error("invalid offset")
       else
         (($offset_hour * 3600 + $offset_minute * 60) *
          (if $offset.sign == "+" then 1 else -1 end))
       end
     end) as $offset_seconds |
    ((days_from_civil($year; $month; $day) * 86400) + ($hour * 3600) +
     ($minute * 60) + (if $second == 60 then 59 else $second end) - $offset_seconds) as $seconds |
    (if $second == 60 and ($seconds - (($seconds / 86400 | floor) * 86400)) != 86399 then
       error("invalid leap second")
     else
       {seconds: $seconds, leap_phase: (if $second == 60 then 1 else 0 end),
        fraction: (($parts.fraction // "") | sub("^\\."; "") | sub("0+$"; ""))}
     end)
  end;

def timestamp_gte($candidate; $cutoff):
  if $candidate.seconds > $cutoff.seconds then true
  elif $candidate.seconds < $cutoff.seconds then false
  elif $candidate.leap_phase > $cutoff.leap_phase then true
  elif $candidate.leap_phase < $cutoff.leap_phase then false
  else
    ([$candidate.fraction | length, $cutoff.fraction | length] | max) as $width |
    ($candidate.fraction + ("0" * ($width - ($candidate.fraction | length)))) as $candidate_fraction |
    ($cutoff.fraction + ("0" * ($width - ($cutoff.fraction | length)))) as $cutoff_fraction |
    $candidate_fraction >= $cutoff_fraction
  end;

# Session directories are calendar-day partitions. Include the day before the UTC
# cutoff day because session metadata can carry any known RFC3339 offset.
def scan_from_date($value):
  rfc3339_instant($value) as $instant |
  ((($instant.seconds / 86400) | floor) - 1) as $day_number |
  civil_from_days($day_number) as $civil |
  if $civil.year < 0 or $civil.year > 9999 then null
  else "\($civil.year | padded(4))/\($civil.month | padded(2))/\($civil.day | padded(2))"
  end;
'

sessions_dir=''
thread_id=''
agent_path=''
since=''
seen_sessions_dir=0
seen_agent_path=0
seen_since=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --sessions-dir)
      [ "$seen_sessions_dir" -eq 0 ] || usage_fail
      [ "$#" -ge 2 ] || usage_fail
      sessions_dir=$2
      seen_sessions_dir=1
      shift 2
      ;;
    --agent-path)
      [ "$seen_agent_path" -eq 0 ] || usage_fail
      [ "$#" -ge 2 ] || usage_fail
      agent_path=$2
      seen_agent_path=1
      shift 2
      ;;
    --since)
      [ "$seen_since" -eq 0 ] || usage_fail
      [ "$#" -ge 2 ] || usage_fail
      since=$2
      seen_since=1
      shift 2
      ;;
    --*) usage_fail ;;
    *)
      [ -z "$thread_id" ] || usage_fail
      thread_id=$1
      shift
      ;;
  esac
done

if [ "$seen_agent_path" -eq 1 ]; then
  [ -z "$thread_id" ] || usage_fail
  [ "$seen_since" -eq 1 ] || usage_fail
elif [ "$seen_since" -eq 1 ]; then
  usage_fail
elif [ -z "$thread_id" ]; then
  usage_fail
fi

if [ "$seen_sessions_dir" -eq 1 ] && [ -z "$sessions_dir" ]; then
  fail "--sessions-dir requires a non-empty directory."
fi

if [ "$seen_agent_path" -eq 1 ]; then
  if ! printf '%s\n' "$agent_path" | LC_ALL=C grep -Eq '^/root/[a-z0-9_]+(/[a-z0-9_]+)*$'; then
    fail "--agent-path must be a canonical non-empty /root/<task> path."
  fi
  if ! jq -en --arg timestamp "$since" "$timestamp_jq rfc3339_instant(\$timestamp)" >/dev/null 2>&1; then
    fail "--since must be a valid known-offset RFC3339 timestamp."
  fi
else
  if ! printf '%s\n' "$thread_id" | LC_ALL=C grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
    fail "THREAD_ID must be a lowercase UUID."
  fi
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
candidates_file=''
directories_file=''

cleanup() {
  for temporary_file in "$matches_file" "$candidates_file" "$directories_file"; do
    if [ -n "$temporary_file" ] && [ -f "$temporary_file" ]; then
      case "$temporary_file" in
        "$tmp_base"/sol-advisor-runtime.*)
          rm -f "$temporary_file"
          ;;
        *)
          printf '%s\n' "ERROR: refusing cleanup of unexpected temporary file." >&2
          ;;
      esac
    fi
  done
}

trap cleanup 0 HUP INT TERM

select_scan_directories() {
  cutoff_directory=$1
  if [ -z "$cutoff_directory" ]; then
    printf '%s\n' "$sessions_dir" > "$directories_file"
    return
  fi
  if ! find "$sessions_dir" -type d -mindepth 3 -maxdepth 3 -print > "$matches_file"; then
    return 1
  fi
  canonical_count=$(awk -v root="$sessions_dir" '
    BEGIN { prefix = root "/"; count = 0 }
    index($0, prefix) == 1 {
      relative = substr($0, length(prefix) + 1)
      if (relative ~ /^[0-9][0-9][0-9][0-9]\/[0-9][0-9]\/[0-9][0-9]$/) count++
    }
    END { print count + 0 }
  ' "$matches_file")
  if [ "$canonical_count" -eq 0 ]; then
    printf '%s\n' "$sessions_dir" > "$directories_file"
    return
  fi
  awk -v root="$sessions_dir" -v cutoff="$cutoff_directory" '
    BEGIN { prefix = root "/" }
    index($0, prefix) == 1 {
      relative = substr($0, length(prefix) + 1)
      if (relative ~ /^[0-9][0-9][0-9][0-9]\/[0-9][0-9]\/[0-9][0-9]$/ && relative >= cutoff) print
    }
  ' "$matches_file" > "$directories_file"
}

matches_file=$(mktemp "$tmp_base/sol-advisor-runtime.XXXXXX") || fail "could not create a temporary match list."

if [ "$seen_agent_path" -eq 1 ]; then
  # Search only session metadata records. A candidate has the exact returned native
  # task path and an inclusive timestamp at or after the pre-spawn cutoff.
  candidates_file=$(mktemp "$tmp_base/sol-advisor-runtime.XXXXXX") || fail "could not create a temporary candidate list."
  directories_file=$(mktemp "$tmp_base/sol-advisor-runtime.XXXXXX") || fail "could not create a temporary directory list."
  scan_from=$(jq -nr --arg timestamp "$since" "$timestamp_jq scan_from_date(\$timestamp)" 2>/dev/null || true)
  case "$scan_from" in
    [0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]) ;;
    *) scan_from='' ;;
  esac
  select_scan_directories "$scan_from" || fail "could not enumerate session date directories."
  if ! while IFS= read -r scan_directory; do
    # find passes filenames directly to bounded streaming jq invocations; no xargs,
    # filename parsing, or rollout slurping is involved.
    find "$scan_directory" -type f -name 'rollout-*.jsonl' -exec jq -cr --arg expected_path "$agent_path" --arg since "$since" "$timestamp_jq
      rfc3339_instant(\$since) as \$cutoff |
      if type != \"object\" then error(\"malformed JSONL record\")
      elif .type != \"session_meta\" then empty
      elif ((.payload? | type) != \"object\") then error(\"malformed session metadata\")
      elif .payload.agent_path? != \$expected_path then empty
      elif ((.payload.id? | type) != \"string\") or (.payload.id == \"\") then error(\"missing session id\")
      elif ((.timestamp? | type) != \"string\") or (.timestamp == \"\") then error(\"missing session timestamp\")
      else
        rfc3339_instant(.timestamp) as \$candidate |
        if timestamp_gte(\$candidate; \$cutoff) then
          {input_filename: input_filename, thread_id: .payload.id}
        else empty end
      end" {} + 2>/dev/null >> "$candidates_file" || exit 1
  done < "$directories_file"; then
    fail "session metadata is malformed or could not be read."
  fi

  match_count=$(awk 'END { print NR + 0 }' "$candidates_file")
  case "$match_count" in
    0) fail "no session metadata matched the requested agent path and cutoff." ;;
    1) ;;
    *) fail "multiple session metadata records matched the requested agent path and cutoff." ;;
  esac
  if ! thread_id=$(jq -er '
    if type == "object" and (.input_filename | type) == "string" and .input_filename != ""
      and (.thread_id | type) == "string" and .thread_id != ""
    then .thread_id else error("invalid candidate") end
  ' "$candidates_file" 2>/dev/null); then
    fail "session metadata candidate is invalid."
  fi
  if ! candidate_rollout=$(jq -er '.input_filename' "$candidates_file" 2>/dev/null); then
    fail "session metadata candidate is invalid."
  fi
  if ! printf '%s\n' "$thread_id" | LC_ALL=C grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
    fail "session metadata contains an invalid thread id."
  fi
fi

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
if [ "$seen_agent_path" -eq 1 ] && [ "$rollout_file" != "$candidate_rollout" ]; then
  fail "session metadata does not bind to the matched rollout filename."
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
