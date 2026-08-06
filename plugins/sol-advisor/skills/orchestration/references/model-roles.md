# Model roles and the local dashboard

Sol Advisor separates **roles** from **models**. The role names below describe
responsibility; the configured model identifier is a user choice. This plugin does
not hard-code a provider, inspect OpenCodex, enumerate models, or change another
application's configuration.

## Role map

The checked-in role map is
[`config/role-map.json`](../../../config/role-map.json), relative to this plugin's
root. It contains exactly these four assignments:

| Role key | Responsibility | How its model is applied |
|---|---|---|
| `primary_orchestrator` | Requirements, architecture, verification, acceptance | Select the configured model and effort manually when starting the primary Codex task. A skill cannot change an already-running task. |
| `native_implementer` | Bounded implementation in the native custom-agent lane | Generates `sol_advisor_terra_implementer`; explicitly sync the template into Codex before a new task. |
| `native_reviewer` | Fresh read-only review of the verified native diff | Generates `sol_advisor_sol_reviewer`; explicitly sync the template into Codex before a new task. |
| `luna_task` | Explicitly authorized, user-visible Codex app task | The orchestration workflow reads this model and effort when it calls `create_thread`. |

The two namespaced native agent types remain stable even if their configured models
change. They identify workflow roles, not a particular model family.

## Use the dashboard

From the repository root, start the dashboard:

~~~text
python plugins/sol-advisor/scripts/role-dashboard.py serve
~~~

Open the printed `http://127.0.0.1:8765/` address yourself. The server binds only to
the loopback interface and does not start a browser. It offers a dropdown of model
identifiers stored in `config/models.json` plus a `Custom model…` field for any
identifier your existing Codex/OpenCodex setup accepts—for example, an existing
OpenCodex combo name or a direct model name. The dashboard validates only safe
identifier syntax and known reasoning-effort values; it does not claim that a
provider accepts the selected value.

Saving has deliberately narrow scope:

1. It writes `config/role-map.json` inside this plugin.
2. It writes `config/models.json` inside this plugin, adding a saved custom model
   to the dropdown list.
3. It regenerates only this plugin's two native custom-agent templates.
4. It does not install those templates into Codex, modify OpenCodex, query local
   processes, or change the model of an existing task.

Use these non-server commands when useful:

~~~text
# Show every current assignment and whether generated native templates match it.
python plugins/sol-advisor/scripts/role-dashboard.py status

# Read one assignment, including from an orchestration preflight.
python plugins/sol-advisor/scripts/role-dashboard.py get luna_task --json

# Regenerate the two plugin-local native templates after a direct role-map edit.
python plugins/sol-advisor/scripts/role-dashboard.py apply
python plugins/sol-advisor/scripts/role-dashboard.py check
~~~

## Activate a native-role change deliberately

After saving a different `native_implementer` or `native_reviewer` assignment, the
generated template is still only inside the plugin checkout. To make a new Codex task
see it, explicitly run the existing companion installer:

~~~text
sh plugins/sol-advisor/scripts/install-agents.sh --sync
sh plugins/sol-advisor/scripts/install-agents.sh --check
~~~

`--sync` is required for a previously dashboard-generated or prior Sol Advisor
template. It accepts only a missing file, an exact recognized historical template, or
an intact dashboard-generated template; it refuses a symlink, nonregular file, or a
manually changed/unknown destination. Start a **new** Codex task after it succeeds.
The normal installer remains suitable for a first install into a missing destination.

The primary and Luna assignments do not use that installer:

- Choose the `primary_orchestrator` mapping before starting the primary task.
- The orchestration workflow resolves `luna_task` only after the current request
  explicitly authorizes the Luna task lane.

## Runtime evidence

Treat the role map as the expected routing contract, not proof of provider behavior.
For native roles, require the current plugin-local role map/template check, the
installed-agent exactness check, and observed native spawn/details metadata. Compare
the observed model and effort with the current mapping for the relevant role. For a
Luna task, record the accepted `create_thread` routing and task identity when the app
exposes those values; do not infer unreported provider behavior.
