#!/bin/sh
# Repository-local verification for Sol Advisor's two-role companion migration.

set -eu

pass() { printf '%s\n' "PASS: $*"; }
fail() { printf '%s\n' "FAIL: $*" >&2; exit 1; }

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd) || exit 1
plugin_dir=$(CDPATH= cd "$script_dir/.." && pwd) || exit 1
repo_dir=$(CDPATH= cd "$plugin_dir/../.." && pwd) || exit 1
installer=$script_dir/install-agents.sh
runtime_inspector=$script_dir/inspect-agent-runtime.sh
templates=$plugin_dir/agents
manifest=$plugin_dir/.codex-plugin/plugin.json
skill=$plugin_dir/skills/orchestration/SKILL.md
contracts=$plugin_dir/skills/orchestration/references/role-contracts.md
luna_contract=$plugin_dir/skills/orchestration/references/luna-task-lane.md
readme=$repo_dir/README.md
ui=$plugin_dir/skills/orchestration/agents/openai.yaml

tmp_base=${TMPDIR:-/tmp}
case "$tmp_base" in /*) ;; *) tmp_base=/tmp ;; esac
tmp_dir=''
cleanup() {
  if [ -n "$tmp_dir" ] && [ -d "$tmp_dir" ]; then
    case "$tmp_dir" in
      "$tmp_base"/sol-advisor-verify.*) rm -rf "$tmp_dir" ;;
      *) printf '%s\n' "REFUSING cleanup of unexpected directory: $tmp_dir" >&2 ;;
    esac
  fi
}
trap cleanup 0 HUP INT TERM
tmp_dir=$(mktemp -d "$tmp_base/sol-advisor-verify.XXXXXX") || fail "could not create disposable verification directory"

terra_file=sol-advisor-terra-implementer.toml
sol_file=sol-advisor-sol-reviewer.toml
luna_file=sol-advisor-luna-implementer.toml
legacy_terra_sha256=4425a8c1f21ce8c6af93f96adc253bbc33ea301f1389b3fa8ce350be08584eca
legacy_luna_sha256=fba1b42849d93737e83b094a2ab0b1611f87ac37db7438c8bbdf581f0813f8eb

snapshot_files() {
  target=$1
  if [ ! -d "$target" ]; then
    printf '%s\n' MISSING
    return
  fi
  find "$target" -mindepth 1 -maxdepth 1 -print | LC_ALL=C sort | while IFS= read -r path; do
    if [ -L "$path" ]; then
      printf 'L %s -> %s\n' "$(basename "$path")" "$(readlink "$path")"
    elif [ -f "$path" ]; then
      shasum -a 256 "$path"
    else
      printf 'O %s\n' "$(basename "$path")"
    fi
  done
}

write_legacy_roles() {
  target=$1
  mkdir -p "$target"
  cat > "$target/$terra_file" <<'LEGACY_TERRA'
name = "sol_advisor_terra_implementer"
description = "Sol Advisor's complex implementation lane for context-heavy or higher-risk work."
model = "gpt-5.6-terra"
model_reasoning_effort = "max"

developer_instructions = """
You are Sol Advisor's complex implementation worker. Resolve difficult implementation
details within the settled architecture, including context-heavy, higher-risk, or
wider-blast-radius work. Preserve every stated interface and constraint, stay within
the owned file set, and document material judgment calls.

You are not alone in the codebase: preserve concurrent edits and do not revert
unrelated work. Surface ambiguity, scope conflicts, or verification failures rather
than changing the architecture without direction. Run the requested checks and report
actual evidence. Do not silently substitute a different role, model, or reasoning
level; this installed custom-agent profile is the required complex lane.
"""
LEGACY_TERRA
  cat > "$target/$luna_file" <<'LEGACY_LUNA'
name = "sol_advisor_luna_implementer"
description = "Sol Advisor's routine implementation lane for bounded, fully specified work."
model = "gpt-5.6-luna"
model_reasoning_effort = "max"

developer_instructions = """
You are Sol Advisor's routine implementation worker. Execute the supplied five-part
implementation specification exactly when it is bounded and largely determined by
the contract. Preserve stated interfaces and constraints, make only the files you
own, and adapt to concurrent edits instead of reverting work you do not own.

Surface material ambiguity, missing acceptance criteria, scope conflicts, or failed
verification rather than redesigning the architecture. Run the requested checks and
report actual evidence. Do not silently substitute a different role, model, or
reasoning level; this installed custom-agent profile is the required routine lane.
"""
LEGACY_LUNA
  cp "$templates/$sol_file" "$target/$sol_file"
  [ "$(shasum -a 256 "$target/$terra_file" | awk '{print $1}')" = "$legacy_terra_sha256" ] || fail "legacy Terra fixture digest drifted"
  [ "$(shasum -a 256 "$target/$luna_file" | awk '{print $1}')" = "$legacy_luna_sha256" ] || fail "legacy Luna fixture digest drifted"
}

for required in "$installer" "$runtime_inspector" "$manifest" "$skill" "$contracts" "$luna_contract" "$readme" "$ui"; do
  test -f "$required" || fail "required file missing: $required"
done

jq empty "$manifest"
[ "$(jq -r '.version' "$manifest")" = 0.5.0 ] || fail "manifest version is not 0.5.0"
grep -Fq 'explicit opt-in' "$manifest" || fail "manifest does not describe explicit Luna opt-in"
grep -Fqi 'GPT-5.6 Luna' "$manifest" || fail "manifest does not describe Luna routing"
grep -Fq 'Codex app task tools' "$manifest" || fail "manifest does not describe app-task routing"
grep -Fq 'fresh Sol' "$manifest" || fail "manifest does not preserve native fresh Sol review"
pass "manifest JSON, version, and both-mode UI language"

python3 - "$templates" <<'PY'
from pathlib import Path
import sys, tomllib

root = Path(sys.argv[1])
expected = {
    "sol-advisor-terra-implementer.toml": {
        "name": "sol_advisor_terra_implementer",
        "model": "gpt-5.6-terra",
        "model_reasoning_effort": "high",
    },
    "sol-advisor-sol-reviewer.toml": {
        "name": "sol_advisor_sol_reviewer",
        "model": "gpt-5.6-sol",
        "model_reasoning_effort": "high",
        "sandbox_mode": "read-only",
    },
}
actual = {path.name for path in root.glob("*.toml")}
if actual != set(expected):
    raise SystemExit(f"expected exactly {sorted(expected)}, found {sorted(actual)}")
for filename, pins in expected.items():
    data = tomllib.loads((root / filename).read_text(encoding="utf-8"))
    for field in ("name", "description", "developer_instructions"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise SystemExit(f"{filename}: missing {field}")
    for field, value in pins.items():
        if data.get(field) != value:
            raise SystemExit(f"{filename}: {field}={data.get(field)!r}, expected {value!r}")
print("two exact role pins are valid")
PY
pass "exact two-role TOML inventory"

grep -Fq "legacy_terra_sha256=$legacy_terra_sha256" "$installer" || fail "installer legacy Terra digest mismatch"
grep -Fq "legacy_luna_sha256=$legacy_luna_sha256" "$installer" || fail "installer legacy Luna digest mismatch"
pass "immutable v0.2.0 migration fingerprints"

clean_target=$tmp_dir/clean
sh "$installer" --target-dir "$clean_target"
cmp -s "$templates/$terra_file" "$clean_target/$terra_file" || fail "clean Terra install mismatch"
cmp -s "$templates/$sol_file" "$clean_target/$sol_file" || fail "clean Sol install mismatch"
test ! -e "$clean_target/$luna_file" || fail "clean install created retired Luna role"
sh "$installer" --target-dir "$clean_target" --check
before=$(snapshot_files "$clean_target")
sh "$installer" --target-dir "$clean_target"
after=$(snapshot_files "$clean_target")
[ "$before" = "$after" ] || fail "idempotent install changed current roles"
pass "clean install, exact check, and idempotence"

missing_target=$tmp_dir/missing
if sh "$installer" --target-dir "$missing_target" --check; then fail "--check accepted missing target"; fi
test ! -e "$missing_target" || fail "--check mutated missing target"
pass "missing-target check refusal is non-mutating"

codex_home=$tmp_dir/codex-home
CODEX_HOME="$codex_home" sh "$installer"
cmp -s "$templates/$terra_file" "$codex_home/agents/$terra_file" || fail "CODEX_HOME Terra mismatch"
cmp -s "$templates/$sol_file" "$codex_home/agents/$sol_file" || fail "CODEX_HOME Sol mismatch"
test ! -e "$codex_home/config.toml" || fail "installer created config.toml"
relative_parent=$tmp_dir/relative-parent
mkdir "$relative_parent"
(cd "$relative_parent" && sh "$installer" --target-dir relative-agents)
cmp -s "$templates/$terra_file" "$relative_parent/relative-agents/$terra_file" || fail "relative target Terra mismatch"
pass "CODEX_HOME and relative target behavior"

migration_target=$tmp_dir/migration
write_legacy_roles "$migration_target"
sh "$installer" --target-dir "$migration_target"
cmp -s "$templates/$terra_file" "$migration_target/$terra_file" || fail "legacy Terra was not migrated"
cmp -s "$templates/$sol_file" "$migration_target/$sol_file" || fail "Sol changed during migration"
test ! -e "$migration_target/$luna_file" || fail "exact legacy Luna was not removed"
sh "$installer" --target-dir "$migration_target" --check
pass "exact v0.2.0 Terra replacement and Luna retirement"

modified_luna=$tmp_dir/modified-luna
write_legacy_roles "$modified_luna"
printf '%s\n' modified >> "$modified_luna/$luna_file"
before=$(snapshot_files "$modified_luna")
if sh "$installer" --target-dir "$modified_luna"; then fail "installer removed modified Luna"; fi
after=$(snapshot_files "$modified_luna")
[ "$before" = "$after" ] || fail "modified-Luna refusal partially mutated target"
pass "modified Luna refusal with zero partial mutation"

modified_terra=$tmp_dir/modified-terra
write_legacy_roles "$modified_terra"
printf '%s\n' modified >> "$modified_terra/$terra_file"
before=$(snapshot_files "$modified_terra")
if sh "$installer" --target-dir "$modified_terra"; then fail "installer replaced modified Terra"; fi
after=$(snapshot_files "$modified_terra")
[ "$before" = "$after" ] || fail "modified-Terra refusal partially mutated target"
pass "modified Terra refusal with zero partial mutation"

stale_luna=$tmp_dir/stale-luna
sh "$installer" --target-dir "$stale_luna"
stale_fixture=$tmp_dir/stale-fixture
write_legacy_roles "$stale_fixture"
cp "$stale_fixture/$luna_file" "$stale_luna/$luna_file"
before=$(snapshot_files "$stale_luna")
if sh "$installer" --target-dir "$stale_luna" --check; then fail "--check accepted stale Luna"; fi
after=$(snapshot_files "$stale_luna")
[ "$before" = "$after" ] || fail "stale-Luna check mutated target"
pass "stale Luna check refusal is non-mutating"

unsafe=$tmp_dir/unsafe
mkdir "$unsafe"
ln -s "$templates/$terra_file" "$unsafe/$terra_file"
before=$(snapshot_files "$unsafe")
if sh "$installer" --target-dir "$unsafe"; then fail "installer accepted symlinked Terra"; fi
after=$(snapshot_files "$unsafe")
[ "$before" = "$after" ] || fail "symlink refusal partially mutated target"
test ! -e "$unsafe/$sol_file" || fail "symlink refusal partially installed Sol"
pass "unsafe destination refusal with zero partial mutation"

runtime_sessions=$tmp_dir/runtime-sessions
runtime_day=$runtime_sessions/2026/08/02
mkdir -p "$runtime_day"
runtime_id=11111111-1111-7111-8111-111111111111
runtime_rollout=$runtime_day/rollout-2026-08-02T00-00-00-$runtime_id.jsonl
printf '%s\n' \
  '{"type":"response_item","payload":{"prompt":"DO_NOT_LEAK_PROMPT"}}' \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$runtime_id\",\"parent_thread_id\":\"00000000-0000-7000-8000-000000000000\",\"agent_role\":\"sol_advisor_terra_implementer\",\"agent_path\":\"/root/fixture\",\"model_provider\":\"openai\",\"cwd\":\"/fixture\"}}" \
  '{"type":"turn_context","payload":{"model":"gpt-5.6-terra","effort":"high","sandbox_policy":{"type":"danger-full-access"},"permission_profile":{"type":"disabled"},"cwd":"/fixture"}}' \
  > "$runtime_rollout"
runtime_output=$(sh "$runtime_inspector" --sessions-dir "$runtime_sessions" "$runtime_id")
printf '%s\n' "$runtime_output" | jq -e --arg id "$runtime_id" '
  .thread_id == $id and .agent_role == "sol_advisor_terra_implementer"
  and .model == "gpt-5.6-terra" and .effort == "high"
  and .sandbox_policy_type == "danger-full-access"
  and .permission_profile_type == "disabled"
' >/dev/null || fail "runtime inspector returned wrong Terra/High evidence"
if printf '%s\n' "$runtime_output" | grep -Fq DO_NOT_LEAK; then fail "runtime inspector leaked payload"; fi
if sh "$runtime_inspector" --sessions-dir "$runtime_sessions" invalid >/dev/null 2>&1; then fail "runtime inspector accepted invalid id"; fi
zero_id=22222222-2222-7222-8222-222222222222
if sh "$runtime_inspector" --sessions-dir "$runtime_sessions" "$zero_id" >/dev/null 2>&1; then fail "runtime inspector accepted zero matches"; fi
pass "runtime inspector Terra/High routing and safe refusal"

for document in "$skill" "$contracts"; do
  grep -Fq 'agent_type: sol_advisor_terra_implementer' "$document" || fail "missing Terra spawn in $document"
  grep -Fq 'agent_type: sol_advisor_sol_reviewer' "$document" || fail "missing Sol spawn in $document"
  grep -Fq 'fork_turns: none' "$document" || fail "missing fresh context in $document"
  if grep -Eq 'agent_type:.*(luna|terra_max)' "$document"; then fail "retired implementation spawn remains in $document"; fi
  if grep -Eq '^[[:space:]]*(model|reasoning_effort):' "$document"; then fail "per-spawn override remains in $document"; fi
done
grep -Fq '../../scripts/install-agents.sh' "$skill" || fail "skill does not resolve installer relatively"
grep -Fq '../../scripts/inspect-agent-runtime.sh' "$skill" || fail "skill does not resolve inspector relatively"
grep -Fqi 'public native spawn/details metadata first' "$skill" || fail "skill lacks public-details-first evidence rule"
grep -Fqi 'parent captures and verifies exact before-and-after' "$contracts" || fail "contracts lack behavioral read-only state check"
grep -Fq 'luna-task-lane.md' "$skill" || fail "skill does not link the Luna task contract"
grep -Fq 'luna-task-lane.md' "$contracts" || fail "role contracts do not link the Luna task contract"

for tool in list_projects list_threads create_thread wait_threads read_thread send_message_to_thread; do
  for document in "$skill" "$contracts" "$luna_contract" "$readme"; do
    grep -Fq "$tool" "$document" || fail "$document omits Luna app tool: $tool"
  done
done
grep -Fq 'gpt-5.6-luna' "$skill" || fail "skill omits Luna model"
grep -Fq 'thinking` to `max' "$skill" || fail "skill omits Luna Max routing"
grep -Fq 'isGitRepository' "$luna_contract" || fail "Luna contract omits Git-project check"
grep -Fq 'isolated worktree environment' "$luna_contract" || fail "Luna contract omits Git worktree default"
grep -Fq 'clientThreadId' "$luna_contract" || fail "Luna contract omits setup-pending identity guard"
grep -Fq 'same ready' "$luna_contract" || fail "Luna contract omits same-task correction rule"
grep -Fq 'PR AUTHORIZED FOR' "$luna_contract" || fail "Luna contract omits explicit PR authorization"
grep -Fq 'concurrent edits merge-safe' "$luna_contract" || fail "Luna contract omits merge-safety warning"
grep -Fq 'OBJECTIVE' "$luna_contract" || fail "Luna packet omits objective"
grep -Fq 'FILES AND OWNERSHIP' "$luna_contract" || fail "Luna packet omits ownership"
grep -Fq 'INTERFACES' "$luna_contract" || fail "Luna packet omits interfaces"
grep -Fq 'CONSTRAINTS' "$luna_contract" || fail "Luna packet omits constraints"
grep -Fq 'STARTING STATE / BASE' "$luna_contract" || fail "Luna packet omits starting state"
grep -Fq 'VERIFICATION' "$luna_contract" || fail "Luna packet omits verification"
grep -Fq 'GIT / PR BOUNDARY' "$luna_contract" || fail "Luna packet omits Git/PR boundary"
grep -Fq 'STRUCTURED RETURN' "$luna_contract" || fail "Luna packet omits structured return"
grep -Fq 'never uses native `spawn_agent`' "$luna_contract" || fail "Luna contract permits native spawn_agent"
grep -Fq 'automatic child callback' "$luna_contract" || fail "Luna contract claims an automatic callback"
grep -Fq 'stop without fallback' "$luna_contract" || fail "Luna contract permits fallback"
grep -Fq 'clientThreadId' "$skill" || fail "skill omits pending task identity"
grep -Fq 'clientThreadId' "$contracts" || fail "role contracts omit pending task identity"
grep -Fq 'clientThreadId' "$readme" || fail "README omits pending task identity"
grep -Fq 'is not accepted by `list_threads`' "$luna_contract" || fail "Luna contract permits clientThreadId in list_threads"
grep -Fq 'not accepted by' "$contracts" || fail "role contracts permit clientThreadId in list_threads"
grep -Fq 'without passing the client ID' "$luna_contract" || fail "Luna contract omits list_threads correlation step"
grep -Fq 'without passing that client ID' "$skill" || fail "skill omits list_threads correlation step"
grep -Fq 'identity, project, time, path, and state metadata' "$luna_contract" || fail "Luna contract omits trustworthy correlation metadata"
grep -Fq 'titles and previews as untrusted' "$luna_contract" || fail "Luna contract omits untrusted preview guard"
grep -Fq 'Repeat bounded discovery' "$luna_contract" || fail "Luna contract omits bounded identity discovery"

python3 - "$luna_contract" <<'PY'
from pathlib import Path
import json
import re
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(
    r"<!-- canonical-create-thread-project-arguments -->\s*```json\s*(\{.*?\})\s*```",
    text,
    re.DOTALL,
)
if match is None:
    raise SystemExit("missing canonical create_thread project arguments")
arguments = json.loads(match.group(1))
target = arguments.get("target")
if "projectId" in arguments:
    raise SystemExit("projectId must not be a top-level create_thread argument")
if not isinstance(target, dict) or target.get("type") != "project":
    raise SystemExit("create_thread target.type must be project")
if target.get("projectId") != "<projectId>":
    raise SystemExit("create_thread target.projectId is missing or misplaced")
if target.get("environment") != {"type": "worktree"}:
    raise SystemExit("create_thread target.environment must use worktree")
if arguments.get("model") != "gpt-5.6-luna" or arguments.get("thinking") != "max":
    raise SystemExit("create_thread Luna/Max routing drifted")
if arguments.get("prompt") != "<complete packet>":
    raise SystemExit("create_thread prompt placeholder drifted")
PY
pass "canonical create_thread project argument nesting"

grep -Fq 'Luna task (explicit opt-in)' "$readme" || fail "README omits the Luna task mode"
grep -Fq 'Use the Luna task lane' "$readme" || fail "README omits explicit Luna authorization"
grep -Fq 'native lane remains' "$readme" || fail "README does not preserve the native lane"
grep -Fq 'does not use a Luna' "$readme" || fail "README permits a Luna companion TOML"
grep -Fq 'user-visible GPT-5.6 Luna / Max tasks' "$manifest" || fail "manifest UI omits user-visible Luna tasks"
grep -Fq 'list_threads' "$manifest" || fail "manifest UI omits list_threads"
grep -Fq 'list_threads' "$ui" || fail "skill UI omits list_threads"
grep -Fq 'Requirements common to both modes' "$readme" || fail "README omits common requirements"
grep -Fq 'Additional native-mode requirements' "$readme" || fail "README omits native-only requirements"
grep -Fq 'Additional Luna task-mode requirements' "$readme" || fail "README omits Luna-only requirements"
grep -Fq 'can be skipped for Luna-only use' "$readme" || fail "README does not allow skipping companions for Luna-only use"
grep -Fq 'do not require native subagents, Terra access' "$readme" || fail "README makes native requirements mandatory for Luna-only use"
grep -Fq 'Luna-only users do not need to' "$readme" || fail "README local guidance requires companions for Luna-only use"
if grep -Fq 'with plugins, native subagents, and' "$readme"; then
  fail "README still makes native capabilities a common requirement"
fi
grep -Fq 'explicitly opt into Luna' "$ui" || fail "skill UI omits explicit Luna opt-in"

for document in "$readme" "$manifest" "$skill" "$contracts" "$ui"; do
  if grep -Eqi 'Terra / High is the sole implementation producer|one role-pinned .*handles all implementation|route all implementation through.*Terra|delegate all implementation to (the )?(native )?Terra' "$document"; then
    fail "stale single-mode implementation claim remains in $document"
  fi
done
forbidden_terra='sol_advisor_terra_'"max"
forbidden_file='sol-advisor-terra-'"max"
if grep -ERn "$forbidden_terra|$forbidden_file" "$readme" "$plugin_dir"; then fail "forbidden second Terra role remains"; fi
pass "native and Luna contracts, opt-in guards, and stale-claim checks"

sh -n "$installer"
sh -n "$runtime_inspector"
sh -n "$script_dir/verify.sh"
pass "shell syntax"

printf '%s\n' "VERIFY PASSED: Sol Advisor two-role migration checks completed in $tmp_dir"
