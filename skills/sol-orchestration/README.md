# sol-orchestration

Cost-routed delegation for Prime Agent.

An expensive orchestrator decomposes work and judges results but **never reads a project
file**. Implementation goes to cheaper models drawn from an allowlist you declare. Every
deterministic check — the diff, the ownership comparison, the verification command, the
adversarial signals — runs inside the persistent IPython kernel at zero token cost. Each
delegation appends one **episode record**, so which model was worth spending on which
kind of job can later be fitted to evidence instead of intuition.

That corpus is the point. Everything else exists to produce it honestly.

## Two faces

| File | Audience |
|---|---|
| [`SKILL.md`](SKILL.md) | The workflow contract plus an explicitly unrecorded recovery discipline. |
| `src/sol_orchestration/` | The authoritative recorded lifecycle and its deterministic callables. |

A failed Python load is reported rather than hidden. Raw recovery may preserve the
ownership and acceptance rules, but it cannot reproduce the episode ledger or cost
attribution and must never be reported as a valid package episode.

## Before first use

Declare an allowlist. The package ships **no default model anywhere**:

`~/.prime/agent/sol-orchestration/config.json`

```json
{
  "allowlist": ["provider-a/model-one", "provider-a/model-two"],
  "review_model": "provider-a/model-two",
  "verification_commands": { "unit": ["python", "-m", "pytest", "-q"] },
  "routing_prior": {
    "default": "provider-a/model-one",
    "rules": [{ "domain": "python", "difficulty": "hard", "model": "provider-a/model-two" }]
  }
}
```

## Development

```sh
uv run --with pytest python -m pytest -q
uv run --python 3.14 --with pytest python -m pytest -q -W error
uv run --python 3.11 --with pytest python -m pytest -q -W error
sh ../../scripts/verify-prime-agent-package.sh
```

Every module imports outside a kernel — that is a tested property, not an accident. The
bundled runtime is imported lazily inside calls because it ships with Prime Agent rather
than on PyPI, and the skill contract forbids declaring it as a dependency.

## What is not enforced

The kernel is a durable control environment, not a security sandbox. Children run in
your working tree with your permissions. Every child constraint is prompt text. The
ownership set is an attribution and detection device, not a boundary — a child can write
outside it, and the evidence layer catches that afterwards rather than preventing it. A
detected violation is reported, never reverted.
