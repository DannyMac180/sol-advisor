# Sol Advisor

**Sol runs the show. Terra / High handles implementation, and a fresh Sol review
with a requested read-only profile stands between the diff and done.**

Sol Advisor is a Codex-native architect workflow for capability-routed software
delivery. The primary session stays focused on requirements, architecture, specs, and
verification while native Codex custom-agent threads handle implementation and review.

## Go deeper

I write [**Attention Heads**](https://attentionheads.substack.com/?utm_source=github&utm_medium=readme&utm_campaign=sol-advisor) — deep, evidence-backed writing on AI, cognition, and agentic engineering. The **Agentic Engineering Field Notes** series is where I publish practical advice on the craft of using AI. [Subscribe](https://attentionheads.substack.com/subscribe?utm_source=github&utm_medium=readme&utm_campaign=sol-advisor) to get new posts to your inbox.

| Lane | Native agent type | Pinned profile | Use it for |
|---|---|---|---|
| Orchestrator | Primary session | GPT-5.6 Sol / High | Requirements, architecture, decomposition, routing, and acceptance |
| Implementation | sol_advisor_terra_implementer | GPT-5.6 Terra / High | Bounded work specified by the Sol orchestrator |
| Final review | sol_advisor_sol_reviewer | GPT-5.6 Sol / High / requests read-only | Fresh review of the actual diff and verification evidence |

The final review is context-independent, not model-family-independent: Sol reviews
Sol's orchestration with a fresh context. That catches conversational assumptions, but
it is not cross-vendor review.

## Install from GitHub

Requirements:

- A current Codex CLI or ChatGPT desktop app with plugins, native subagents, and
  custom agents enabled.
- Access to GPT-5.6 Sol / High and GPT-5.6 Terra / High.
- jq, which the companion-install lookup uses to locate the installed plugin package.

Add the GitHub repository as a Codex marketplace, then install the plugin:

~~~sh
codex plugin marketplace add DannyMac180/sol-advisor --ref main
codex plugin add sol-advisor@sol-advisor
~~~

### Install the companion custom agents

Plugin installation does **not** automatically install custom-agent files. That is
intentional: the files are user-owned role pins, and the installer must never overwrite
a different local role silently. Install the companion templates separately:

~~~sh
plugin_dir="$(codex plugin list --json | jq -r '.installed[] | select(.pluginId == "sol-advisor@sol-advisor") | .source.path')"
test -n "$plugin_dir"
test -d "$plugin_dir"
sh "$plugin_dir/scripts/install-agents.sh"
sh "$plugin_dir/scripts/install-agents.sh" --check
~~~

Without an explicit target, the installer uses the existing CODEX_HOME value when one is
already set, otherwise the user's default Codex agents directory. It does not invoke
Codex, edit config.toml, or overwrite a differing agent file. It only installs a
missing template and then verifies every installed copy byte-for-byte.

Start a **new Codex task** after the check passes. Native agent types are discovered at
task creation, so an existing task may not see the installed roles.

Then select GPT-5.6 Sol with High reasoning for the primary session and ask for
implementation work normally, or invoke the orchestration skill explicitly:

~~~text
Use $sol-advisor:orchestration to build this feature, verify it, and obtain the final Sol review before reporting done.
~~~

## Check and update

Run this check whenever a route must be trusted:

~~~sh
plugin_dir="$(codex plugin list --json | jq -r '.installed[] | select(.pluginId == "sol-advisor@sol-advisor") | .source.path')"
test -d "$plugin_dir"
sh "$plugin_dir/scripts/install-agents.sh" --check
~~~

To update the marketplace plugin and migrate the exact recognized v0.2.0 companion
files:

~~~sh
codex plugin marketplace upgrade sol-advisor
codex plugin add sol-advisor@sol-advisor
plugin_dir="$(codex plugin list --json | jq -r '.installed[] | select(.pluginId == "sol-advisor@sol-advisor") | .source.path')"
test -d "$plugin_dir"
sh "$plugin_dir/scripts/install-agents.sh"
sh "$plugin_dir/scripts/install-agents.sh" --check
~~~

Version 0.3.0 recognizes only byte-exact v0.2.0 legacy
`sol-advisor-luna-implementer.toml` and `sol-advisor-terra-implementer.toml` files.
Normal installer mode replaces the exact legacy Terra file with the current Terra /
High template, removes the exact legacy Luna file, and refuses modified, nonregular,
or symlinked destinations without partial agent-file mutation. `--check` is
non-mutating and fails until both current role files match exactly and Luna is absent.
This routing update was motivated by
[Eric Provencher's X post](https://x.com/pvncher/status/2083300990350954981).

Do not use a substitute agent as a shortcut. Start a fresh task after every successful
install or update.

## Runtime routing evidence

Native spawn/details metadata is the primary source of routing evidence. It must show
the selected custom agent type. When it also exposes model and effort, the orchestrator
compares those values with the role pin. If Desktop omits model or effort and the local
rollout is accessible, use the companion inspector as the authoritative read-only
fallback for those omitted fields:

~~~sh
plugin_dir="$(codex plugin list --json | jq -r '.installed[] | select(.pluginId == "sol-advisor@sol-advisor") | .source.path')"
thread_id="<native-subagent-thread-id>"
sh "$plugin_dir/scripts/inspect-agent-runtime.sh" "$thread_id"
~~~

For native `spawn_agent` routing, capture a UTC cutoff immediately before the spawn,
then retain the canonical `/root/<task>` path that native spawn returns. This avoids
mistaking an earlier rollout that reused the same task path for the new agent:

~~~sh
runtime_since="$(date -u +%Y-%m-%dT%H:%M:%SZ)" # immediately before native spawn_agent
agent_path="/root/<canonical-task-path-returned-by-spawn>"
sh "$plugin_dir/scripts/inspect-agent-runtime.sh" --agent-path "$agent_path" --since "$runtime_since"
~~~

The positional lowercase UUID interface remains supported for compatibility.

For a disposable fixture or a non-default local session root, pass it explicitly:

~~~sh
sh "$plugin_dir/scripts/inspect-agent-runtime.sh" --sessions-dir /absolute/path/to/sessions "$thread_id"
~~~

The UUID mode searches only rollout filenames ending in that exact thread id. Path mode
uses only exact session-metadata `agent_path` records at or after its inclusive cutoff,
resolves their UUID, and then applies the same strict filename and routing validation.
Both modes emit one compact JSON object with allowlisted routing fields. The helper
never prints prompts, messages, environment variables, tokens, configuration contents,
or arbitrary rollout payloads. It refuses invalid ids, no or ambiguous matches, and
missing or inconsistent role/model/effort; there is no inferred fallback. If public and
local evidence both exist, they must agree.

## How routing works

The Sol orchestrator writes a five-part spec for every implementation: objective, file
ownership, interfaces, constraints, and verification. Terra / High is the sole
implementation producer; Sol keeps architecture, routing, parent verification, and
acceptance in the primary session.

Before delegation and acceptance, the skill requires all of the following:

1. The installed role files pass the byte-for-byte companion check.
2. The native spawn tool exposes both exact names in the table above.
3. Public native spawn/details metadata identifies the selected role and, when exposed,
   its expected model and effort. If model or effort is omitted, the exact-rollout local
   inspector above must provide them instead.
4. The reviewer’s observed sandbox policy type and permission profile type are captured
   and reported.

A missing, stale, conflicting, unavailable, inconsistent, or unobservable
role/model/effort stops the affected lane with an actionable error. There is no silent
model, reasoning, or agent-type fallback, and per-spawn calls do not override the role
pins.

The Sol reviewer TOML requests read-only sandboxing, but the host permission profile
may broaden that request. If the observed sandbox policy type is read-only, review can
proceed with enforced isolation. If the host broadens it, review can proceed only as
behaviorally read-only when hard isolation is not required, the prompt forbids edits,
and the parent captures and verifies exact before-and-after repository/artifact state;
the broader sandbox and permission profile must be reported as residual risk. If hard
isolation is required, the sandbox cannot be observed, or any mutation occurs, stop the
review lane and do not claim enforced read-only isolation.

The orchestrator inspects every diff and reruns verification. A fresh Sol reviewer then
returns ship, fix-first, or rethink. The session cannot report completion until the
reviewer returns ship. These remain native Codex subagent threads; Sol Advisor does not
launch a nested Codex CLI process or globally reroute unrelated subagents.

## Local development

Install a checkout as a local marketplace when you want Codex to use its skill:

~~~sh
cd /absolute/path/to/sol-advisor
codex plugin marketplace add /absolute/path/to/sol-advisor
codex plugin add sol-advisor@sol-advisor
~~~

Run the repository verifier separately. It uses only a disposable target directory and
never changes your Codex configuration:

~~~sh
cd /absolute/path/to/sol-advisor
sh plugins/sol-advisor/scripts/verify.sh
git diff --check
~~~

To exercise the installer itself against an explicit disposable target:

~~~sh
cd /absolute/path/to/sol-advisor
scratch_agents="$(mktemp -d)"
sh plugins/sol-advisor/scripts/install-agents.sh --target-dir "$scratch_agents"
sh plugins/sol-advisor/scripts/install-agents.sh --target-dir "$scratch_agents" --check
~~~

To install this checkout's templates for real local development, use the same
repository-relative commands without --target-dir, then begin a new task:

~~~sh
cd /absolute/path/to/sol-advisor
sh plugins/sol-advisor/scripts/install-agents.sh
sh plugins/sol-advisor/scripts/install-agents.sh --check
~~~

After editing the plugin, validate both layers:

~~~sh
cd /absolute/path/to/sol-advisor
if [ -n "$CODEX_HOME" ]; then
  codex_skills="$CODEX_HOME/skills/.system"
else
  codex_skills="$HOME/.codex/skills/.system"
fi
uv run --no-project --with pyyaml python "$codex_skills/skill-creator/scripts/quick_validate.py" plugins/sol-advisor/skills/orchestration
uv run --no-project --with pyyaml python "$codex_skills/plugin-creator/scripts/validate_plugin.py" plugins/sol-advisor
jq empty .agents/plugins/marketplace.json plugins/sol-advisor/.codex-plugin/plugin.json
~~~

The verifier validates JSON and TOML, the two exact role pins, clean/current/missing
and idempotent installer behavior, exact-v0.2.0 migration, refusal/non-mutation gates,
runtime-inspector safe fixtures, contract references, and shell syntax. The uv commands
supply the validators' PyYAML dependency in a disposable environment. They do not
install the marketplace or mutate Codex configuration.

## License

MIT
