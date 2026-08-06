#!/bin/sh
# Repository-local verification for Sol Advisor's dashboard-configured role workflow.

set -eu

pass() { printf '%s\n' "PASS: $*"; }
fail() { printf '%s\n' "FAIL: $*" >&2; exit 1; }

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  PYTHON=python
fi

json_validate() {
  "$PYTHON" - "$@" <<'PY'
import json
import sys

for name in sys.argv[1:]:
    with open(name, encoding="utf-8") as handle:
        json.load(handle)
PY
}

json_field() {
  path=$1
  field=$2
  "$PYTHON" - "$path" "$field" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)
for key in sys.argv[2].split('.'):
    value = value[key]
print(value)
PY
}

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd) || exit 1
plugin_dir=$(CDPATH= cd "$script_dir/.." && pwd) || exit 1
repo_dir=$(CDPATH= cd "$plugin_dir/../.." && pwd) || exit 1
installer=$script_dir/install-agents.sh
runtime_inspector=$script_dir/inspect-agent-runtime.sh
role_dashboard=$script_dir/role-dashboard.py
templates=$plugin_dir/agents
role_map=$plugin_dir/config/role-map.json
models_json=$plugin_dir/config/models.json
manifest=$plugin_dir/.codex-plugin/plugin.json
skill=$plugin_dir/skills/orchestration/SKILL.md
contracts=$plugin_dir/skills/orchestration/references/role-contracts.md
luna_contract=$plugin_dir/skills/orchestration/references/luna-task-lane.md
model_roles=$plugin_dir/skills/orchestration/references/model-roles.md
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
prior_terra_sha256=4bf5f7e45836fa4eeb227e1362adac5feaa4732e93b412f3dc1e0be032cab601
prior_sol_sha256=ec4f70f04499417c5a58a2272a551f7f051e8192d01f743b71bc0d471c465fa8

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
      printf '%s  %s\n' "$(sha256_of "$path")" "$path"
    else
      printf 'O %s\n' "$(basename "$path")"
    fi
  done
}

sha256_of() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" 2>/dev/null | awk 'NF >= 1 && length($1) == 64 { print $1; exit }'
  else
    sha256sum "$1" 2>/dev/null | awk 'NF >= 1 && length($1) == 64 { print $1; exit }'
  fi
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
  [ "$(sha256_of "$target/$terra_file")" = "$legacy_terra_sha256" ] || fail "legacy Terra fixture digest drifted"
  [ "$(sha256_of "$target/$luna_file")" = "$legacy_luna_sha256" ] || fail "legacy Luna fixture digest drifted"
}

write_prior_roles() {
  target=$1
  mkdir -p "$target"
  # The pre-dashboard v0.5.0 body is the default role rendering without its two
  # dashboard ownership lines. Generate it independently of the current role map.
  python - "$role_dashboard" "$target" <<'PY'
from pathlib import Path
import importlib.util
import sys

dashboard_path = Path(sys.argv[1])
target = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("role_dashboard_prior", dashboard_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
terra = module.render_terra_template({"model": "combo/sol-advisor-terra", "effort": "high"})
sol = module.render_sol_template({"model": "combo/sol-advisor-sol", "effort": "high"})
(target / "sol-advisor-terra-implementer.toml").write_text("\n".join(terra.splitlines()[2:]) + "\n", encoding="utf-8", newline="\n")
(target / "sol-advisor-sol-reviewer.toml").write_text("\n".join(sol.splitlines()[2:]) + "\n", encoding="utf-8", newline="\n")
PY
  [ "$(sha256_of "$target/$terra_file")" = "$prior_terra_sha256" ] || fail "prior Terra fixture digest drifted"
  [ "$(sha256_of "$target/$sol_file")" = "$prior_sol_sha256" ] || fail "prior Sol fixture digest drifted"
}

write_dashboard_roles() {
  target=$1
  mkdir -p "$target"
  python - "$role_dashboard" "$target" <<'PY'
from pathlib import Path
import copy
import importlib.util
import sys

dashboard_path = Path(sys.argv[1])
target = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("role_dashboard_fixture", dashboard_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
config = copy.deepcopy(module.load_config())
config["roles"]["native_implementer"] = {"model": "fixture/implementer", "effort": "max"}
config["roles"]["native_reviewer"] = {"model": "fixture/reviewer", "effort": "low"}
for path, content in module.native_templates(config).items():
    (target / path.name).write_text(content, encoding="utf-8", newline="\n")
PY
}

for required in "$installer" "$runtime_inspector" "$role_dashboard" "$role_map" "$models_json" "$manifest" "$skill" "$contracts" "$luna_contract" "$model_roles" "$readme" "$ui"; do
  test -f "$required" || fail "required file missing: $required"
done

json_validate "$manifest"
[ "$(json_field "$manifest" version | sed 's/+.*//')" = 0.6.0 ] || fail "manifest base version is not 0.6.0"
grep -Fq 'explicit opt-in' "$manifest" || fail "manifest does not describe explicit Luna opt-in"
grep -Fq 'local, loopback-only model-role dashboard' "$manifest" || fail "manifest does not describe the local dashboard"
grep -Fq 'Codex app task tools' "$manifest" || fail "manifest does not describe app-task routing"
grep -Fq 'fresh native review' "$manifest" || fail "manifest does not preserve native fresh review"
pass "manifest JSON, version, local-dashboard, and both-mode UI language"

"$PYTHON" "$role_dashboard" check
native_model=$("$PYTHON" "$role_dashboard" get native_implementer --json | "$PYTHON" -c 'import json, sys; print(json.load(sys.stdin)["model"])')
native_effort=$("$PYTHON" "$role_dashboard" get native_implementer --json | "$PYTHON" -c 'import json, sys; print(json.load(sys.stdin)["effort"])')
"$PYTHON" - "$templates" "$role_map" "$role_dashboard" <<'PY'
from pathlib import Path
import importlib.util
import json
import sys
import tomllib

root = Path(sys.argv[1])
role_map_path = Path(sys.argv[2])
dashboard_path = Path(sys.argv[3])
config = json.loads(role_map_path.read_text(encoding="utf-8"))
expected_roles = {
    "primary_orchestrator",
    "native_implementer",
    "native_reviewer",
    "luna_task",
}
if config.get("schema_version") != 1 or set(config) != {"schema_version", "roles"}:
    raise SystemExit("role map schema is invalid")
if set(config["roles"]) != expected_roles:
    raise SystemExit(f"unexpected role map keys: {sorted(config['roles'])}")
for role_name, assignment in config["roles"].items():
    if set(assignment) != {"model", "effort"}:
        raise SystemExit(f"{role_name}: expected model and effort")
    if not isinstance(assignment["model"], str) or not assignment["model"]:
        raise SystemExit(f"{role_name}: invalid model")
    if assignment["effort"] not in {"minimal", "low", "medium", "high", "max"}:
        raise SystemExit(f"{role_name}: invalid effort")

expected = {
    "sol-advisor-terra-implementer.toml": {
        "name": "sol_advisor_terra_implementer",
        "model": config["roles"]["native_implementer"]["model"],
        "model_reasoning_effort": config["roles"]["native_implementer"]["effort"],
    },
    "sol-advisor-sol-reviewer.toml": {
        "name": "sol_advisor_sol_reviewer",
        "model": config["roles"]["native_reviewer"]["model"],
        "model_reasoning_effort": config["roles"]["native_reviewer"]["effort"],
        "sandbox_mode": "read-only",
    },
}
actual = {path.name for path in root.glob("*.toml")}
if actual != set(expected):
    raise SystemExit(f"expected exactly {sorted(expected)}, found {sorted(actual)}")
for filename, pins in expected.items():
    source = (root / filename).read_text(encoding="utf-8")
    if not source.replace("\r\n", "\n").startswith(
        "# Generated by Sol Advisor local role dashboard. Do not edit manually.\n"
    ):
        raise SystemExit(f"{filename}: is not dashboard-generated")
    data = tomllib.loads(source)
    for field in ("name", "description", "developer_instructions"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise SystemExit(f"{filename}: missing {field}")
    for field, value in pins.items():
        if data.get(field) != value:
            raise SystemExit(f"{filename}: {field}={data.get(field)!r}, expected {value!r}")

spec = importlib.util.spec_from_file_location("role_dashboard_verify", dashboard_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
if module.validate_config(config) != config:
    raise SystemExit("dashboard rejects its checked-in role map")
print("role map and generated native templates are valid")
PY
pass "dashboard role map and generated two-role TOML inventory"

json_validate "$models_json"
"$PYTHON" - "$role_dashboard" "$models_json" <<'PY'
from pathlib import Path
import importlib.util
import json
import sys

dashboard_path = Path(sys.argv[1])
models_path = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("role_dashboard_models", dashboard_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
raw = json.loads(models_path.read_text(encoding="utf-8"))
if set(raw) != {"schema_version", "models"} or raw.get("schema_version") != module.SCHEMA_VERSION:
    raise SystemExit("dashboard model list file has an invalid shape")
if module.load_models() != raw["models"]:
    raise SystemExit("dashboard model list does not round-trip")
if not raw["models"] or len(raw["models"]) != len(set(raw["models"])):
    raise SystemExit("dashboard model list is empty or contains duplicates")
for model in raw["models"]:
    if not module.MODEL_PATTERN.fullmatch(model):
        raise SystemExit(f"invalid dashboard model entry: {model}")
print("dashboard dropdown model list is valid")
PY
pass "dashboard dropdown model list"

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

prior_target=$tmp_dir/prior
write_prior_roles "$prior_target"
before=$(snapshot_files "$prior_target")
if sh "$installer" --target-dir "$prior_target"; then fail "normal installer replaced prior dashboard-predecessor templates"; fi
after=$(snapshot_files "$prior_target")
[ "$before" = "$after" ] || fail "normal installer partially mutated prior templates"
sh "$installer" --target-dir "$prior_target" --sync
cmp -s "$templates/$terra_file" "$prior_target/$terra_file" || fail "--sync did not update prior Terra template"
cmp -s "$templates/$sol_file" "$prior_target/$sol_file" || fail "--sync did not update prior Sol template"
sh "$installer" --target-dir "$prior_target" --check
pass "prior fixed templates require explicit sync and update safely"

dashboard_target=$tmp_dir/dashboard
write_dashboard_roles "$dashboard_target"
before=$(snapshot_files "$dashboard_target")
if sh "$installer" --target-dir "$dashboard_target"; then fail "normal installer replaced dashboard-generated templates"; fi
after=$(snapshot_files "$dashboard_target")
[ "$before" = "$after" ] || fail "normal installer partially mutated dashboard-generated templates"
sh "$installer" --target-dir "$dashboard_target" --sync
cmp -s "$templates/$terra_file" "$dashboard_target/$terra_file" || fail "--sync did not update dashboard Terra template"
cmp -s "$templates/$sol_file" "$dashboard_target/$sol_file" || fail "--sync did not update dashboard Sol template"
sh "$installer" --target-dir "$dashboard_target" --check
pass "dashboard-generated templates require explicit sync and update safely"

modified_dashboard=$tmp_dir/modified-dashboard
write_dashboard_roles "$modified_dashboard"
printf '%s\n' modified >> "$modified_dashboard/$terra_file"
before=$(snapshot_files "$modified_dashboard")
if sh "$installer" --target-dir "$modified_dashboard" --sync; then fail "--sync accepted modified dashboard Terra"; fi
after=$(snapshot_files "$modified_dashboard")
[ "$before" = "$after" ] || fail "modified dashboard refusal partially mutated target"
pass "modified dashboard refusal with zero partial mutation"

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
ln -s "$templates/$terra_file" "$unsafe/$terra_file" 2>/dev/null || true
if [ ! -L "$unsafe/$terra_file" ]; then
  # Git Bash on some Windows hosts emulates `ln -s` as a regular copied file when
  # symlink creation is unavailable. Use a directory to retain a portable unsafe
  # destination test rather than mistaking that regular copy for a real link.
  rm -f "$unsafe/$terra_file"
  mkdir "$unsafe/$terra_file"
fi
before=$(snapshot_files "$unsafe")
if sh "$installer" --target-dir "$unsafe"; then fail "installer accepted unsafe Terra destination"; fi
after=$(snapshot_files "$unsafe")
[ "$before" = "$after" ] || fail "unsafe destination refusal partially mutated target"
test ! -e "$unsafe/$sol_file" || fail "unsafe destination refusal partially installed Sol"
pass "unsafe destination refusal with zero partial mutation"

runtime_sessions=$tmp_dir/runtime-sessions
runtime_day=$runtime_sessions/2026/08/02
mkdir -p "$runtime_day"
runtime_id=11111111-1111-7111-8111-111111111111
runtime_rollout=$runtime_day/rollout-2026-08-02T00-00-00-$runtime_id.jsonl
printf '%s\n' \
  '{"type":"response_item","payload":{"prompt":"DO_NOT_LEAK_PROMPT"}}' \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$runtime_id\",\"parent_thread_id\":\"00000000-0000-7000-8000-000000000000\",\"agent_role\":\"sol_advisor_terra_implementer\",\"agent_path\":\"/root/fixture\",\"model_provider\":\"openai\",\"cwd\":\"/fixture\"}}" \
  "{\"type\":\"turn_context\",\"payload\":{\"model\":\"$native_model\",\"effort\":\"$native_effort\",\"sandbox_policy\":{\"type\":\"danger-full-access\"},\"permission_profile\":{\"type\":\"disabled\"},\"cwd\":\"/fixture\"}}" \
  > "$runtime_rollout"
runtime_output=$(sh "$runtime_inspector" --sessions-dir "$runtime_sessions" "$runtime_id")
printf '%s\n' "$runtime_output" | "$PYTHON" -c '
import json
import sys

payload = json.load(sys.stdin)
expected = sys.argv[1:]
if not (
    payload.get("thread_id") == expected[0]
    and payload.get("agent_role") == "sol_advisor_terra_implementer"
    and payload.get("model") == expected[1]
    and payload.get("effort") == expected[2]
    and payload.get("sandbox_policy_type") == "danger-full-access"
    and payload.get("permission_profile_type") == "disabled"
):
    raise SystemExit(1)
' "$runtime_id" "$native_model" "$native_effort" >/dev/null || fail "runtime inspector returned wrong configured-implementer evidence"
if printf '%s\n' "$runtime_output" | grep -Fq DO_NOT_LEAK; then fail "runtime inspector leaked payload"; fi
if sh "$runtime_inspector" --sessions-dir "$runtime_sessions" invalid >/dev/null 2>&1; then fail "runtime inspector accepted invalid id"; fi
zero_id=22222222-2222-7222-8222-222222222222
if sh "$runtime_inspector" --sessions-dir "$runtime_sessions" "$zero_id" >/dev/null 2>&1; then fail "runtime inspector accepted zero matches"; fi
pass "runtime inspector configured-implementer routing and safe refusal"

for document in "$skill" "$contracts"; do
  grep -Fq 'agent_type: sol_advisor_terra_implementer' "$document" || fail "missing Terra spawn in $document"
  grep -Fq 'agent_type: sol_advisor_sol_reviewer' "$document" || fail "missing Sol spawn in $document"
  grep -Fq 'fork_turns: none' "$document" || fail "missing fresh context in $document"
  if grep -Eq 'agent_type:.*(luna|terra_max)' "$document"; then fail "retired implementation spawn remains in $document"; fi
  if grep -Eq '^[[:space:]]*(model|reasoning_effort):' "$document"; then fail "per-spawn override remains in $document"; fi
done
grep -Fq '../../scripts/install-agents.sh' "$skill" || fail "skill does not resolve installer relatively"
grep -Fq '../../scripts/inspect-agent-runtime.sh' "$skill" || fail "skill does not resolve inspector relatively"
grep -Fq '../../scripts/role-dashboard.py' "$skill" || fail "skill does not resolve the role dashboard relatively"
grep -qi 'public native spawn/details metadata first' "$skill" || fail "skill lacks public-details-first evidence rule"
grep -qi 'parent captures and verifies exact before-and-after' "$contracts" || fail "contracts lack behavioral read-only state check"
grep -Fq 'luna-task-lane.md' "$skill" || fail "skill does not link the Luna task contract"
grep -Fq 'luna-task-lane.md' "$contracts" || fail "role contracts do not link the Luna task contract"
grep -Fq 'model-roles.md' "$skill" || fail "skill does not link the model-role reference"
grep -Fq 'model-roles.md' "$contracts" || fail "role contracts do not link the model-role reference"
grep -Fq '127.0.0.1' "$model_roles" || fail "model-role reference does not document loopback-only dashboard scope"

for tool in list_projects list_threads create_thread wait_threads read_thread send_message_to_thread; do
  for document in "$skill" "$contracts" "$luna_contract" "$readme"; do
    grep -Fq "$tool" "$document" || fail "$document omits Luna app tool: $tool"
  done
done
grep -Fq 'luna_task' "$skill" || fail "skill omits configured Luna role"
grep -Fq '`model` and `thinking` to its configured values' "$skill" || fail "skill does not route Luna through the configured model and effort"
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

grep -Fq 'Luna task (explicit opt-in)' "$readme" || fail "README omits the Luna task mode"
grep -Fq 'Use the Luna task lane' "$readme" || fail "README omits explicit Luna authorization"
grep -Fq 'native lane remains' "$readme" || fail "README does not preserve the native lane"
grep -Fq 'does not use a Luna' "$readme" || fail "README permits a Luna companion TOML"
grep -Fq 'user-visible Luna tasks' "$manifest" || fail "manifest UI omits user-visible Luna tasks"
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
grep -Fq 'local dashboard' "$readme" || fail "README does not document the local dashboard"
grep -Fq 'install-agents.sh --sync' "$readme" || fail "README does not document explicit native sync"

for document in "$readme" "$manifest" "$skill" "$contracts" "$ui"; do
  if grep -Eqi 'Terra / High is the sole implementation producer|one role-pinned .*handles all implementation|route all implementation through.*Terra|delegate all implementation to (the )?(native )?Terra' "$document"; then
    fail "stale single-mode implementation claim remains in $document"
  fi
done
forbidden_terra='sol_advisor_terra_'"max"
forbidden_file='sol-advisor-terra-'"max"
if command -v rg >/dev/null 2>&1; then
  if rg -n "$forbidden_terra|$forbidden_file" "$readme" "$plugin_dir"; then
    fail "forbidden second Terra role remains"
  fi
elif grep -R -n -E "$forbidden_terra|$forbidden_file" "$readme" "$plugin_dir"; then
  fail "forbidden second Terra role remains"
fi
pass "native and Luna contracts, opt-in guards, and stale-claim checks"

sh -n "$installer"
sh -n "$runtime_inspector"
sh -n "$script_dir/verify.sh"
"$PYTHON" -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$role_dashboard"
pass "shell and dashboard syntax"

printf '%s\n' "VERIFY PASSED: Sol Advisor dashboard-configured role checks completed in $tmp_dir"
