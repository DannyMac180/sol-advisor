"""A fresh child that reads the actual changed files, on the operator's declared model.

This is the one place in the design where a model *should* read code. The orchestrator
is starved by construction and never opens a file, and the context that wrote the spec
is a weak judge of the result it asked for. Reading files is the expensive-by-volume
job, which is exactly why it belongs on the cheap tier rather than the expensive one.

Three properties keep it honest:

**It runs on the operator-declared review entry, never an inferred cheapest.** The
allowlist is a list of bare selectors carrying no price field, so "cheapest" has no
meaning against it and any inference would be the package inventing a preference the
operator never expressed.

**Its findings are evidence, not a verdict.** Acceptance belongs to the orchestrator.
A reviewer that returned `ship` would have taken the one decision the whole design
reserves for the expensive tier.

**Its read-only posture is a prompt, not enforced isolation.** The kernel is a durable
control environment, not a sandbox, and this child runs with the operator's
permissions like every other. The package reports it as prompt-constrained and must
never describe it as anything stronger.

Losing the review must not lose the delegation. A review child that never reports
degrades to a packet without findings rather than blocking, because the review is
evidence and evidence can be missing.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config as config_module
from . import home
from . import host as host_module
from .contract import CHILD_TIMEOUT, SPAWN_RAISED, Degradation

#: Directory holding one findings file per reviewed delegation.
FINDINGS_DIR_NAME = "reviews"

#: How the package describes the review child's posture. Never anything stronger.
PROMPT_CONSTRAINED = "prompt-constrained: the review child is asked not to edit, and nothing enforces it"

DEFAULT_REVIEW_BOUND_SECONDS = 600.0
DEFAULT_POLL_SECONDS = 5.0


class _RealClock:
    def time(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


def findings_dir() -> Path:
    return home.agent_home() / config_module.CONFIG_DIR_NAME / FINDINGS_DIR_NAME


def findings_path(delegation_id: str) -> Path:
    """The one path the review child is asked to write."""
    return findings_dir() / f"{delegation_id}.json"


def write_findings(delegation_id: str, payload: dict[str, Any]) -> Path:
    """Write a findings file. Used by tests and by the unrecorded recovery discipline."""
    path = findings_path(delegation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def read_findings(delegation_id: str) -> tuple[str, ...]:
    """Return the child's findings. Unparsable child-authored bytes are no findings.

    Nothing here is trusted. The findings are strings written by a cheap model and
    they enter the packet inside its untrusted region; treating malformed bytes as
    anything at all would give a child a way to influence the packet by writing junk.
    """
    path = findings_path(delegation_id)
    if not path.exists():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict):
        return ()
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return ()
    return tuple(str(entry) for entry in findings if isinstance(entry, (str, int, float)))


@dataclass(frozen=True)
class ReviewResult:
    """What the review produced, and under what conditions.

    There is deliberately no ``verdict`` field. Acceptance belongs to the orchestrator.
    """

    findings: tuple[str, ...]
    posture: str
    trusted: bool
    timed_out: bool
    selector: str | None
    degradations: tuple[Degradation, ...]


def child_name_for(delegation_id: str) -> str:
    """Name the review child distinctly from the implementation child it reviews."""
    return f"sol-review-{delegation_id}"[: host_module.CHILD_NAME_MAX_LENGTH]


def assemble_prompt(
    *, delegation_id: str, changed_paths: tuple[str, ...], objective: str, diff_summary: str = ""
) -> str:
    """Build the review child's prompt: read these files, report what you find."""
    lines = [
        "You are a reviewer. A previous worker changed the files listed below in an",
        "existing repository. Read them as they now stand and report what you find.",
        "",
        "## What the worker was asked to do",
        "",
        objective.strip(),
        "",
        "## Files that changed",
        "",
    ]
    lines.extend(f"- `{path}`" for path in changed_paths)
    if diff_summary.strip():
        lines += ["", "## Summary of the change", "", diff_summary.strip()]
    lines += [
        "",
        "## What to look for",
        "",
        "- Work that appears finished but is stubbed, hollowed out, or unimplemented.",
        "- Assertions weakened or removed, tests skipped, deleted, or made vacuous.",
        "- Changes outside what the objective needed.",
        "- Anything that would pass a test run and still be wrong.",
        "",
        "## What you must not do",
        "",
        "- Do not edit, create, delete, or move any file. Read only.",
        "- Do not run any command that changes anything.",
        "- Do not decide whether this work is accepted. That decision is not yours;",
        "  report what you observed and let it be weighed.",
        "- Do not reply to the parent session. Your reply is not collected.",
        "",
        "Nothing above is enforced by the environment. You are running with the",
        "operator's own permissions, so these are obligations you keep.",
        "",
        "## How to finish",
        "",
        "Write your findings to this exact path:",
        "",
        f"    {findings_path(delegation_id)}",
        "",
        'It must be a JSON object of the form {"findings": ["...", "..."]}, each entry',
        "one observation in one sentence. An empty list is a legitimate result. That",
        "file is the only path you may write, and writing it is the only way to report.",
    ]
    return "\n".join(lines) + "\n"


async def request(
    *,
    declared: config_module.Config,
    delegation_id: str,
    changed_paths: tuple[str, ...],
    objective: str,
    diff_summary: str = "",
    host: host_module.Host | None = None,
    clock: Any | None = None,
    bound_seconds: float = DEFAULT_REVIEW_BOUND_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
) -> ReviewResult:
    """Dispatch the review child and wait, bounded, for its findings file.

    Dispatched directly through the adapter rather than through the delegation
    lifecycle: going through dispatch would open a second episode record, and the
    contract is one episode per implementation delegation. The review is evidence
    inside that delegation, not a delegation of its own.

    Returns:
        The findings and the conditions they were produced under. Never raises for a
        review that failed — a missing review degrades the packet, it does not lose
        the delegation.
    """
    host = host or host_module.current()
    clock = clock or _RealClock()
    degradations: list[Degradation] = []
    selector = declared.review_model
    name = child_name_for(delegation_id)

    prompt = assemble_prompt(
        delegation_id=delegation_id,
        changed_paths=changed_paths,
        objective=objective,
        diff_summary=diff_summary,
    )

    try:
        await host.spawn(prompt, name=name, selector=selector)
    except Exception as error:
        degradations.append(
            Degradation(
                kind=SPAWN_RAISED,
                detail=f"the review child did not start: {type(error).__name__}: {error}",
            )
        )
        return ReviewResult(
            findings=(),
            posture=PROMPT_CONSTRAINED,
            trusted=False,
            timed_out=False,
            selector=selector,
            degradations=tuple(degradations),
        )

    started = clock.time()
    while True:
        findings = read_findings(delegation_id)
        if findings or findings_path(delegation_id).exists():
            return ReviewResult(
                findings=findings,
                posture=PROMPT_CONSTRAINED,
                trusted=False,
                timed_out=False,
                selector=selector,
                degradations=tuple(degradations),
            )
        elapsed = clock.time() - started
        if elapsed >= bound_seconds:
            break
        await clock.sleep(min(poll_seconds, bound_seconds - elapsed))

    degradations.append(
        Degradation(
            kind=CHILD_TIMEOUT,
            detail=f"the review child reported nothing within {bound_seconds:g}s; the packet "
            "carries no findings and the delegation continues",
        )
    )
    try:
        await host.delete_subagent(name)
    except Exception:
        pass  # a failed teardown must not turn a degraded review into a lost delegation

    return ReviewResult(
        findings=(),
        posture=PROMPT_CONSTRAINED,
        trusted=False,
        timed_out=True,
        selector=selector,
        degradations=tuple(degradations),
    )
