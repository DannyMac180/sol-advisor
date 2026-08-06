# Sol Advisor

**Sol / High runs the show. It declares a risk-gated route before task tools, keeps
solo as the default, and uses a single auxiliary only when that improves delivery.**

Sol Advisor is a Codex-only workflow for capability-routed software delivery. You
bring the goal and constraints; Sol owns the plan, implementation or delegation,
verification, and acceptance.

## Go deeper

I write [**Attention Heads**](https://attentionheads.substack.com/?utm_source=github&utm_medium=readme&utm_campaign=sol-advisor) — deep, evidence-backed writing on AI, cognition, and agentic engineering. The **Agentic Engineering Field Notes** series is where I publish practical advice on the craft of using AI. [Subscribe](https://attentionheads.substack.com/subscribe?utm_source=github&utm_medium=readme&utm_campaign=sol-advisor) to get new posts to your inbox.

## Quick start

You need a current Codex CLI or ChatGPT desktop app with plugins enabled, GPT-5.6
Sol / High for the primary session, native custom-agent support, and jq. GPT-5.6
Luna / Max or Terra / High access is needed only when the selected route delegates.
A routed DeepSeek V4 Flash / High capability is optional for delegated work.

~~~sh
codex plugin marketplace add DannyMac180/sol-advisor --ref main
codex plugin add sol-advisor@sol-advisor
plugin_dir="$(codex plugin list --json | jq -r '.installed[] | select(.pluginId == "sol-advisor@sol-advisor") | .source.path')" && test -n "$plugin_dir" && test "$plugin_dir" != null && test -d "$plugin_dir" && test -f "$plugin_dir/scripts/install-agents.sh" && sh "$plugin_dir/scripts/install-agents.sh"
~~~

The companion installer verifies all four exact role files after installation. It is
fail-closed: modified, unsafe, nonregular, symlinked, unknown, or differing files
are left untouched. It does not edit Codex configuration. Start a fresh Codex task
after installation so native roles are discovered.

Use this one prompt in the new task:

~~~text
Use $sol-advisor:orchestration to build this feature and verify it. Declare the selective route before task tools.
~~~

## What you do

Give Sol the outcome, constraints, and any important repository context. You do not
need to select or manage a lane; Sol records the route and owns verification and
acceptance.

## Routes

| Mode | Use it when | Delivery |
|---|---|---|
| `solo` | Default; risk is contained. | Root plans, implements, tests, and self-reviews. |
| `delegate` | A complete spec is better executed by one implementer. | Routed DeepSeek V4 Flash / High when verified, Luna / Max for bounded work, or Terra / High for judgment-heavy or high-risk work; root verifies. |
| `audit` | Independent final scrutiny matters more than delegation. | Root implements; a fresh read-only Sol / High reviews. |
| `full` | Explicit broad or high-risk exception. | One selected implementer, root verification, and a fresh Sol / High review. |

Solo is the default. One auxiliary is the default maximum; `full` is the explicit
exception. Sol emits a `SELECTIVE ROUTE` declaration with the mode and concise risk
rationale before the first task tool call. It can escalate only when newly observed
risk justifies it and never silently downgrades.

DeepSeek is capability-gated and uses `deepseek/deepseek-v4-flash` at high reasoning.
An explicit DeepSeek request stops when the exact role, model, effort, or provider route cannot be verified. When DeepSeek is selected
automatically, only a clear failure before worker work begins may be reported before
selecting Terra; that fallback must never be described as a DeepSeek run.

## What happens automatically

Sol / High keeps architecture, decomposition, route selection, parent verification,
escalation decisions, and acceptance in the primary task. Auxiliary work substitutes
for root work; it does not duplicate it. The root inspects the complete diff and
reruns the requested checks. When the selected route includes a review, a fresh Sol /
High reviewer returns ship, fix-first, or rethink; any fix requires a new review.

## Updating

Update the marketplace plugin, reinstall the companion roles, and start a new task:

~~~sh
codex plugin marketplace upgrade sol-advisor
codex plugin add sol-advisor@sol-advisor
plugin_dir="$(codex plugin list --json | jq -r '.installed[] | select(.pluginId == "sol-advisor@sol-advisor") | .source.path')" && test -n "$plugin_dir" && test "$plugin_dir" != null && test -d "$plugin_dir" && test -f "$plugin_dir/scripts/install-agents.sh" && sh "$plugin_dir/scripts/install-agents.sh"
~~~

For exact spawn, runtime-evidence, sandbox, installer, and maintainer verification
details, read [advanced native operations](plugins/sol-advisor/skills/orchestration/references/operations.md).
For local development, install this checkout as a marketplace:

~~~sh
cd /absolute/path/to/sol-advisor
codex plugin marketplace add /absolute/path/to/sol-advisor
codex plugin add sol-advisor@sol-advisor
~~~
