#!/usr/bin/env python3
"""Manage Sol Advisor's plugin-local model-to-role configuration.

This utility never connects to, starts, stops, or configures OpenCodex. It accepts
model identifiers as text and writes only files inside this plugin directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PLUGIN_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = PLUGIN_DIR / "config" / "role-map.json"
MODELS_PATH = PLUGIN_DIR / "config" / "models.json"
AGENTS_DIR = PLUGIN_DIR / "agents"
SCHEMA_VERSION = 1
MAX_REQUEST_BYTES = 64 * 1024
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-~]{0,127}$")
EFFORTS = ("minimal", "low", "medium", "high", "max")
DEFAULT_MODELS = (
    "codex-auto-review",
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-pro",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.5",
    "gpt-5.6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "openrouter/anthropic-claude-sonnet-5",
    "openrouter/deepseek-deepseek-v4-flash-0731",
    "openrouter/moonshotai-kimi-k3",
    "openrouter/openai-gpt-5.6-luna",
    "openrouter/openai-gpt-5.6-luna-pro",
    "openrouter/openai-gpt-5.6-terra",
    "openrouter/openai-gpt-5.6-terra-pro",
    "openrouter/~deepseek/deepseek-v4-flash-latest",
)
ROLE_ORDER = (
    "primary_orchestrator",
    "native_implementer",
    "native_reviewer",
    "luna_task",
)

ROLE_METADATA = {
    "primary_orchestrator": {
        "title": "Primary orchestrator",
        "description": "Owns requirements, architecture, verification, and final acceptance in the current Codex task.",
        "application": "Select this model and effort manually for the primary Codex task. A plugin cannot change an already-running task's model.",
    },
    "native_implementer": {
        "title": "Native implementer",
        "description": "Runs bounded implementation work through the installed Terra custom-agent role.",
        "application": "Saving regenerates this plugin's Terra template. Sync it into Codex only with the explicit installer command shown below.",
    },
    "native_reviewer": {
        "title": "Fresh native reviewer",
        "description": "Performs context-clean final review through the installed read-only Sol custom-agent role.",
        "application": "Saving regenerates this plugin's Sol reviewer template. The requested read-only sandbox remains part of the role.",
    },
    "luna_task": {
        "title": "User-visible Luna task",
        "description": "Runs an explicitly authorized Codex app task while the primary task retains review and acceptance ownership.",
        "application": "The orchestration skill reads this model and effort when it creates an explicitly authorized Luna task.",
    },
}


class ConfigError(ValueError):
    """The role map is incomplete, malformed, or unsafe to render."""


def canonical_config_text(config: dict[str, Any]) -> str:
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def normalize_model(value: Any, role_name: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{role_name}.model must be a string.")
    if value != value.strip() or not MODEL_PATTERN.fullmatch(value):
        raise ConfigError(
            f"{role_name}.model must be a model identifier with no whitespace or quotes "
            "(for example: provider/model-name or openrouter/model-name)."
        )
    return value


def normalize_effort(value: Any, role_name: str) -> str:
    if not isinstance(value, str) or value not in EFFORTS:
        raise ConfigError(f"{role_name}.effort must be one of: {', '.join(EFFORTS)}.")
    return value


def validate_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConfigError("Role map must be a JSON object.")
    if set(raw) != {"schema_version", "roles"}:
        raise ConfigError("Role map must contain only schema_version and roles.")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ConfigError(f"schema_version must be {SCHEMA_VERSION}.")
    roles = raw.get("roles")
    if not isinstance(roles, dict) or set(roles) != set(ROLE_ORDER):
        raise ConfigError("Role map must define exactly the supported Sol Advisor roles.")

    normalized_roles: dict[str, dict[str, str]] = {}
    for role_name in ROLE_ORDER:
        assignment = roles[role_name]
        if not isinstance(assignment, dict) or set(assignment) != {"model", "effort"}:
            raise ConfigError(f"{role_name} must contain only model and effort.")
        normalized_roles[role_name] = {
            "model": normalize_model(assignment["model"], role_name),
            "effort": normalize_effort(assignment["effort"], role_name),
        }
    return {"schema_version": SCHEMA_VERSION, "roles": normalized_roles}


def load_config() -> dict[str, Any]:
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Role map is missing: {CONFIG_PATH.relative_to(PLUGIN_DIR)}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Role map is not valid JSON: {exc.msg}.") from exc
    return validate_config(raw)


def validate_models(raw: Any) -> list[str]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("Model list must be a non-empty array of identifiers.")
    seen: set[str] = set()
    models: list[str] = []
    for item in raw:
        if not isinstance(item, str) or item != item.strip() or not MODEL_PATTERN.fullmatch(item):
            raise ConfigError(
                f"Model entry is not a valid identifier: {item!r} (no whitespace or quotes)."
            )
        if item in seen:
            raise ConfigError(f"Duplicate model entry: {item}.")
        seen.add(item)
        models.append(item)
    return models


def load_models() -> list[str]:
    """Return the dashboard dropdown list, falling back to built-in defaults."""

    try:
        raw = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return list(DEFAULT_MODELS)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Model list is not valid JSON: {exc.msg}.") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "models"}:
        raise ConfigError("Model list file must contain only schema_version and models.")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ConfigError(f"Model list schema_version must be {SCHEMA_VERSION}.")
    return validate_models(raw["models"])


def save_models(models: list[str]) -> None:
    atomic_write(
        MODELS_PATH,
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "models": models},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
    )


def toml_string(value: str) -> str:
    """JSON strings are valid TOML basic strings for restricted role-map values."""

    return json.dumps(value, ensure_ascii=False)


def generated_template(body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return (
        "# Generated by Sol Advisor local role dashboard. Do not edit manually.\n"
        f"# sol-advisor-role-map-sha256: {digest}\n"
        f"{body}"
    )


def render_terra_template(assignment: dict[str, str]) -> str:
    body = "\n".join(
        (
            'name = "sol_advisor_terra_implementer"',
            'description = "Sol Advisor\'s sole implementation lane for routine and complex work."',
            f"model = {toml_string(assignment['model'])}",
            f"model_reasoning_effort = {toml_string(assignment['effort'])}",
            "",
            'developer_instructions = """',
            "You are Sol Advisor's sole implementation worker for routine, context-heavy,",
            "higher-risk, and wider-blast-radius work. Execute the supplied five-part specification",
            "within the settled architecture. Preserve every stated interface and constraint, stay",
            "within the owned file set, and document material judgment calls.",
            "",
            "You are not alone in the codebase: preserve concurrent edits and do not revert",
            "unrelated work. Surface ambiguity, scope conflicts, or verification failures rather",
            "than redesigning the architecture without direction. Run the requested checks and",
            "report actual evidence. Do not silently substitute a different role, model, or",
            "reasoning level; this installed custom-agent profile is the only implementation lane.",
            '"""',
            "",
        )
    )
    return generated_template(body)


def render_sol_template(assignment: dict[str, str]) -> str:
    body = "\n".join(
        (
            'name = "sol_advisor_sol_reviewer"',
            'description = "Sol Advisor\'s fresh, read-only final review lane for inspected diffs and evidence."',
            f"model = {toml_string(assignment['model'])}",
            f"model_reasoning_effort = {toml_string(assignment['effort'])}",
            'sandbox_mode = "read-only"',
            "",
            'developer_instructions = """',
            "You are Sol Advisor's fresh final reviewer. Remain strictly read-only: do not create,",
            "modify, delete, format, or implement files, and do not broaden the requested scope.",
            "Inspect the actual files, accumulated change set, stated interfaces and constraints,",
            "and verification evidence in a fresh context.",
            "",
            "Return exactly one verdict: ship, fix-first, or rethink. Base the verdict on concrete,",
            "evidence-backed findings. Use fix-first only for bounded required corrections and",
            "rethink when the architecture or scope must change. Do not silently substitute a",
            "different role, model, or reasoning level; this installed custom-agent profile is the",
            "required read-only review lane.",
            '"""',
            "",
        )
    )
    return generated_template(body)


def native_templates(config: dict[str, Any]) -> dict[Path, str]:
    roles = config["roles"]
    return {
        AGENTS_DIR / "sol-advisor-terra-implementer.toml": render_terra_template(
            roles["native_implementer"]
        ),
        AGENTS_DIR / "sol-advisor-sol-reviewer.toml": render_sol_template(
            roles["native_reviewer"]
        ),
    }


def atomic_write(path: Path, content: str) -> None:
    """Atomically write only beside the requested plugin-local path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def write_native_templates(config: dict[str, Any]) -> None:
    for path, content in native_templates(config).items():
        atomic_write(path, content)


def save_config_and_templates(config: dict[str, Any]) -> None:
    """Persist the desired map, then materialize its native-role template cache."""

    write_native_templates(config)
    atomic_write(CONFIG_PATH, canonical_config_text(config))


def native_template_status(config: dict[str, Any]) -> dict[str, bool]:
    status: dict[str, bool] = {}
    for path, expected in native_templates(config).items():
        try:
            actual = path.read_text(encoding="utf-8")
            status[path.name] = actual.replace("\r\n", "\n").replace("\r", "\n") == expected
        except FileNotFoundError:
            status[path.name] = False
    return status


def status_payload(config: dict[str, Any]) -> dict[str, Any]:
    templates = native_template_status(config)
    return {
        "config": config,
        "role_metadata": ROLE_METADATA,
        "models": load_models(),
        "native_templates": templates,
        "native_templates_current": all(templates.values()),
        "scope": {
            "writes": [
                "config/role-map.json",
                "config/models.json",
                "agents/sol-advisor-terra-implementer.toml",
                "agents/sol-advisor-sol-reviewer.toml",
            ],
            "does_not_do": [
                "query, start, stop, or configure OpenCodex",
                "inspect other local processes or applications",
                "install or overwrite Codex custom-agent files",
                "change the model of an already-running Codex task",
            ],
        },
    }


def dashboard_html() -> str:
    effort_options = "".join(
        f'<option value="{effort}">{effort}</option>' for effort in EFFORTS
    )
    cards: list[str] = []
    for role_name in ROLE_ORDER:
        metadata = ROLE_METADATA[role_name]
        native_class = " native" if role_name in {"native_implementer", "native_reviewer"} else ""
        cards.append(
            "\n".join(
                (
                    f'<section class="card{native_class}" data-role="{role_name}">',
                    '  <div class="card-heading">',
                    f'    <h2>{metadata["title"]}</h2>',
                    f'    <code>{role_name}</code>',
                    "  </div>",
                    f'  <p>{metadata["description"]}</p>',
                    "  <label>Model",
                    f'    <select name="{role_name}-model" class="model-select" required></select>',
                    f'    <input name="{role_name}-model-custom" class="model-custom" hidden autocomplete="off" spellcheck="false" maxlength="128" placeholder="Type a custom model identifier" />',
                    "  </label>",
                    "  <label>Reasoning effort",
                    f'    <select name="{role_name}-effort">{effort_options}</select>',
                    "  </label>",
                    f'  <p class="application">{metadata["application"]}</p>',
                    "</section>",
                )
            )
        )
    role_names_json = json.dumps(ROLE_ORDER)
    cards_html = "\n".join(cards)
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sol Advisor model roles</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      --bg: #0a0e13;
      --panel: #121a24;
      --panel-2: #0e151d;
      --border: #223042;
      --border-strong: #32455c;
      --text: #e9f0f8;
      --text-dim: #9fb1c6;
      --accent: #4da3e8;
      --danger: #ff9b92;
      --radius: 12px;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); min-height: 100vh; }}
    main {{ max-width: 1000px; margin: 0 auto; padding: 36px 28px 64px; }}
    header {{ display: flex; align-items: baseline; justify-content: space-between; gap: 14px; flex-wrap: wrap; }}
    h1 {{ font-size: 1.45rem; margin: 0; letter-spacing: -0.02em; }}
    .header-note {{ color: var(--text-dim); font-size: .85rem; }}
    .lede {{ margin: 10px 0 20px; color: var(--text-dim); font-size: .95rem; line-height: 1.55; max-width: 76ch; }}
    .notice {{ border: 1px solid var(--border); background: var(--panel-2); border-radius: 10px; padding: 12px 16px; font-size: .9rem; color: var(--text-dim); line-height: 1.5; margin-bottom: 24px; }}
    .notice strong {{ color: var(--text); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }}
    .card {{ border: 1px solid var(--border); background: var(--panel); border-radius: var(--radius); padding: 18px; display: grid; gap: 14px; align-content: start; }}
    .card.native {{ border-color: var(--border-strong); }}
    .card-heading {{ display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }}
    .card-heading h2 {{ margin: 0; font-size: 1rem; }}
    .card-heading code {{ font-size: .72rem; color: var(--text-dim); overflow-wrap: anywhere; }}
    .card > p {{ margin: 0; color: var(--text-dim); font-size: .88rem; line-height: 1.5; }}
    label {{ display: grid; gap: 6px; font-size: .82rem; font-weight: 650; }}
    input, select {{ width: 100%; min-width: 0; background: var(--panel-2); border: 1px solid var(--border-strong); border-radius: 8px; color: var(--text); padding: 9px 11px; font: inherit; font-size: .92rem; }}
    select {{ text-overflow: ellipsis; white-space: nowrap; overflow: hidden; }}
    .model-select, .model-select option, .model-custom {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    .model-custom[hidden] {{ display: none; }}
    input:focus-visible, select:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 1px; border-color: var(--accent); }}
    .application {{ border-top: 1px solid var(--border); padding-top: 12px; font-size: .82rem; color: var(--text-dim); }}
    .actions {{ margin-top: 22px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }}
    button {{ cursor: pointer; border: 0; border-radius: 9px; background: var(--accent); color: #06121e; font-weight: 700; padding: 11px 18px; font: inherit; font-size: .92rem; }}
    button:hover {{ background: #70bcf2; }}
    button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    #status {{ color: var(--text-dim); font-size: .9rem; min-height: 1.4em; }}
    .error {{ color: var(--danger) !important; }}
    .next {{ margin-top: 30px; padding: 18px 20px; border-radius: var(--radius); background: var(--panel-2); border: 1px solid var(--border); }}
    .next h2 {{ margin: 0 0 10px; font-size: .95rem; }}
    .next p {{ margin: 0 0 10px; color: var(--text-dim); font-size: .88rem; line-height: 1.5; }}
    .next p:last-child {{ margin-bottom: 0; }}
    pre {{ margin: 0 0 12px; overflow-x: auto; white-space: pre; color: #c3e3ff; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; font-size: .82rem; line-height: 1.5; }}
    @media (max-width: 720px) {{ main {{ padding: 24px 16px 44px; }} .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Sol Advisor model roles</h1>
      <span class="header-note">Local-only · loopback dashboard</span>
    </header>
    <p class="lede">Assign a model identifier and reasoning effort to each role in this plugin's workflow. Pick from the dropdown or choose Custom model… to enter an identifier your existing setup accepts; the dropdown list is stored inside this plugin only, and this page does not query or configure OpenCodex or any other application.</p>
    <div class="notice"><strong>Local-only scope.</strong> Saving writes only this plugin's role map, model list, and two generated native-agent templates. It does not install them into Codex, change the active task, or access another program. After saving native roles, use the explicit installer command below from a new terminal when you are ready.</div>
    <form id="role-form">
      <div class="grid">{cards_html}</div>
      <div class="actions">
        <button type="submit">Save role assignments</button>
        <span id="status" aria-live="polite">Loading the local role map…</span>
      </div>
    </form>
    <section class="next">
      <h2>Use the saved roles</h2>
      <p>For a native role change, start a new Codex task after explicitly syncing the plugin-managed agent templates. The sync command safely refuses manually edited or unknown destination files.</p>
      <pre>python plugins/sol-advisor/scripts/role-dashboard.py status
sh plugins/sol-advisor/scripts/install-agents.sh --sync
sh plugins/sol-advisor/scripts/install-agents.sh --check</pre>
      <p>For the primary role, select the saved model/effort manually in Codex before delegation. For a Luna task, the orchestration skill reads the saved mapping when the current request explicitly authorizes that lane.</p>
    </section>
  </main>
  <script>
    const roleNames = {role_names_json};
    const form = document.querySelector('#role-form');
    const status = document.querySelector('#status');
    const customValue = '__custom__';
    let models = [];

    function setStatus(message, isError = false) {{
      status.textContent = message;
      status.classList.toggle('error', isError);
    }}

    function populateModelOptions(select, selected) {{
      select.replaceChildren();
      for (const model of models) {{
        const option = document.createElement('option');
        option.value = model;
        option.textContent = model;
        select.appendChild(option);
      }}
      const customOption = document.createElement('option');
      customOption.value = customValue;
      customOption.textContent = 'Custom model…';
      select.appendChild(customOption);
      select.value = models.includes(selected) ? selected : customValue;
    }}

    function syncCustomInput(roleName, focus = false) {{
      const select = document.querySelector(`[name="${{roleName}}-model"]`);
      const customInput = document.querySelector(`[name="${{roleName}}-model-custom"]`);
      const isCustom = select.value === customValue;
      customInput.hidden = !isCustom;
      if (isCustom && focus) customInput.focus();
    }}

    function modelValue(roleName) {{
      const select = document.querySelector(`[name="${{roleName}}-model"]`);
      if (select.value !== customValue) return select.value;
      return document.querySelector(`[name="${{roleName}}-model-custom"]`).value.trim();
    }}

    function setRoleValues(config) {{
      for (const roleName of roleNames) {{
        const select = document.querySelector(`[name="${{roleName}}-model"]`);
        const customInput = document.querySelector(`[name="${{roleName}}-model-custom"]`);
        populateModelOptions(select, config.roles[roleName].model);
        if (select.value === customValue) {{
          customInput.value = config.roles[roleName].model;
        }}
        syncCustomInput(roleName);
        document.querySelector(`[name="${{roleName}}-effort"]`).value = config.roles[roleName].effort;
      }}
    }}

    for (const roleName of roleNames) {{
      document.querySelector(`[name="${{roleName}}-model"]`).addEventListener('change', () => syncCustomInput(roleName, true));
    }}

    async function load() {{
      try {{
        const response = await fetch('/api/config', {{cache: 'no-store'}});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Unable to load the local role map.');
        models = data.models || [];
        setRoleValues(data.config);
        setStatus(data.native_templates_current ? 'Native templates match the saved role map.' : 'Role map loaded; native templates need generation.');
      }} catch (error) {{
        setStatus(error.message, true);
      }}
    }}

    form.addEventListener('submit', async (event) => {{
      event.preventDefault();
      const config = {{schema_version: {SCHEMA_VERSION}, roles: {{}}}};
      for (const roleName of roleNames) {{
        const model = modelValue(roleName);
        if (!model) {{
          setStatus(`Model for ${{roleName}} is required.`, true);
          return;
        }}
        config.roles[roleName] = {{
          model: model,
          effort: document.querySelector(`[name="${{roleName}}-effort"]`).value,
        }};
      }}
      setStatus('Saving the local role map and generating local templates…');
      try {{
        const response = await fetch('/api/config', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(config),
        }});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Unable to save the local role map.');
        models = data.models || models;
        setRoleValues(data.config);
        setStatus('Saved locally. Native templates were generated; run the explicit --sync command only when you want Codex to use them.');
      }} catch (error) {{
        setStatus(error.message, true);
      }}
    }});

    load();
  </script>
</body>
</html>'''


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "SolAdvisorRoleDashboard/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep routine browser requests out of the dashboard's concise terminal output.
        return

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_payload(self, message: str, status: HTTPStatus) -> None:
        self.send_json({"ok": False, "error": message}, status)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        route = urlparse(self.path).path
        if route == "/":
            body = dashboard_html().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route == "/api/config":
            try:
                self.send_json({"ok": True, **status_payload(load_config())})
            except ConfigError as exc:
                self.send_error_payload(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self.send_error_payload("Not found.", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        route = urlparse(self.path).path
        if route != "/api/config":
            self.send_error_payload("Not found.", HTTPStatus.NOT_FOUND)
            return
        content_length = self.headers.get("Content-Length")
        try:
            length = int(content_length or "")
        except ValueError:
            self.send_error_payload("Content-Length is required.", HTTPStatus.BAD_REQUEST)
            return
        if length < 1 or length > MAX_REQUEST_BYTES:
            self.send_error_payload(
                "Request body is too large or empty.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            )
            return
        try:
            raw = json.loads(self.rfile.read(length).decode("utf-8"))
            config = validate_config(raw)
            save_config_and_templates(config)
            models = load_models()
            for role_name in ROLE_ORDER:
                model = config["roles"][role_name]["model"]
                if model not in models:
                    models.append(model)
            save_models(models)
        except (ConfigError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.send_error_payload(str(exc), HTTPStatus.BAD_REQUEST)
            return
        except OSError as exc:
            self.send_error_payload(
                f"Could not write plugin-local files: {exc.strerror or exc}.",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        self.send_json({"ok": True, **status_payload(config)})


def command_status(as_json: bool) -> int:
    try:
        payload = status_payload(load_config())
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("Sol Advisor local model-role map")
    for role_name in ROLE_ORDER:
        assignment = payload["config"]["roles"][role_name]
        print(f"- {role_name}: {assignment['model']} / {assignment['effort']}")
    print("Native templates:")
    for filename, current in payload["native_templates"].items():
        print(f"- {filename}: {'current' if current else 'out of date'}")
    print("Scope: files remain inside this plugin; no OpenCodex or Codex state is changed.")
    return 0


def command_get(role_name: str, as_json: bool) -> int:
    try:
        assignment = load_config()["roles"][role_name]
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps({"role": role_name, **assignment}, ensure_ascii=False))
    else:
        print(f"{role_name}: {assignment['model']} / {assignment['effort']}")
    return 0


def command_check() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    stale = [name for name, current in native_template_status(config).items() if not current]
    if stale:
        print(
            "ERROR: Native templates do not match config/role-map.json: " + ", ".join(stale),
            file=sys.stderr,
        )
        return 1
    print("CHECK PASSED: local role map and generated native templates match exactly.")
    return 0


def command_apply() -> int:
    try:
        config = load_config()
        write_native_templates(config)
    except (ConfigError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("APPLIED: regenerated native agent templates inside this plugin only.")
    return 0


def command_render() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = native_templates(config)
    for index, (path, content) in enumerate(rendered.items()):
        if index:
            print()
        print(f"--- {path.relative_to(PLUGIN_DIR).as_posix()} ---")
        print(content, end="")
    return 0


def command_serve(port: int) -> int:
    try:
        load_config()
        load_models()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    except OSError as exc:
        print(
            f"ERROR: could not start the loopback dashboard on 127.0.0.1:{port}: {exc}",
            file=sys.stderr,
        )
        return 1
    print(f"Sol Advisor dashboard: http://127.0.0.1:{port}/")
    print("Local-only: press Ctrl+C to stop. No browser, OpenCodex, or Codex process was started.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
    return 0


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage Sol Advisor's plugin-local model-role map without contacting OpenCodex."
    )
    subcommands = parser.add_subparsers(dest="command")

    serve = subcommands.add_parser("serve", help="serve the loopback-only web dashboard")
    serve.add_argument("--port", type=int, default=8765, help="loopback port to use (default: 8765)")

    status = subcommands.add_parser("status", help="show the current role map and template state")
    status.add_argument("--json", action="store_true", help="emit machine-readable local status")

    get = subcommands.add_parser("get", help="show one configured role assignment")
    get.add_argument("role", choices=ROLE_ORDER, help="role whose model and effort to show")
    get.add_argument("--json", action="store_true", help="emit machine-readable role data")

    subcommands.add_parser("apply", help="regenerate native templates inside this plugin only")
    subcommands.add_parser("check", help="fail unless native templates match the local role map")
    subcommands.add_parser("render", help="print the generated native templates without writing")

    if not argv:
        argv = ["serve"]
    arguments = parser.parse_args(argv)
    if arguments.command == "serve" and not 1024 <= arguments.port <= 65535:
        parser.error("--port must be between 1024 and 65535.")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(list(sys.argv[1:] if argv is None else argv))
    if arguments.command == "serve":
        return command_serve(arguments.port)
    if arguments.command == "status":
        return command_status(arguments.json)
    if arguments.command == "get":
        return command_get(arguments.role, arguments.json)
    if arguments.command == "apply":
        return command_apply()
    if arguments.command == "check":
        return command_check()
    if arguments.command == "render":
        return command_render()
    raise AssertionError(f"Unhandled command: {arguments.command}")


if __name__ == "__main__":
    raise SystemExit(main())
