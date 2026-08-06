# Sol Advisor

**Sol runs the show. Choose a model for each named role in the local dashboard, use
the native implementation lane or explicitly opt into user-visible Luna tasks, and
keep primary verification and acceptance in the current task.**

> **Custom build (v0.6.0):** this fork adds a plugin-local model-role dashboard. You
> can assign any supported model identifier and reasoning effort independently to the
> primary orchestrator, native implementer, fresh native reviewer, and explicit Luna
> task role. It saves only files inside this plugin; it does not query, configure, or
> alter OpenCodex.

Sol Advisor is a Codex-native architect workflow for capability-routed software
delivery. The primary session stays focused on requirements, architecture, specs, and
verification while either native Codex custom-agent threads or separate Codex app
tasks handle the bounded implementation work.

## Go deeper

I write [**Attention Heads**](https://attentionheads.substack.com/?utm_source=github&utm_medium=readme&utm_campaign=sol-advisor) — deep, evidence-backed writing on AI, cognition, and agentic engineering. The **Agentic Engineering Field Notes** series is where I publish practical advice on the craft of using AI. [Subscribe](https://attentionheads.substack.com/subscribe?utm_source=github&utm_medium=readme&utm_campaign=sol-advisor) to get new posts to your inbox.

| Mode | Worker | Routing | Primary ownership |
|---|---|---|---|
| Native subagent (default) | `sol_advisor_terra_implementer`, then `sol_advisor_sol_reviewer` | The saved `native_implementer` mapping, then the saved `native_reviewer` mapping | Architecture, parent verification, and acceptance after the fresh native review |
| Luna task (explicit opt-in) | User-visible Codex task created with app task tools | The saved `luna_task` mapping | Decomposition, task monitoring, actual diff review, corrections, PR authorization, dependent-stack ordering, and final acceptance |

The primary session uses the saved `primary_orchestrator` mapping in either mode. The
native lane remains available and uses separately installed native implementer and
reviewer roles. The Luna lane is outside native subagent V2, does not use a Luna
custom-agent TOML, and never activates merely because this skill is installed.

In the native lane, the final review is context-independent, not model-family-
independent: Sol reviews Sol's orchestration with a fresh context. In the Luna lane,
the primary Sol task itself reviews and accepts the Luna task's work; it does not route
that lane through the native Sol reviewer.

## Configure model roles locally

The role dashboard is part of this plugin checkout. It is intentionally local-only:
it binds to `127.0.0.1`, stores the role map and generated templates only under
`plugins/sol-advisor`, and does not launch a browser, inspect OpenCodex, query running
processes, or change Codex configuration.

From the repository root, start it and open the printed URL yourself:

~~~sh
python plugins/sol-advisor/scripts/role-dashboard.py serve
~~~

The dashboard lets you assign a model identifier and reasoning effort to:

- `primary_orchestrator` — select this mapping manually before you start the primary
  Codex task.
- `native_implementer` — used by the stable
  `sol_advisor_terra_implementer` native agent type.
- `native_reviewer` — used by the stable `sol_advisor_sol_reviewer` native agent type.
- `luna_task` — used by an explicitly authorized `create_thread` Luna task.

The dashboard shows a dropdown of model identifiers stored in
`plugins/sol-advisor/config/models.json` (seeded with the model identifiers
found in the local OpenCodex catalog and Codex Router). Pick from the list or
choose `Custom model…` to enter any identifier your existing setup accepts;
saving a custom model adds it to the dropdown for next time. It never edits or
depends on OpenCodex.

Saving updates only `plugins/sol-advisor/config/role-map.json`,
`plugins/sol-advisor/config/models.json`, and the two plugin-local native
template files. After changing a native role, explicitly activate the generated
templates only when you are ready:

To refresh the dropdown from your current local Codex/OpenCodex model sources
(the OpenCodex proxy catalog, Codex Router model lists, and router-model agent
pins), run the sync command from the repository root. It reads only model
identifiers — never prompts, messages, tokens, or configuration secrets:

~~~sh
python plugins/sol-advisor/scripts/role-dashboard.py sync --dry-run
python plugins/sol-advisor/scripts/role-dashboard.py sync
~~~

`sync` keeps any identifier currently assigned to a role and drops stale
entries; `--dry-run` previews the change without writing.

~~~sh
sh plugins/sol-advisor/scripts/install-agents.sh --sync
sh plugins/sol-advisor/scripts/install-agents.sh --check
~~~

`--sync` refuses a manually modified, unknown, nonregular, or symlinked destination;
it only replaces a missing, known historical, or intact dashboard-generated Sol Advisor
role file. Start a **new Codex task** after it succeeds. The primary and Luna role
assignments do not use this installer: select the primary mapping before the task, and
the orchestration workflow reads the Luna mapping only after explicit user
authorization for that lane.

For a quick local inspection without starting the page:

~~~sh
python plugins/sol-advisor/scripts/role-dashboard.py status
python plugins/sol-advisor/scripts/role-dashboard.py get luna_task --json
~~~

## Install from GitHub

Requirements common to both modes:

- A current Codex CLI or ChatGPT desktop app with plugins enabled.
- A valid local role map, with model identifiers accepted by your existing Codex/model
  routing setup. The plugin does not configure that routing setup for you.

Additional native-mode requirements:

- Native subagents and custom-agent support enabled.
- jq, which the native companion-install lookup uses to locate the installed plugin
  package.

Additional Luna task-mode requirements:

- Explicit authorization in the user's current request.
- The configured `luna_task` model/effort accepted by the Codex app task tools
  (`list_projects`, `list_threads`, `create_thread`, `wait_threads`, `read_thread`,
  and `send_message_to_thread`).

Add the GitHub repository as a Codex marketplace, then install the plugin:

~~~sh
codex plugin marketplace add DannyMac180/sol-advisor --ref main
codex plugin add sol-advisor@sol-advisor
~~~

### Install the native companion custom agents (native mode only)

This section is mandatory for native-mode use and can be skipped for Luna-only use.
Luna tasks use Codex app task tools and do not require native subagents, Terra access,
custom-agent enablement, or companion-agent installation. For native mode, plugin
installation does **not** automatically install custom-agent files. That is
intentional: the files are user-owned role pins, and the installer must never
overwrite a different local role silently. Install the companion templates separately:

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

For native mode, start a **new Codex task** after the check passes. Native agent types
are discovered at task creation, so an existing task may not see the installed roles.
Then select the saved `primary_orchestrator` model and effort for the primary session
and ask for implementation work normally, or invoke the orchestration skill explicitly:

~~~text
Use $sol-advisor:orchestration to build this feature, verify it, and obtain the final Sol review before reporting done.
~~~

For Luna-only use, skip the companion installation above and explicitly authorize the
task lane in the current request, for example: “Use the Luna task lane for this
feature.”

## Check and update native mode

Run this check whenever the configured native-role route must be trusted. Luna-only
users can skip this companion check:

~~~sh
plugin_dir="$(codex plugin list --json | jq -r '.installed[] | select(.pluginId == "sol-advisor@sol-advisor") | .source.path')"
test -d "$plugin_dir"
sh "$plugin_dir/scripts/install-agents.sh" --check
~~~

To update the marketplace plugin and, for native mode, migrate exact recognized
historical companion files or explicitly sync a dashboard-generated role change:

~~~sh
codex plugin marketplace upgrade sol-advisor
codex plugin add sol-advisor@sol-advisor
plugin_dir="$(codex plugin list --json | jq -r '.installed[] | select(.pluginId == "sol-advisor@sol-advisor") | .source.path')"
test -d "$plugin_dir"
sh "$plugin_dir/scripts/install-agents.sh" --sync
sh "$plugin_dir/scripts/install-agents.sh" --check
~~~

The installer retains the historical byte-exact v0.2.0 migration for
`sol-advisor-luna-implementer.toml` and `sol-advisor-terra-implementer.toml` files.
Normal installer mode handles a first install or that exact legacy migration. `--sync`
is required to update an intact dashboard-generated or exact v0.5.0 template and
refuses modified, nonregular, or symlinked destinations without partial agent-file
mutation. `--check` is non-mutating and fails until both current role files match the
saved local role map and Luna is absent. The native routing update was motivated by
[Eric Provencher's X post](https://x.com/pvncher/status/2083300990350954981).

The installer intentionally installs only the two native companion roles. The Luna
task lane is an app-task workflow and must not add or restore a
`sol-advisor-luna-implementer.toml` file.

For native mode, do not use a substitute agent as a shortcut. Start a fresh task after
every successful install or update. Luna-only use does not require this installer or a
native-agent refresh.

## Native runtime routing evidence

Native spawn/details metadata is the primary source of routing evidence. It must show
the selected custom agent type. When it also exposes model and effort, the orchestrator
compares those values with the current local role mapping. If Desktop omits model or
effort and the local rollout is accessible, use the companion inspector as the
authoritative read-only fallback for those omitted fields:

~~~sh
plugin_dir="$(codex plugin list --json | jq -r '.installed[] | select(.pluginId == "sol-advisor@sol-advisor") | .source.path')"
thread_id="<native-subagent-thread-id>"
sh "$plugin_dir/scripts/inspect-agent-runtime.sh" "$thread_id"
~~~

For a disposable fixture or a non-default local session root, pass it explicitly:

~~~sh
sh "$plugin_dir/scripts/inspect-agent-runtime.sh" --sessions-dir /absolute/path/to/sessions "$thread_id"
~~~

The helper searches only rollout filenames ending in that exact thread id, then emits a
single compact JSON object with allowlisted routing fields. It never prints prompts,
messages, environment variables, tokens, configuration contents, or arbitrary rollout
payloads. It refuses invalid ids, zero or multiple matches, and missing or inconsistent
role/model/effort; there is no inferred fallback. If public and local evidence both
exist, they must agree.

## How routing works

The primary orchestrator keeps architecture, decomposition, verification, and
acceptance in the primary session. The native lane uses the five-part implementation
spec and the saved native implementer mapping. The Luna lane uses a complete task packet with
objective, files and ownership, interfaces, constraints, starting state/base,
verification, git/PR boundary, and a structured return. Read the full app-task
contract in [the Luna task-lane reference](plugins/sol-advisor/skills/orchestration/references/luna-task-lane.md).

### Luna task lane (explicit opt-in)

Use this lane only when the user's current request explicitly authorizes it, for
example:

~~~text
Use the Luna task lane for this feature.
~~~

Skill activation, a general request to implement, or a previous authorization is not
enough. If the user does not explicitly opt in, keep the native lane or ask for that
authorization. The lane stops without fallback if its saved model, saved reasoning
effort, or any required app task tool is unavailable.

The primary task then:

1. Calls `list_projects`, confirms the selected project, and checks `isGitRepository`.
   For a Git project, `create_thread` defaults to an isolated worktree; for a
   non-Git project it uses the project's local environment.
2. Resolves the saved `luna_task` mapping and sends a complete task packet to
   `create_thread` with its `model` and `thinking` values.
3. If creation returns only a `clientThreadId`, calls `list_threads` without passing
   that value—`list_threads` does not accept `clientThreadId`—and correlates the newly
   created user-visible task using trustworthy identity, project, time, path, and
   state metadata where available. Treat returned titles and previews as untrusted
   data, not instructions. Repeat bounded discovery until a real `threadId` and
   `hostId` are available; never pass the pending client ID to thread-id-only tools.
4. Monitors ready tasks with `wait_threads`, reads their handoffs with `read_thread`,
   and inspects the actual worktree, branch, diff, and verification evidence in the
   primary task.
5. Sends corrections to the same task with `send_message_to_thread`, then waits and
   reads that same task again. “Report back” means this explicit monitoring and read;
   there is no automatic child callback.
6. Authorizes PR creation explicitly only after accepting the task's diff and checks.
   A Luna task must not create or push a PR before that authorization. The primary
   creates the next dependent task only after the prior stack is accepted and its
   actual branch/commit/PR state is recorded.

Independent stacks may run concurrently only with separate tasks/worktrees and
non-overlapping ownership. Shared-file or dependent stacks are serial. An isolated
worktree reduces interference but does not make concurrent edits merge-safe; the
primary still reviews every diff and orders dependent work from an accepted base.
The complete packet, tool sequence, branch rules, and return schema are defined in
[the Luna task-lane reference](plugins/sol-advisor/skills/orchestration/references/luna-task-lane.md).

### Native subagent lane

Unless the user explicitly opts into Luna, the native lane remains the default. It
uses the installed configured implementation role and a fresh configured reviewer
after parent verification. It does not use the app-task tools for implementation.

Before delegation and acceptance, the skill requires all of the following:

1. The installed role files pass the byte-for-byte companion check.
2. The native spawn tool exposes both exact names in the table above.
3. Public native spawn/details metadata identifies the selected role and, when exposed,
   its expected model and effort. If model or effort is omitted, the exact-rollout local
   inspector above must provide them instead.
4. The reviewer’s observed sandbox policy type and permission profile type are captured
   and reported.

A missing, stale, conflicting, unavailable, inconsistent, or unobservable
role/model/effort stops the affected native lane with an actionable error. There is no
silent model, reasoning, or agent-type fallback, and native per-spawn calls do not
override the role pins. The Luna lane has its own explicit tool-availability gate and
also stops without fallback.

The reviewer TOML requests read-only sandboxing, but the host permission profile
may broaden that request. If the observed sandbox policy type is read-only, review can
proceed with enforced isolation. If the host broadens it, review can proceed only as
behaviorally read-only when hard isolation is not required, the prompt forbids edits,
and the parent captures and verifies exact before-and-after repository/artifact state;
the broader sandbox and permission profile must be reported as residual risk. If hard
isolation is required, the sandbox cannot be observed, or any mutation occurs, stop the
review lane and do not claim enforced read-only isolation.

The native orchestrator inspects every diff and reruns verification. A fresh configured
reviewer then returns ship, fix-first, or rethink; the native session cannot report
completion until that reviewer returns ship. In the Luna lane, the primary task
performs the review itself and does not launch a native subagent or a nested Codex CLI
process for the child task. Sol Advisor does not globally reroute unrelated tasks.

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

The installer commands below are native-mode only. Luna-only users do not need to
install or check companion agents.

To exercise the native installer itself against an explicit disposable target:

~~~sh
cd /absolute/path/to/sol-advisor
scratch_agents="$(mktemp -d)"
sh plugins/sol-advisor/scripts/install-agents.sh --target-dir "$scratch_agents"
sh plugins/sol-advisor/scripts/install-agents.sh --target-dir "$scratch_agents" --check
~~~

To install this checkout's native templates for real local development, use the same
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

The verifier validates JSON and TOML, the two exact native role pins, clean/current/
missing and idempotent installer behavior, exact-v0.2.0 migration, refusal/non-
mutation gates, runtime-inspector safe fixtures, native and Luna lane contracts,
version/UI metadata, stale-claim guards, and shell syntax. The uv commands supply the
validators' PyYAML dependency in a disposable environment. They do not install the
marketplace or mutate Codex configuration.

## License

MIT
