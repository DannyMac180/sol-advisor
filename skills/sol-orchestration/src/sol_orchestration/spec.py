"""Assemble the child's prompt: its work, its boundary, and how it says it is finished.

The prompt is built from the spec's fields and the ownership set alone. Nothing is
read from the repository to produce it, which is what keeps the orchestrator's context
starved — it decomposes and judges, and never reads a project file.

**The child signals completion by writing a file, never by replying.** The host
delivers a child's last output straight to the parent and the spawn call offers no way
to suppress it, so a child that replies has written directly into the orchestrator's
only input, outside the evidence packet. That is the exact channel the trust boundary
exists to close, so the prompt closes it explicitly and the lifecycle never treats a
reply as completion.

Every prohibition below is **prompt text**. The kernel is a durable control
environment, not a security sandbox, and children run in the operator's own working
tree with the operator's own permissions. None of this is enforced. The ownership set
is an attribution and detection device, not a boundary: a child can write outside it,
and the evidence layer catches that afterwards rather than preventing it. The package
must never describe any of this as isolation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import config as config_module
from . import home
from .contract import Refusal

#: Directory under the Prime Agent home holding one completion signal per delegation.
#: It is deliberately not the config directory and not the episode store: the evidence
#: layer hashes those to detect tampering, and a path children are told to write would
#: blunt exactly that check.
SIGNAL_DIR_NAME = "signals"

#: Carried into every child prompt verbatim. Worded as instructions to the child, and
#: checked verbatim by a test so an edit here cannot silently weaken the boundary.
PROHIBITIONS: tuple[str, ...] = (
    "Do not commit, and do not stage anything for commit.",
    "Do not push, and do not create or update a pull request.",
    "Do not publish, release, or deploy anything.",
    "Do not read, copy, or transmit anything under the Prime Agent home, and do not "
    "read any credential, token, key, or session file anywhere on this machine.",
    "Do not make any network call that your declared verification command does not "
    "itself require.",
    "Do not reply to the parent session, and do not send it a message by any means. "
    "Your reply is not how this delegation is collected and will not be read as one.",
    "Do not modify, weaken, skip, or delete any test or assertion you were not "
    "explicitly asked to change, and do not edit the file your verification command "
    "runs against in order to make it pass.",
    "Do not touch files outside the ownership set below. You are not alone in this "
    "repository: preserve edits you did not make, and adapt to concurrent changes "
    "rather than reverting them.",
)


@dataclass(frozen=True)
class Spec:
    """One delegation, as the orchestrator declares it.

    ``verification_command`` is a **key** into the operator's declared command set,
    never a command line. Accepting free text here would let a spec name a command the
    operator never approved, which the kernel would then run with their permissions.
    """

    objective: str
    domain: str
    difficulty: str
    ownership: tuple[str, ...]
    verification_command: str
    interfaces: str = ""
    constraints: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)


def signal_dir() -> Path:
    """Return the directory holding completion signals under the Prime Agent home."""
    return home.agent_home() / config_module.CONFIG_DIR_NAME / SIGNAL_DIR_NAME


def signal_path(delegation_id: str) -> Path:
    """Return the one path a given delegation's child is permitted to write."""
    return signal_dir() / f"{delegation_id}.json"


def write_signal(delegation_id: str, payload: dict) -> Path:
    """Write a completion signal. Used by tests and by the unrecorded recovery discipline."""
    path = signal_path(delegation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def read_signal(delegation_id: str) -> dict | None:
    """Return the child's completion signal, or ``None`` when it has not written one.

    A malformed signal is not a completion. Treating unparsable child-authored bytes
    as "done" would let a child end its delegation by writing anything at all.
    """
    path = signal_path(delegation_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def clear_signal(delegation_id: str) -> None:
    """Remove a delegation's signal so the next delegation starts from nothing."""
    signal_path(delegation_id).unlink(missing_ok=True)


def resolve_verification_command(spec: Spec, declared: config_module.Config) -> tuple[str, ...]:
    """Resolve the spec's named command against the operator's declared set.

    Raises:
        Refusal: The spec named nothing, or named something the operator never declared.
    """
    if not spec.verification_command or not spec.verification_command.strip():
        raise Refusal(
            artifact="the delegation spec",
            remedy="name a verification command from the declared set; a delegation with nothing "
            "to verify makes ship a rubber stamp",
        )
    name = spec.verification_command.strip()
    if name not in declared.verification_commands:
        raise Refusal(
            artifact=str(declared.path),
            remedy=f"the spec named verification command {name!r}, which is not in the declared "
            f"set ({', '.join(sorted(declared.verification_commands))}); declare it there or "
            "name one that exists — free-text commands from a spec are never run",
        )
    return declared.verification_commands[name]


def assemble(spec: Spec, *, delegation_id: str, declared: config_module.Config) -> str:
    """Build the child's complete prompt.

    Args:
        spec: What the orchestrator declared for this delegation.
        delegation_id: Identifies the delegation and names its signal file.
        declared: The operator's config, which resolves the verification command.

    Returns:
        The prompt, deterministic for identical inputs.

    Raises:
        Refusal: The spec is missing a field this package will not guess.
    """
    if not spec.domain or not spec.domain.strip():
        raise Refusal(
            artifact="the delegation spec",
            remedy="declare a domain on the spec; it is a routing feature and the episode records "
            "it, so guessing it would record something that was never declared",
        )
    if not spec.difficulty or not spec.difficulty.strip():
        raise Refusal(
            artifact="the delegation spec",
            remedy="declare a difficulty on the spec; it is a routing feature and the episode "
            "records it, so guessing it would record something that was never declared",
        )
    if not spec.ownership:
        raise Refusal(
            artifact="the delegation spec",
            remedy="declare the ownership set: exactly the files this child may change. Without "
            "one there is nothing to compare the delta against, so no ownership verdict is "
            "possible and the delegation is not specified yet",
        )

    argv = resolve_verification_command(spec, declared)
    signal = signal_path(delegation_id)

    lines: list[str] = [
        "You are an implementation worker in a delegated build. You have inherited none",
        "of the orchestrator's context: everything you need is below.",
        "",
        "## Objective",
        "",
        spec.objective.strip(),
        "",
        "## The files you own",
        "",
        "You may change these files and no others:",
        "",
    ]
    lines.extend(f"- `{path}`" for path in spec.ownership)
    lines.append("")

    if spec.interfaces.strip():
        lines += ["## Interfaces", "", spec.interfaces.strip(), ""]
    if spec.constraints.strip():
        lines += ["## Constraints", "", spec.constraints.strip(), ""]
    if spec.notes:
        lines += ["## Notes", ""] + [f"- {note}" for note in spec.notes] + [""]

    lines += [
        "## How your work is checked",
        "",
        "This command is run for you, in the kernel, after you finish. Do not run it as",
        "a way of proving anything to anyone — run it as often as you like while working.",
        "",
        f"    {' '.join(argv)}",
        "",
        "## What you must not do",
        "",
    ]
    lines.extend(f"- {prohibition}" for prohibition in PROHIBITIONS)
    lines += [
        "",
        "None of the above is enforced by the environment. You are running in the",
        "operator's own working tree with their own permissions, so these are",
        "obligations you keep, not walls you will hit.",
        "",
        "## How to finish",
        "",
        "When you are done, write your completion signal to this exact path:",
        "",
        f"    {signal}",
        "",
        "It must be a JSON object with a `status` of `\"done\"` and a short `summary`",
        "of what you changed. For example:",
        "",
        '    {"status": "done", "summary": "added a bounded retry to fetch()"}',
        "",
        "That file is the only path under the Prime Agent home you may touch, and you",
        "may only write it — never read anything else there. Writing it is the only",
        "way to report completion. Do not reply to the parent; a reply is not collected,",
        "is not read as completion, and breaks the boundary this delegation depends on.",
    ]

    return "\n".join(lines) + "\n"
