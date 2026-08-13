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
agent_config=$plugin_dir/skills/orchestration/agents/openai.yaml
luna_contract=$plugin_dir/skills/orchestration/references/luna-task-lane.md
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
if ! jq -e '
  (.interface.defaultPrompt | type == "array") and
  all(.interface.defaultPrompt[]; type == "string" and length <= 128) and
  any(.interface.defaultPrompt[]; . == "Use challenge-first resolve_route; use its exact generated role and fresh exact generated advisor review.") and
  any(.interface.defaultPrompt[]; . == "Use the Luna task lane only if I explicitly authorize it; create visible GPT-5.6 Luna / Max tasks via Codex app tools.") and
  all(.interface.defaultPrompt[]; contains("fresh Sol review") | not)
' "$manifest" >/dev/null; then
  fail ".codex-plugin default prompts must be guarded schema-v2/generated-advisor and explicit-Luna text"
fi
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
runtime_challenge=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
runtime_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$runtime_id.jsonl
mkdir -p "$(dirname "$runtime_file")"
printf '%s\n' \
  '{"timestamp":"2026-08-13T00:00:00Z","type":"response_item","payload":{"prompt":"DO_NOT_LEAK_PROMPT"}}' \
  "{\"timestamp\":\"2026-08-13T00:00:00Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"$runtime_id\"}}" \
  "{\"timestamp\":\"2026-08-13T00:00:01Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"$runtime_id\"}}" \
  '{"timestamp":"2026-08-13T00:00:02Z","type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  '{"timestamp":"2026-08-13T00:00:03Z","type":"event_msg","payload":{"type":"thread_settings_applied","thread_settings":{"service_tier":"priority"}}}' \
  '{"timestamp":"2026-08-13T00:00:04Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"total_tokens":123},"last_token_usage":{"input_tokens":20}}}}' \
  '{"timestamp":"2026-08-13T00:00:05Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"total_tokens":456},"last_token_usage":{"input_tokens":40}}}}' \
  '{"timestamp":"2026-08-13T00:00:06Z","type":"response_item","payload":{"type":"custom_tool_call"}}' \
  '{"timestamp":"2026-08-13T00:00:07Z","type":"event_msg","payload":{"type":"context_compacted"}}' \
  > "$runtime_file"
runtime_output=$(CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" --challenge "$runtime_challenge" "$runtime_id")
printf '%s\n' "$runtime_output" | jq -e --arg id "$runtime_id" --arg challenge "$runtime_challenge" '.challenge==$challenge and .threadId==$id and .parentThreadId==null and .latestEventAt=="2026-08-13T00:00:02Z" and .evidenceSource=="codex-rollout-inspector" and .executionContext=="parent" and .agentIdentifier==null and .observedRuntimeTier=="priority" and .rawTokens==456 and .modelRounds==2 and .medianInputTokensPerRound==30 and .medianInputTokensFirst20==null and .toolCalls==1 and .compactions==1' >/dev/null || fail "runtime inspector parent evidence is incorrect"
agent_id=22222222-2222-7222-8222-222222222222
agent_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$agent_id.jsonl
printf '%s\n' \
  "{\"timestamp\":\"2026-08-13T00:00:08Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"$agent_id\",\"parent_thread_id\":\"$runtime_id\",\"agent_role\":\"sol_advisor_routine\"}}" \
  '{"timestamp":"2026-08-13T00:00:09Z","type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  > "$agent_file"
agent_output=$(CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" --challenge "$runtime_challenge" "$agent_id")
printf '%s\n' "$agent_output" | jq -e --arg id "$agent_id" --arg parent "$runtime_id" '.threadId==$id and .parentThreadId==$parent and .executionContext=="agent" and .agentIdentifier=="sol_advisor_routine"' >/dev/null || fail "runtime inspector agent evidence is incorrect"
mixed_parent_id=33333333-3333-7333-8333-333333333333
mixed_parent_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$mixed_parent_id.jsonl
printf '%s\n' \
  "{\"timestamp\":\"2026-08-13T00:00:10Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"$mixed_parent_id\"}}" \
  "{\"timestamp\":\"2026-08-13T00:00:11Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"$mixed_parent_id\",\"parent_thread_id\":\"$runtime_id\",\"agent_role\":\"sol_advisor_routine\"}}" \
  '{"timestamp":"2026-08-13T00:00:12Z","type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  > "$mixed_parent_file"
if CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" --challenge "$runtime_challenge" "$mixed_parent_id" >/dev/null 2>&1; then fail "runtime inspector accepted mixed parent-thread provenance"; fi
mixed_role_id=44444444-4444-7444-8444-444444444444
mixed_role_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$mixed_role_id.jsonl
printf '%s\n' \
  "{\"timestamp\":\"2026-08-13T00:00:13Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"$mixed_role_id\",\"parent_thread_id\":\"$runtime_id\",\"agent_role\":\"sol_advisor_routine\"}}" \
  "{\"timestamp\":\"2026-08-13T00:00:14Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"$mixed_role_id\",\"parent_thread_id\":\"$runtime_id\"}}" \
  '{"timestamp":"2026-08-13T00:00:15Z","type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  > "$mixed_role_file"
if CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" --challenge "$runtime_challenge" "$mixed_role_id" >/dev/null 2>&1; then fail "runtime inspector accepted mixed agent-role provenance"; fi
parent_role_id=55555555-5555-7555-8555-555555555555
parent_role_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$parent_role_id.jsonl
printf '%s\n' \
  "{\"timestamp\":\"2026-08-13T00:00:16Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"$parent_role_id\",\"agent_role\":\"sol_advisor_routine\"}}" \
  '{"timestamp":"2026-08-13T00:00:17Z","type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  > "$parent_role_file"
if CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" --challenge "$runtime_challenge" "$parent_role_id" >/dev/null 2>&1; then fail "runtime inspector accepted parent metadata with an agent role"; fi
incomplete_turn_id=66666666-6666-7666-8666-666666666666
incomplete_turn_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$incomplete_turn_id.jsonl
printf '%s\n' \
  "{\"timestamp\":\"2026-08-13T00:00:18Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"$incomplete_turn_id\"}}" \
  '{"timestamp":"2026-08-13T00:00:19Z","type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  '{"timestamp":"2026-08-13T00:00:20Z","type":"turn_context","payload":{"model":"gpt-5.6-luna","sandbox_policy":{"type":"danger-full-access"}}}' \
  > "$incomplete_turn_file"
if CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" --challenge "$runtime_challenge" "$incomplete_turn_id" >/dev/null 2>&1; then fail "runtime inspector accepted incomplete authoritative turn context"; fi
mixed_turn_id=77777777-7777-7777-8777-777777777777
mixed_turn_file=$runtime_home/sessions/2026/08/13/rollout-2026-08-13T00-00-00-$mixed_turn_id.jsonl
printf '%s\n' \
  "{\"timestamp\":\"2026-08-13T00:00:21Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"$mixed_turn_id\"}}" \
  '{"timestamp":"2026-08-13T00:00:22Z","type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  '{"timestamp":"2026-08-13T00:00:23Z","type":"turn_context","payload":{"model":"gpt-5.6-sol","effort":"max","sandbox_policy":{"type":"danger-full-access"}}}' \
  > "$mixed_turn_file"
if CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" --challenge "$runtime_challenge" "$mixed_turn_id" >/dev/null 2>&1; then fail "runtime inspector accepted mixed authoritative turn contexts"; fi
if printf '%s\n' "$runtime_output" | grep -Fq DO_NOT_LEAK; then fail "runtime inspector leaked prompt canary"; fi
if CODEX_HOME="$runtime_home" sh "$script_dir/inspect-agent-runtime.sh" --sessions-dir "$runtime_home" "$runtime_id" >/dev/null 2>&1; then fail "runtime inspector accepted an arbitrary path"; fi
pass "pathless aggregate runtime inspection, provenance rejection, and prompt-canary privacy"

grep -Fq 'currentRuntimeEvidence' "$routing_skill" || fail "routing skill omits current evidence"
grep -Fq 'targetRuntimeEvidence' "$routing_skill" || fail "routing skill omits target evidence"
grep -Fq 'fresh_agent' "$routing_skill" || fail "routing skill omits fresh-agent semantics"
grep -Fq 'Luna / Max / Standard' "$routing_skill" || fail "routing skill omits parent recommendation"
grep -Fq 'Luna / Max / Standard' "$skill" || fail "orchestration skill omits parent recommendation"
grep -Fq 'Luna / Max / Standard' "$contracts" || fail "role contracts omit parent recommendation"
grep -Fq 'Luna / Max / Standard' "$plugin_dir/skills/setup/SKILL.md" || fail "setup skill omits parent recommendation"
grep -Fq 'The default native' "$skill" || fail "orchestration skill omits the schema-v2 native default"
grep -Fq 'challenge-first `resolve_route`' "$skill" || fail "orchestration skill omits challenge-first default routing"
grep -Fq 'only when the user' "$skill" || fail "orchestration skill omits explicit compatibility opt-in"
grep -Fq 'Every schema-v2 generated-role prompt' "$contracts" || fail "role contracts omit generated-role default prompt contract"
grep -Fq 'Only after explicit current-request compatibility opt-in' "$contracts" || fail "role contracts omit static compatibility gate"
grep -Fq 'exact schema-v2 role' "$agent_config" || fail "orchestration agent prompt omits schema-v2 routing"
grep -Fq 'inherits the user' "$luna_contract" || fail "Luna contract omits inherited parent setting"
grep -Fq "available only when the user's current" "$plugin_dir/skills/orchestration/references/portable-entry.md" || fail "portable entry omits explicit compatibility opt-in"
grep -Fq 'routing preflight' "$plugin_dir/skills/orchestration/references/portable-entry.md" || fail "portable entry omits compatibility preflight"
orchestration_text=$(tr '\n' ' ' < "$skill")
contracts_text=$(tr '\n' ' ' < "$contracts")
if printf '%s\n' "$orchestration_text" | grep -Fq 'The default native lane delegates implementation to Terra / High'; then fail "orchestration default still routes through static Terra"; fi
if printf '%s\n' "$orchestration_text" | grep -Fq 'For the native lane, delegate corrections through Terra'; then fail "orchestration corrections still route through static Terra"; fi
if printf '%s\n' "$orchestration_text" | grep -Fq 'After native implementation and parent verification, always spawn a new, fresh reviewer'; then fail "orchestration final review still requires static Sol"; fi
if printf '%s\n' "$contracts_text" | grep -Fq 'Terra / High - sole native implementation lane'; then fail "role contracts still describe Terra as the sole native lane"; fi
if printf '%s\n' "$contracts_text" | grep -Fq 'Use this lane for every delegated native implementation'; then fail "role contracts still make static Terra the general default"; fi
portable_text=$(tr '\n' ' ' < "$plugin_dir/skills/orchestration/references/portable-entry.md")
if printf '%s\n' "$portable_text" | grep -Fq 'compatibility lane remains available when its separately installed roles'; then fail "portable entry still exposes ungated compatibility"; fi
readme_text=$(tr '\n' ' ' < "$readme")
grep -Fq 'sol-advisor-hard' "$readme" || fail "README omits hard role"
grep -Fq 'Its nine tools are:' "$readme" || fail "README tool count is stale"
grep -Fq -- '- `resolve_route`' "$readme" || fail "README tool list omits route resolver"
grep -Fq 'routine to `routine`; medium to the `high` compatibility storage role; hard' "$readme" || fail "README class mapping is stale"
grep -Fq 'and planning or review to `advisor`.' "$readme" || fail "README advisor class mapping is stale"
printf '%s\n' "$readme_text" | grep -Fq '`spawn-required` preserves the active challenge. Accepted parent or target proof consumes it. Blocked provenance, same-thread evidence, or a target mismatch invalidates it and requires a new route challenge.' || fail "README challenge lifecycle rule is stale"
grep -Fq 'Reviews are always fresh and read-only' "$readme" || fail "README review rule is stale"
if grep -Eq 'all eight tools|these eight enabled tools' "$readme"; then fail "README stale eight-tool wording remains"; fi
grep -Fq 'four generated files' "$readme" || fail "README generated-file count is stale"
grep -Fq 'Luna / Max / Standard recommended' "$readme" || fail "README parent recommendation is stale"
grep -Fq 'Schema-v2 native default' "$readme" || fail "README omits schema-v2 native default"
grep -Fq 'Codex compatibility (explicit opt-in)' "$readme" || fail "README omits explicit compatibility lane"
if printf '%s\n' "$readme_text" | grep -Fq 'The native lane remains the default for the exact retained Codex compatibility workflow'; then fail "README still makes compatibility the native default"; fi
pass "four-role MCP/runtime fixture and documentation contracts"

sh -n "$script_dir/install-agents.sh"
sh -n "$script_dir/inspect-agent-runtime.sh"
sh -n "$script_dir/verify.sh"
PATH=/opt/homebrew/bin:$PATH bun test "$plugin_dir/mcp/server.test.ts"
pass "shell syntax and MCP lifecycle/route tests"
printf '%s\n' "VERIFY PASSED: Sol Advisor v0.6.0 disposable checks completed"
