# Sol Advisor

**A configurable, architect-first orchestration plugin for compatible Agent Plugins v1 clients.**

Sol Advisor keeps requirements, architecture, decomposition, diff inspection,
verification, and acceptance in the parent chat. Native implementer and advisor roles
use the exact model IDs and supported reasoning settings the user chooses during lazy
first-use setup. The orchestrator always inherits the parent chat's selected model
and effort.

## Recent changes

v0.6.0 adds schema-v2 four-role preferences, automatic v1 migration, fail-closed
runtime-evidence route resolution, bounded Fast, and safe four-role adapter lifecycle.
See the full [CHANGELOG.md](https://github.com/DannyMac180/sol-advisor/blob/main/CHANGELOG.md).

## Architecture

The flattened plugin contains:

- `plugin.json`: canonical Agent Plugins v1 package manifest.
- `.codex-plugin/plugin.json`: Codex-specific compatibility metadata.
- `mcp.json`: stdio MCP registration for `bun ${PLUGIN_ROOT}/mcp/server.ts`.
- `mcp/server.ts`: newline-delimited JSON-RPC server and configuration/adapter engine.
- `skills/setup/SKILL.md`: parent-chat first-use and reconfiguration interview.
- `skills/orchestration/SKILL.md`: architect workflow, routing, and review loops.
- `skills/routing/SKILL.md`: general routine, medium, hard, planning, and review entrypoint.
- `agents/` and `scripts/`: retained exact Codex v0.5 compatibility lane.

Plugin installation only makes these surfaces discoverable. It does **not** run setup,
install a hook, choose models, or write native role files. On the first orchestration
invocation, the skill checks setup state and starts the interview when configuration
is missing, corrupt, or from an unsupported schema.

Logical, non-secret preferences live in `${PLUGIN_DATA}/config.json`. Generated
client files are separate and appear only after an exact preview and explicit bound
confirmation. Bun is the only runtime prerequisite for the MCP server; the packaged
runtime has no repository-root or third-party runtime dependency.

## First-use interview

The interview stays in the parent/main chat and asks for client, project/user scope,
and four exact client-native model IDs copied from the client's picker or `/model`:

| Role | Purpose | Current Codex recommendation |
|---|---|---|
| Routine implementer | Bounded, mechanical, fully specified work | `gpt-5.6-luna`, `max` |
| Medium-compatible high | Medium routine work; stored as `roles.high` | `gpt-5.6-terra`, `high` |
| Hard implementer | Security, concurrency, algorithms, hard debugging, migrations, wide refactors | `gpt-5.6-sol`, `high` |
| Advisor | Commitment review and final diff/evidence verdict; requested read-only | `gpt-5.6-sol`, `high` |
| Orchestrator | Parent ownership and verification | `inherit` (Luna / Max / Standard recommended) |

These are editable recommendations, not a universal model catalog. Sol Advisor never
guesses, normalizes, silently falls back, or claims a model exists in another client.
The optional Codex app-task lane remains a distinct explicit opt-in for
`gpt-5.6-luna` / Max; it is never a fallback or a native role.

## Go deeper

I write [**Attention Heads**](https://attentionheads.substack.com/?utm_source=github&utm_medium=readme&utm_campaign=sol-advisor) — deep, evidence-backed writing on AI, cognition, and agentic engineering. The **Agentic Engineering Field Notes** series is where I publish practical advice on the craft of using AI. [Subscribe](https://attentionheads.substack.com/subscribe?utm_source=github&utm_medium=readme&utm_campaign=sol-advisor) to get new posts to your inbox.

## Client installation and adapter paths

### Codex installation from GitHub

Add the repository marketplace and install the plugin:

~~~sh
codex plugin marketplace add DannyMac180/sol-advisor --ref main
codex plugin add sol-advisor@sol-advisor
~~~

Start a new chat, then invoke the workflow explicitly or request orchestration normally:

~~~text
Use $sol-advisor:orchestration to build this feature, verify it, and obtain the configured advisor review before reporting done.

Use $sol-advisor:routing to choose a fail-closed routine, medium, hard, planning, or review route with current runtime evidence.
~~~

Update an existing marketplace installation with:

~~~sh
codex plugin marketplace upgrade sol-advisor
codex plugin add sol-advisor@sol-advisor
~~~

### Cursor installation from a local clone

Cursor officially supports loading Agent Plugins from `~/.cursor/plugins/local`, but
live testing found two Cursor 3.15.6 incompatibilities with the Agent Plugins v1 MCP
runtime contract:

- it rejects a symlink whose resolved target is outside the local-plugin directory;
- its plugin MCP process cannot resolve the portable bare `bun` command, even when
  Cursor is launched with Bun on `PATH`.

Until Cursor fixes those host issues, macOS users can use Sol Advisor's guarded local
compatibility installer. It keeps the canonical package unchanged, makes a physical plugin copy,
disables the failing MCP entry only in that copy, and adds an equivalent native MCP
entry to the selected project's `.cursor/mcp.json` using absolute, locally discovered
paths. Project scope is required; the installer never edits `~/.cursor/mcp.json`.

~~~sh
git switch agent-plugin-conformance
bun install --frozen-lockfile
bun run ci

# Choose the existing project that should receive the local MCP overlay.
workspace="$(pwd -P)"
bun tools/cursor-local.ts install --workspace "$workspace"
~~~

The macOS-only installer refuses unmanaged conflicts, symlinks in managed
Cursor/plugin-data paths, non-private plugin data, and changed managed state. An exact
same-workspace managed install is recoverable and idempotent. It preserves other servers
already present in `.cursor/mcp.json`, refuses concurrent edits, and records an exact
receipt for guarded cleanup.

In Cursor:

1. Open the exact `workspace` folder and run **Developer: Reload Window**.
2. Under **Customize → MCPs**, use Customize's own scope dropdown to select that exact
   workspace. The active project shown in Cursor Agents can be different; do not select
   a similarly named repository.
3. Open `sol-advisor` and enable its workspace source. Cursor keeps new or recreated
   project MCP sources disabled until the user explicitly enables them.
4. Confirm the local environment is **Connected** and all nine tools are enabled.
   If it remains **Disconnected**, or Cursor's shared MCP process leaves every server
   disconnected, fully quit Cursor—not merely the window—reopen the exact workspace,
   return to its Customize scope, and explicitly enable the source again. Do not change
   the command, paths, permissions, or canonical plugin manifest to force a connection.
5. If needed, verify `loadUserLocalPlugin sol-advisor loaded` in the `Cursor Plugins`
   output/log. Do not require a card under the user-level Plugins filter.
6. Start a new Agent chat and ask:
   `Run the Sol Advisor setup skill in this parent chat. Use Cursor project scope, ask
   one question at a time, and stop after showing the complete adapter preview.`

Copy exact model IDs from Cursor's model picker. Inspect all four generated files,
then repeat the exact `INSTALL <nonce>` token—not a generic “yes.” After installation,
reload Cursor. The native roles should be invocable as `/sol-advisor-routine`,
`/sol-advisor-high`, `/sol-advisor-hard`, and `/sol-advisor-advisor`.

Before cleanup, use the setup skill to uninstall its generated adapter files and reset
the active test profile with the required exact tokens. Then run:

~~~sh
bun tools/cursor-local.ts uninstall --workspace "$workspace"
~~~

Uninstall removes only an unchanged managed plugin copy and the exact project MCP entry
it installed. It preserves `<workspace>/.cursor/sol-advisor-dev-data` by design so a
local test cannot silently destroy preferences. `reset_configuration` applies only to
that workspace-local development data root; invoke it only after inspecting its preview
and exact token.

For the complete disposable-workspace procedure and evidence checklist, follow
[Developer smoke test: Cursor](#developer-smoke-test-cursor). Cursor's documented base
flow is [Test plugins locally](https://cursor.com/docs/plugins#test-plugins-locally),
but the compatibility overlay above is required for the tested Cursor 3.15.6 build.


For other clients, use only that client's documented Agent Plugins v1 UI or local
package mechanism; Sol Advisor does not claim a universal install command.

Install `plugins/sol-advisor` as the plugin root through a compatible Agent Plugins v1
client. Ensure `bun` is on the client's PATH and that it supplies an absolute,
existing, private `${PLUGIN_DATA}` directory. Then invoke orchestration; setup previews
all native files before requesting consent.

| Client | Project adapter | User adapter | Binding limits |
|---|---|---|---|
| Codex | `.codex/agents/*.toml` | `~/.codex/agents/*.toml` | Model + effort. Advisor requests `sandbox_mode = "read-only"`; verify observed sandbox. |
| Cursor | `.cursor/agents/*.md` | `~/.cursor/agents/*.md` | Model; optional `[effort=…]` syntax. Cursor may fall back when a pin is unavailable/restricted; Sol Advisor cannot detect or prevent host fallback. Read-only remains client/behavior dependent. |
| VS Code | `.github/agents/*.agent.md` | `~/.copilot/agents/*.agent.md` | Model only; effort and parent cost tier are session constraints. |
| GitHub Copilot | `.github/agents/*.agent.md` | `~/.copilot/agents/*.agent.md` | Model only; effort and parent cost tier are session constraints. |
| Kiro IDE/CLI | `.kiro/agents/*.md` | `~/.kiro/agents/*.md` | Model only; effort is session/per-model, not per-agent. |

ChatGPT Work web, Kiro web/mobile, and skills-only surfaces are not native client
profiles and cannot be saved through `save_preferences`. Use parent-chat prompt
guidance only; role binding is not enforceable. No live smoke-test claim is made for
those surfaces.

After any adapter install, update, or uninstall, start a new chat or reload the client
so native role discovery observes the new state.

## Preview, consent, reconfigure, and uninstall

`render_client_adapter` returns exact destinations, full contents, SHA-256 plan
digest, target-state hashes, warnings, and a short-lived one-time confirmation token.
It computes destinations from an existing workspace and the selected client/scope;
the parent never hands MCP an arbitrary destination path. User scope requires a
second exact token bound to the same preview.

Installation rejects traversal, symlink ancestors/targets, unmanaged conflicts,
drifted managed files, expired/replayed consent, and target changes since preview.
Managed files carry the exact `sol-advisor-managed:v1` marker and are recorded with
hashes. Updates create private backups. Uninstall first previews its files and token,
then removes only exact, unchanged managed files. Reconfiguration repeats the
interview and preview; reset requires its own exact confirmation and must not be used
to bypass a live managed install.

## Reconfigure, adapter uninstall, and plugin uninstall

Re-run the parent-chat interview explicitly when preferences change:

~~~text
Use $sol-advisor:setup to reconfigure my Sol Advisor client, scope, workspace, and exact native role choices.
~~~

Reconfiguration saves/selects a profile but does not write adapters until the new
exact preview is confirmed. Adapter uninstall is the `uninstall_client_adapter` flow:
it previews the current profile's managed files and confirmation token, then removes
only unchanged managed files. It does **not** uninstall the plugin package. To remove
the plugin itself, first uninstall managed adapters, then use the specific client's
documented plugin manager or UI. No cross-client plugin-uninstall command is assumed.

## MCP tools

The server implements `initialize`, `ping`, `tools/list`, and `tools/call` over
newline-delimited JSON-RPC. Its nine tools are:

- `get_setup_status`
- `get_preferences`
- `resolve_route`
- `save_preferences`
- `render_client_adapter`
- `install_client_adapter`
- `uninstall_client_adapter`
- `validate_configuration`
- `reset_configuration`

Configuration is schema-versioned and written atomically. Secret-like fields are
rejected recursively; model IDs and effort values cannot contain control characters.
No credentials belong in plugin configuration.

## Orchestration semantics

The parent owns the specification, architecture, decomposition, actual diff review,
rerun verification, correction loops, and acceptance. Worker reports are claims until
the parent verifies the working tree and checks. The five task classes route as
follows: routine to `routine`; medium to the `high` compatibility storage role; hard
to `hard`; and planning or review to `advisor`. The parent runs a route only when its
current evidence is fresh, exact, and challenge-bound, and the task is not review.
Call `resolve_route` first without evidence to obtain its expiring single-use challenge,
then pass the inspector's complete camelCase object unchanged. Agent evidence includes
an allowlisted `parentThreadId` that must equal the current parent `threadId`; freshness
comes only from complete, consistent authoritative turn contexts. Any route change requires
a fresh exact agent. `spawn-required` preserves the active challenge. Accepted parent
or target proof consumes it. Blocked provenance, same-thread evidence, or a target
mismatch invalidates it and requires a new route challenge.
Reviews are always fresh and read-only, with runtime evidence required before use. Sol
Advisor reports the observed guarantee rather than inventing one.

The historical exact Codex native compatibility lane remains separate: it uses a
separately installed Terra / High implementer and a fresh Sol / High reviewer. It
is available only after explicit current-request opt-in, never as a fallback. It does
not use a Luna custom-agent TOML. The Luna lane instead uses app task tools and is
outside native subagent V2.

| Mode | Worker | Parent ownership |
|---|---|---|
| Schema-v2 native default | Exact generated `routine`/`high`/`hard`/`advisor` role returned by challenge-first `resolve_route` | Architecture, diff/check verification, corrections, acceptance |
| Codex compatibility (explicit opt-in) | Static Terra / High implementer and fresh Sol / High reviewer | Architecture, diff/check verification, corrections, acceptance |
| Luna task (explicit opt-in) | User-visible `gpt-5.6-luna` / Max task | Monitoring, diff review, corrections, PR authorization, dependent ordering |

Use the Luna task lane only with current-request authorization such as: **“Use the
Luna task lane for this feature.”** It requires `list_projects`, `list_threads`,
`create_thread`, `wait_threads`, `read_thread`, and `send_message_to_thread`. A pending
`clientThreadId` is a setup handle, not a ready task ID. Missing tools, Luna, or Max
stop without fallback. The schema-v2 generated route is the native default. The static
Codex compatibility lane requires explicit current-request opt-in and does not use a
Luna companion file.

### Requirements common to both modes

- Bun available for portable MCP runtime.
- A compatible plugin client and exact user-selected model access.
- Parent ownership of verification and acceptance.

### Additional schema-v2 native-mode requirements

- A compatible native spawn tool exposing the exact generated role.
- Fresh, challenge-bound observable runtime routing; no unverified model/effort claim.

### Additional Luna task-mode requirements

- Explicit authorization in the current request.
- Luna / Max availability and all six app task tools.

The native companion installation is required only for explicit Codex compatibility-lane
use. Luna tasks do not require native subagents, Terra access, or companion TOML files.
Luna-only users do not need to run `scripts/install-agents.sh`.

## Retained Codex companion lane

Only after the user's current request explicitly opts into this exact legacy-compatible
native lane:

~~~sh
plugin_dir="$(codex plugin list --json | jq -r '.installed[] | select(.pluginId == "sol-advisor@sol-advisor") | .source.path')"
sh "$plugin_dir/scripts/install-agents.sh"
sh "$plugin_dir/scripts/install-agents.sh" --check
~~~

Start a fresh task afterward. The installer refuses conflicting or symlinked files and
retains the byte-exact v0.2.0 migration. Runtime routing may be inspected with:

~~~sh
sh "$plugin_dir/scripts/inspect-agent-runtime.sh" --challenge <resolve-route-challenge> <native-thread-id>
~~~

## Security model and limitations

- Sol Advisor fails closed: it chooses no fallback models, guessed aliases, or arbitrary write paths.
- Cursor itself may fall back when a pinned model is unavailable or restricted. Sol Advisor never chooses that fallback but cannot detect or prevent it.
- `${PLUGIN_DATA}` must be an absolute existing `0700`-equivalent directory: never `/`, the home directory, the plugin root, or a path with symlink ancestors. Its realpath/device/inode are pinned for the server process; Sol Advisor never chmods the host-supplied root.
- Install and uninstall use fsynced transaction journals, same-directory staging/quarantine, immediate hash/ancestor checks, and no-clobber creation. Recovery mutates only validated active-profile allowlisted paths with exact recorded hashes.
- Configuration is non-secret state; adapter files are allowlisted.
- Exact preview consent is necessary but does not establish client capability.
- Client-native read-only and effort guarantees vary. Only observed evidence counts.
- Standard manifest conformance is packaging conformance, not behavioral parity.
- Unsupported web/mobile/skills-only surfaces are prompt-only.
- No live cross-client behavioral claim is made without a real client test.

## Developer smoke test: Cursor

Use this procedure from the `agent-plugin-conformance` branch before claiming live
Cursor support. It follows [Cursor's documented local-plugin flow](https://cursor.com/docs/plugins#test-plugins-locally)
and uses project scope plus a disposable workspace so it does not touch global agent
files. Record the Cursor version, chosen model IDs, observed subagent details, and any
fallback or permission message.

### 1. Create an isolated workspace and install the compatibility bridge

From this repository:

~~~sh
git switch agent-plugin-conformance
bun install --frozen-lockfile
bun run ci

tmp_base="$(cd "${TMPDIR:-/tmp}" && pwd -P)"
smoke_dir="$(mktemp -d "$tmp_base/sol-advisor-cursor-smoke.XXXXXX")"
git -C "$smoke_dir" init
bun tools/cursor-local.ts install --workspace "$smoke_dir"
printf 'Open this folder in Cursor: %s\n' "$smoke_dir"
~~~

This creates a physical plugin copy and a project-native MCP bridge. Cursor 3.15.6
rejects external local-plugin symlinks and cannot resolve the canonical plugin MCP's
bare `bun` executable. The bridge suppresses only the copied plugin's failing MCP entry;
the repository's canonical `mcp.json` remains unchanged for conformant clients.

Open the printed folder in Cursor and run **Developer: Reload Window**. Then:

1. Open **Customize → MCPs** and, in Customize's own scope dropdown, select the exact
   `sol-advisor-cursor-smoke…` workspace. Do not select the similarly named source
   repository, even if Cursor Agents currently shows it as the active project.
2. Open `sol-advisor` and explicitly enable its workspace source. Reinstalling or
   recreating `.cursor/mcp.json` can cause Cursor to require this consent again.
3. Confirm **Local — Connected** and these nine enabled tools:
   `get_setup_status`, `get_preferences`, `save_preferences`,
   `render_client_adapter`, `install_client_adapter`, `uninstall_client_adapter`, `resolve_route`,
   `validate_configuration`, and `reset_configuration`.
4. If the source remains **Disconnected**, or all MCP servers become disconnected,
   fully quit Cursor, reopen the printed workspace, select its Customize scope again,
   and re-enable the source. A window reload alone did not recover the shared MCP process
   in the live Cursor 3.15.6 smoke test. Preserve the failure logs before restarting.
5. Confirm `loadUserLocalPlugin sol-advisor loaded` in the `Cursor Plugins` output/log.

Workspace MCP sources are disabled by default; enabling this source is an intentional
user security boundary. The connected identifier should be project-scoped (for example,
`project-0-sol-advisor-cursor-smoke-sol-advisor`), not the failing
`plugin-sol-advisor-sol-advisor` identifier. Record any different behavior as a host
failure rather than silently substituting another server.

Keep `smoke_dir` in that terminal for the later checks and cleanup.

### 2. Run setup in the parent chat

Open a new Cursor Agent chat and say:

~~~text
Run the Sol Advisor setup skill in this parent chat. Configure Cursor project scope
for this exact workspace: <paste smoke_dir>. Ask one question at a time. I will copy
exact model IDs from Cursor's model picker. Show the full adapter preview and stop
before installation until I repeat the exact token.
~~~

Choose exact model IDs that are currently available to your Cursor account. Where the
model supports it, choose an effort value such as `high`; the generated Cursor model
value should use Cursor's documented `model-id[effort=high]` syntax. Before confirming,
verify that the preview contains only these four destinations and their complete
contents:

~~~text
<smoke_dir>/.cursor/agents/sol-advisor-routine.md
<smoke_dir>/.cursor/agents/sol-advisor-high.md
<smoke_dir>/.cursor/agents/sol-advisor-hard.md
<smoke_dir>/.cursor/agents/sol-advisor-advisor.md
~~~

In the terminal, confirm preview was non-mutating:

~~~sh
test ! -e "$smoke_dir/.cursor/agents/sol-advisor-routine.md"
test ! -e "$smoke_dir/.cursor/agents/sol-advisor-high.md"
test ! -e "$smoke_dir/.cursor/agents/sol-advisor-hard.md"
test ! -e "$smoke_dir/.cursor/agents/sol-advisor-advisor.md"
~~~

Repeat the exact `INSTALL <nonce>` token in chat. Do not use a generic “yes.” Confirm
all four files now exist, contain `sol-advisor-managed:v1`, and no other file was
created under `.cursor/agents`:

~~~sh
for name in routine high hard advisor; do
  test -f "$smoke_dir/.cursor/agents/sol-advisor-$name.md"
done
test "$(find "$smoke_dir/.cursor/agents" -maxdepth 1 -type f | wc -l | tr -d ' ')" = 4
find "$smoke_dir/.cursor/agents" -maxdepth 1 -type f -print -exec grep -H 'sol-advisor-managed:v1' {} \;
~~~

### 3. Verify discovery, routing, and review

Run **Developer: Reload Window** again and start a new Agent chat. Cursor custom
subagents support explicit `/name` invocation. Perform these checks:

1. Invoke `/sol-advisor-routine` to create `cursor-smoke.txt` containing one known
   line. Confirm its subagent details show the configured model/options, or record any
   Cursor fallback warning.
2. Invoke `/sol-advisor-high` to append a second known line while checking the file for
   a deliberately described edge case. Confirm its details show the configured high
   role model/options, or record any fallback warning.
3. Invoke `/sol-advisor-hard` for a bounded migration or concurrency review task. Confirm
   its details show the configured hard role model/options, or record any fallback warning.
4. Before invoking the advisor, run `advisor_before="$(git -C "$smoke_dir" status --short)"`
   in the same terminal. Invoke `/sol-advisor-advisor` to review the file without
   changing it. Confirm the agent is shown as read-only, then run
   `test "$(git -C "$smoke_dir" status --short)" = "$advisor_before"` to prove the
   advisor created no additional change.
5. Ask: `Use the Sol Advisor orchestration skill to append one line to
   cursor-smoke.txt through the routine role, verify the diff, and obtain the advisor
   verdict.` Confirm setup does not repeat, the parent remains the orchestrator, and
   the configured routine and advisor roles are used.
6. In the same parent chat, ask Sol Advisor to call `get_setup_status` and
   `validate_configuration` for the exact smoke workspace. Both should report a ready,
   valid project profile.

Cursor documents that it may substitute a compatible model when a pin is restricted
or unavailable. Treat any such substitution as an observed host limitation, not as a
successful exact-model routing claim.

### 4. Uninstall and clean up

In the parent chat, say:

~~~text
Use the Sol Advisor setup skill to uninstall this active project adapter. Preview the
managed files first and do not remove anything until I repeat the exact uninstall token.
After uninstall succeeds, preview reset_configuration for this disposable workspace's
isolated development data root and require its exact reset token before clearing it.
~~~

Repeat each exact token, then verify the four managed agent files are gone. Remove the
unchanged compatibility bridge and guarded disposable workspace:

~~~sh
bun tools/cursor-local.ts uninstall --workspace "$smoke_dir"
case "$smoke_dir" in
  "$tmp_base"/sol-advisor-cursor-smoke.*) rm -rf -- "$smoke_dir" ;;
  *) echo "Refusing to remove unexpected workspace: $smoke_dir" >&2; exit 1 ;;
esac
~~~

The compatibility uninstaller deliberately preserves the isolated
`<workspace>/.cursor/sol-advisor-dev-data` directory. In this disposable smoke workspace,
`reset_configuration` affects only that local data root; the guarded workspace removal
then deletes it without touching another project's preferences.

A passing smoke test requires successful plugin discovery plus the documented project-MCP
compatibility bridge, lazy parent-chat setup,
non-mutating preview, exact-token installation, all four native subagents, observable
routine/high/hard/advisor routing, unchanged-file advisor review, validated configuration, and
exact managed-file uninstall. Add this evidence to the draft PR before making it ready
for review:

~~~text
Cursor version:
Plugin loaded + project MCP bridge connected (9 tools): pass/fail
Setup stayed in parent chat: pass/fail
Configured routine/high/hard/advisor model values:
Preview paths/content inspected: pass/fail
No files before exact token: pass/fail
Four managed files after token: pass/fail
Observed routine routing/model/fallback:
Observed high routing/model/fallback:
Observed hard routing/model/fallback:
Observed advisor routing/read-only/no-diff:
Orchestration reused saved setup: pass/fail
validate_configuration result:
Exact uninstall + cleanup: pass/fail
Notes/screenshots/log references:
~~~

## Local testing and development

~~~sh
bun install --frozen-lockfile
bun run test
bun run validate
bun run ci
bun run tag:check -- v0.6.0
bun run release:check
git diff --check
~~~

`bun run release:check` builds a flattened archive, extracts it, validates its packaged
manifests/skills/runtime, and starts the extracted MCP server with isolated HOME and
PLUGIN_DATA. Tagged releases remain CI-gated; this repository does not overwrite an
existing release.

## License

MIT. See [LICENSE](https://github.com/DannyMac180/sol-advisor/blob/main/LICENSE).
