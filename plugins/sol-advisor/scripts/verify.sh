#!/bin/sh
# Repository-local, disposable verification for Sol Advisor v0.6.0.
set -eu
PATH=/opt/homebrew/bin:$PATH
export PATH

fail() { printf '%s\n' "FAIL: $*" >&2; exit 1; }
pass() { printf '%s\n' "PASS: $*"; }
script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
plugin_dir=$(CDPATH= cd "$script_dir/.." && pwd)
repo_dir=$(CDPATH= cd "$plugin_dir/../.." && pwd)
tmp_dir=$(mktemp -d /tmp/sol-advisor-verify.XXXXXX) || fail "could not create disposable workspace"
cleanup() { case "$tmp_dir" in /tmp/sol-advisor-verify.*) rm -rf "$tmp_dir" ;; *) fail "unsafe cleanup path" ;; esac; }
trap cleanup 0 HUP INT TERM

manifest=$plugin_dir/.codex-plugin/plugin.json
installer=$script_dir/install-agents.sh
templates=$plugin_dir/agents
skill=$plugin_dir/skills/orchestration/SKILL.md
routing_skill=$plugin_dir/skills/routing/SKILL.md
contracts=$plugin_dir/skills/orchestration/references/role-contracts.md
readme=$repo_dir/README.md
terra_file=sol-advisor-terra-implementer.toml
sol_file=sol-advisor-sol-reviewer.toml
luna_file=sol-advisor-luna-implementer.toml
legacy_terra_sha256=4425a8c1f21ce8c6af93f96adc253bbc33ea301f1389b3fa8ce350be08584eca
legacy_luna_sha256=fba1b42849d93737e83b094a2ab0b1611f87ac37db7438c8bbdf581f0813f8eb
snapshot_files() { test -d "$1" || { printf '%s\n' MISSING; return; }; find "$1" -mindepth 1 -maxdepth 1 -print | LC_ALL=C sort | while IFS= read -r path; do if test -L "$path"; then printf 'L %s\n' "$(basename "$path")"; elif test -f "$path"; then shasum -a 256 "$path"; else printf 'O %s\n' "$(basename "$path")"; fi; done; }
write_legacy_roles() { target=$1; mkdir -p "$target"; cat > "$target/$terra_file" <<'EOF'
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
EOF
cat > "$target/$luna_file" <<'EOF'
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
EOF
cp "$templates/$sol_file" "$target/$sol_file"; test "$(shasum -a 256 "$target/$terra_file" | awk '{print $1}')" = "$legacy_terra_sha256" || fail "legacy Terra fixture digest drifted"; test "$(shasum -a 256 "$target/$luna_file" | awk '{print $1}')" = "$legacy_luna_sha256" || fail "legacy Luna fixture digest drifted"; }
test "$(jq -r .version "$manifest")" = "0.6.0" || fail "manifest version is not 0.6.0"
test "$(jq -r .version "$plugin_dir/plugin.json")" = "0.6.0" || fail "canonical manifest version is not 0.6.0"
test "$(node -p "require('$repo_dir/package.json').version")" = "0.6.0" || fail "package version is not 0.6.0"
test -f "$plugin_dir/skills/routing/SKILL.md" || fail "routing skill is missing"
grep -Fq 'resolve_route' "$plugin_dir/skills/routing/SKILL.md" || fail "routing skill omits resolver"
grep -Fq 'sol_advisor_terra_implementer' "$plugin_dir/agents/sol-advisor-terra-implementer.toml" || fail "Terra compatibility alias is missing"
grep -Fq 'sol_advisor_sol_reviewer' "$plugin_dir/agents/sol-advisor-sol-reviewer.toml" || fail "Sol compatibility alias is missing"
pass "v0.6 manifests, routing entrypoint, and compatibility aliases"

python3 - "$templates" <<'PY'
from pathlib import Path
import sys, tomllib
root=Path(sys.argv[1]); expected={"sol-advisor-terra-implementer.toml":("sol_advisor_terra_implementer","gpt-5.6-terra","high",None),"sol-advisor-sol-reviewer.toml":("sol_advisor_sol_reviewer","gpt-5.6-sol","high","read-only")}
if {p.name for p in root.glob("*.toml")} != set(expected): raise SystemExit("static role inventory drifted")
for name,(role,model,effort,sandbox) in expected.items():
 d=tomllib.loads((root/name).read_text()); assert d["name"]==role and d["model"]==model and d["model_reasoning_effort"]==effort and isinstance(d.get("developer_instructions"),str)
 if sandbox is not None: assert d.get("sandbox_mode")==sandbox
print("static Terra/Sol aliases valid")
PY
grep -Fq "legacy_terra_sha256=$legacy_terra_sha256" "$installer" || fail "installer legacy Terra digest mismatch"
grep -Fq "legacy_luna_sha256=$legacy_luna_sha256" "$installer" || fail "installer legacy Luna digest mismatch"
pass "static Terra/Sol alias inventory and immutable v0.2 fingerprints"

target=$tmp_dir/agents
sh "$installer" --target-dir "$target"
cmp -s "$templates/$terra_file" "$target/$terra_file" || fail "clean Terra install mismatch"
cmp -s "$templates/$sol_file" "$target/$sol_file" || fail "clean Sol install mismatch"
sh "$installer" --target-dir "$target" --check
before=$(snapshot_files "$target"); sh "$installer" --target-dir "$target"; after=$(snapshot_files "$target"); test "$before" = "$after" || fail "idempotent install changed roles"
test ! -e "$target/sol-advisor-luna-implementer.toml" || fail "retired legacy Luna profile was created"
missing=$tmp_dir/missing; if sh "$installer" --target-dir "$missing" --check; then fail "check accepted missing target"; fi; test ! -e "$missing" || fail "missing-target check mutated target"
codex_home=$tmp_dir/codex-home; CODEX_HOME="$codex_home" sh "$installer"; cmp -s "$templates/$terra_file" "$codex_home/agents/$terra_file" || fail "CODEX_HOME install mismatch"
relative=$tmp_dir/relative; mkdir "$relative"; (cd "$relative" && sh "$installer" --target-dir agents); cmp -s "$templates/$sol_file" "$relative/agents/$sol_file" || fail "relative target mismatch"
migration=$tmp_dir/migration; write_legacy_roles "$migration"; sh "$installer" --target-dir "$migration"; test ! -e "$migration/$luna_file" || fail "legacy Luna not retired"
modified=$tmp_dir/modified; write_legacy_roles "$modified"; printf '%s\n' modified >> "$modified/$luna_file"; before=$(snapshot_files "$modified"); if sh "$installer" --target-dir "$modified"; then fail "modified Luna removed"; fi; test "$before" = "$(snapshot_files "$modified")" || fail "modified Luna refusal was partial"
modified_terra=$tmp_dir/modified-terra; write_legacy_roles "$modified_terra"; printf '%s\n' modified >> "$modified_terra/$terra_file"; before=$(snapshot_files "$modified_terra"); if sh "$installer" --target-dir "$modified_terra"; then fail "modified Terra replaced"; fi; test "$before" = "$(snapshot_files "$modified_terra")" || fail "modified Terra refusal was partial"
stale=$tmp_dir/stale; sh "$installer" --target-dir "$stale"; cp "$templates/$terra_file" "$stale/$luna_file"; before=$(snapshot_files "$stale"); if sh "$installer" --target-dir "$stale" --check; then fail "stale Luna accepted"; fi; test "$before" = "$(snapshot_files "$stale")" || fail "stale Luna check mutated target"
unsafe=$tmp_dir/unsafe; mkdir "$unsafe"; ln -s "$templates/$terra_file" "$unsafe/$terra_file"; before=$(snapshot_files "$unsafe"); if sh "$installer" --target-dir "$unsafe"; then fail "symlink destination accepted"; fi; test "$before" = "$(snapshot_files "$unsafe")" || fail "symlink refusal was partial"
pass "clean/idempotent install, migration, modified/stale/symlink refusals, CODEX_HOME, and relative targets"

runtime_home=$tmp_dir/runtime-home
runtime_id=11111111-1111-7111-8111-111111111111
runtime_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$runtime_id.jsonl
mkdir -p "$(dirname "$runtime_file")"
printf '%s\n' \
  '{"type":"response_item","payload":{"prompt":"DO_NOT_LEAK_PROMPT"}}' \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$runtime_id\"}}" \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$runtime_id\"}}" \
  '{"type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  '{"type":"event_msg","payload":{"type":"thread_settings_applied","thread_settings":{"service_tier":"priority"}}}' \
  '{"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"total_tokens":123},"last_token_usage":{"input_tokens":20}}}}' \
  '{"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"total_tokens":456},"last_token_usage":{"input_tokens":40}}}}' \
  '{"type":"response_item","payload":{"type":"custom_tool_call"}}' \
  '{"type":"event_msg","payload":{"type":"context_compacted"}}' \
  > "$runtime_file"
runtime_output=$(CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" "$runtime_id")
printf '%s\n' "$runtime_output" | jq -e --arg id "$runtime_id" '.thread_id==$id and .evidence_source=="codex-rollout-inspector" and .execution_context=="parent" and .agent_identifier==null and .observed_runtime_tier=="priority" and .raw_tokens==456 and .model_rounds==2 and .median_input_tokens_per_round==30 and .median_input_tokens_first_20==null and .tool_calls==1 and .compactions==1' >/dev/null || fail "runtime inspector parent evidence is incorrect"
agent_id=22222222-2222-7222-8222-222222222222
agent_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$agent_id.jsonl
printf '%s\n' \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$agent_id\",\"parent_thread_id\":\"$runtime_id\",\"agent_role\":\"sol_advisor_routine\"}}" \
  '{"type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  > "$agent_file"
agent_output=$(CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" "$agent_id")
printf '%s\n' "$agent_output" | jq -e --arg id "$agent_id" '.thread_id==$id and .evidence_source=="codex-rollout-inspector" and .execution_context=="agent" and .agent_identifier=="sol_advisor_routine"' >/dev/null || fail "runtime inspector agent evidence is incorrect"
mixed_parent_id=33333333-3333-7333-8333-333333333333
mixed_parent_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$mixed_parent_id.jsonl
printf '%s\n' \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$mixed_parent_id\"}}" \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$mixed_parent_id\",\"parent_thread_id\":\"$runtime_id\",\"agent_role\":\"sol_advisor_routine\"}}" \
  '{"type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  > "$mixed_parent_file"
if CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" "$mixed_parent_id" >/dev/null 2>&1; then fail "runtime inspector accepted mixed parent-thread provenance"; fi
mixed_role_id=44444444-4444-7444-8444-444444444444
mixed_role_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$mixed_role_id.jsonl
printf '%s\n' \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$mixed_role_id\",\"parent_thread_id\":\"$runtime_id\",\"agent_role\":\"sol_advisor_routine\"}}" \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$mixed_role_id\",\"parent_thread_id\":\"$runtime_id\"}}" \
  '{"type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  > "$mixed_role_file"
if CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" "$mixed_role_id" >/dev/null 2>&1; then fail "runtime inspector accepted mixed agent-role provenance"; fi
parent_role_id=55555555-5555-7555-8555-555555555555
parent_role_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$parent_role_id.jsonl
printf '%s\n' \
  "{\"type\":\"session_meta\",\"payload\":{\"id\":\"$parent_role_id\",\"agent_role\":\"sol_advisor_routine\"}}" \
  '{"type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  > "$parent_role_file"
if CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" "$parent_role_id" >/dev/null 2>&1; then fail "runtime inspector accepted parent metadata with an agent role"; fi
if printf '%s\n' "$runtime_output" | grep -Fq DO_NOT_LEAK; then fail "runtime inspector leaked prompt canary"; fi
if CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" --sessions-dir "$runtime_home" "$runtime_id" >/dev/null 2>&1; then fail "runtime inspector accepted an arbitrary path"; fi
pass "pathless aggregate runtime inspection, provenance rejection, and prompt-canary privacy"

grep -Fq 'currentRuntimeEvidence' "$routing_skill" || fail "routing skill omits current evidence"
grep -Fq 'targetRuntimeEvidence' "$routing_skill" || fail "routing skill omits target evidence"
grep -Fq 'fresh_agent' "$routing_skill" || fail "routing skill omits fresh-agent semantics"
readme_text=$(tr '\n' ' ' < "$readme")
grep -Fq 'sol-advisor-hard' "$readme" || fail "README omits hard role"
grep -Fq 'Its nine tools are:' "$readme" || fail "README tool count is stale"
grep -Fq -- '- `resolve_route`' "$readme" || fail "README tool list omits route resolver"
grep -Fq 'routine to `routine`; medium to the `high` compatibility storage role; hard' "$readme" || fail "README class mapping is stale"
grep -Fq 'and planning or review to `advisor`.' "$readme" || fail "README advisor class mapping is stale"
printf '%s\n' "$readme_text" | grep -Fq 'Any route change requires a fresh exact agent.' || fail "README fresh-route rule is stale"
grep -Fq 'Reviews are always fresh and read-only' "$readme" || fail "README review rule is stale"
if grep -Eq 'all eight tools|these eight enabled tools' "$readme"; then fail "README stale eight-tool wording remains"; fi
grep -Fq 'four generated files' "$readme" || fail "README generated-file count is stale"
pass "four-role MCP/runtime fixture and documentation contracts"

sh -n "$script_dir/install-agents.sh"
sh -n "$script_dir/inspect-agent-runtime.sh"
sh -n "$script_dir/verify.sh"
PATH=/opt/homebrew/bin:$PATH bun test "$plugin_dir/mcp/server.test.ts"
pass "shell syntax and MCP lifecycle/route tests"
printf '%s\n' "VERIFY PASSED: Sol Advisor v0.6.0 disposable checks completed"
