"""One versioned record per delegation. This is the epic's deliverable.

Everything else in this package exists so a later plan can fit a routing policy
against real evidence instead of intuition. A record that is missing, collapsed, or
confounded cannot be backfilled — the delegation it described is gone.

Three properties are non-obvious and each was a defect in an earlier draft:

**Two-phase write.** :func:`open_record` is built before the spawn call and
:func:`close_record` at the terminal outcome. Building the record after the handle
returns loses a spawn that raises; writing only on completion loses every delegation
that crashed, hung, or was abandoned — the highest-information episodes in the set.

**Per-round outcomes, never one collapsed result.** A model that passes first try and
one that passes after three corrections must be distinguishable. That distinction is
the entire reason for collecting the data.

**Four confounder controls on every record.** The exact selector passed to the spawn,
the effort in force at that spawn, the child's effective effort after clamping, and
the size of the surviving allowlist the choice was made from. The operator can move
the effort dial mid-session at any time, so without these the corpus cannot separate
a model's contribution from the conditions it ran under.

Cost is read from the child's own session transcript, where every assistant message
carries a usage block with token counts and per-component cost. When it is unreadable
the record is written **without** the cost term and with a degradation recorded —
never an exception, and never a zero, because a zero reads as a free delegation.

Nothing here may call a model. A model-graded reward would make every training example
cost a model call and invert the economics this package exists to fix.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config as config_module
from . import home
from .contract import UNREADABLE_COST, Degradation

#: Stamped on the first record ever written. Records outlive the code that wrote them
#: and the consumer is a plan that does not exist yet, so the version rides on the
#: record rather than being inferred from when it was collected.
SCHEMA_VERSION = 1

#: The four verdicts a delegation may close with.
TERMINAL_OUTCOMES = ("ship", "fix-first", "rethink", "abandon")

STORE_FILE_NAME = "episodes.jsonl"


def store_path() -> Path:
    """Where episodes are appended: host-local, under the home, outside any repository."""
    return home.agent_home() / config_module.CONFIG_DIR_NAME / STORE_FILE_NAME


def transcript_path(session_id: str, session_dir: Path | str | None = None) -> Path:
    """The session transcript for a given session id.

    A **root** session's transcript lives in ``<home>/sessions/<id>.jsonl``. A **child's**
    does not: the runtime nests it under the parent's artifact directory, as
    ``<home>/session-artifacts/<parent-id>/sub-<child-id>/<child-session-id>.jsonl``.
    So a child's cost is only findable if the caller passes the ``session_dir`` the
    spawn handle or the subagent registry reported.

    Established by the live smoke run, which produced a real delegation whose cost was
    recorded as unreadable purely because this resolved to the root layout.
    """
    if session_dir is not None:
        return Path(session_dir) / f"{session_id}.jsonl"
    return home.agent_home() / "sessions" / f"{session_id}.jsonl"


@dataclass(frozen=True)
class RoundOutcome:
    """One correction round's deterministic result.

    Every field is observed by the kernel. Nothing here is a model's opinion.
    """

    round_index: int
    verification_exit_status: int | None
    verification_timed_out: bool
    ownership_violation: bool
    integrity_failure: bool
    empty_diff: bool
    wall_clock_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "verification_exit_status": self.verification_exit_status,
            "verification_timed_out": self.verification_timed_out,
            "ownership_violation": self.ownership_violation,
            "integrity_failure": self.integrity_failure,
            "empty_diff": self.empty_diff,
            "wall_clock_seconds": self.wall_clock_seconds,
        }


@dataclass(frozen=True)
class Usage:
    """What one child actually cost, summed from its own transcript."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_tokens: int
    cost_total: float


def _transcript_entries(session_id: str, session_dir: Path | str | None = None) -> list[dict] | None:
    path = transcript_path(session_id, session_dir)
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    entries: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # one corrupt line must not lose the rest
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def read_usage(
    session_id: str, session_dir: Path | str | None = None
) -> tuple[Usage | None, Degradation | None]:
    """Sum a child's own usage from its own transcript.

    Every assistant message carries a usage block with input, output, cache, total
    tokens and per-component cost. Reading the child's transcript directly avoids
    bracketing the parent's totals across a turn boundary, which would be noisy and
    would break the moment anything else happened in the same turn.

    Returns:
        The usage and ``None``, or ``None`` and the degradation explaining why not.
        Never raises, and never reports zero for an unreadable signal — a zero would
        read as a delegation that was free.
    """
    entries = _transcript_entries(session_id, session_dir)
    if entries is None:
        return None, Degradation(
            kind=UNREADABLE_COST,
            detail=f"no readable transcript at {transcript_path(session_id, session_dir)}",
        )

    totals = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0}
    cost_total = 0.0
    seen = False

    for entry in entries:
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        seen = True
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] += value
        cost = usage.get("cost")
        if isinstance(cost, dict) and isinstance(cost.get("total"), (int, float)):
            cost_total += float(cost["total"])

    if not seen:
        return None, Degradation(
            kind=UNREADABLE_COST,
            detail=f"the transcript at {transcript_path(session_id, session_dir)} carried no usage block",
        )

    return (
        Usage(
            input_tokens=totals["input"],
            output_tokens=totals["output"],
            cache_read_tokens=totals["cacheRead"],
            cache_write_tokens=totals["cacheWrite"],
            total_tokens=totals["totalTokens"] or (totals["input"] + totals["output"]),
            cost_total=cost_total,
        ),
        None,
    )


def read_clamped_effort(session_id: str, session_dir: Path | str | None = None) -> str | None:
    """Return the level a child actually ran at, from its own transcript.

    A child receives the parent's level clamped to what its own model supports, so
    this is not necessarily the level the parent was at when it spawned. Recording
    both is what stops the corpus attributing a clamp to the model's ability.
    """
    entries = _transcript_entries(session_id, session_dir)
    if entries is None:
        return None
    for entry in reversed(entries):
        if entry.get("type") == "thinking_level_change":
            level = entry.get("thinkingLevel")
            if isinstance(level, str):
                return level
    return None


def open_record(
    *,
    delegation_id: str,
    selector: str,
    surviving_size: int,
    domain: str,
    difficulty: str,
    ownership: tuple[str, ...],
    effort_at_spawn: str | None,
    child_name: str,
    restarted_from: str | None = None,
) -> dict[str, Any]:
    """Build the record's opening half. Called **before** the spawn, never after."""
    return {
        "schema_version": SCHEMA_VERSION,
        "delegation_id": delegation_id,
        "child_name": child_name,
        # The four confounder controls. Three of them are known now; the child's
        # clamped effort can only be read once the child has run, so it lands at close.
        "selector": selector,
        "effort_at_spawn": effort_at_spawn,
        "surviving_allowlist_size": surviving_size,
        # Routing features.
        "domain": domain,
        "difficulty": difficulty,
        "ownership": list(ownership),
        "restarted_from": restarted_from,
        "restarted_context": restarted_from is not None,
    }


def close_record(
    *,
    opened: dict[str, Any],
    outcome: str,
    rounds: tuple[RoundOutcome, ...],
    child_effort_clamped: str | None = None,
    usage: Usage | None = None,
    degradations: tuple[Degradation, ...] = (),
    child_session_id: str | None = None,
) -> dict[str, Any]:
    """Complete the record at the terminal outcome.

    Raises:
        ValueError: ``outcome`` is not one of the four terminal outcomes.
    """
    if outcome not in TERMINAL_OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(TERMINAL_OUTCOMES)}, got {outcome!r}")

    record = dict(opened)
    record["outcome"] = outcome
    record["child_effort_clamped"] = child_effort_clamped
    record["child_session_id"] = child_session_id
    record["rounds"] = [entry.as_dict() for entry in rounds]
    # Corrections are rounds after the first, so a first-try pass and a pass after
    # three corrections are different records rather than the same one.
    record["correction_count"] = max(0, len(rounds) - 1)
    record["wall_clock_seconds"] = sum(entry.wall_clock_seconds for entry in rounds)
    record["degradations"] = [entry.as_dict() for entry in degradations]

    if usage is not None:
        record["total_tokens"] = usage.total_tokens
        record["input_tokens"] = usage.input_tokens
        record["output_tokens"] = usage.output_tokens
        record["cache_read_tokens"] = usage.cache_read_tokens
        record["cache_write_tokens"] = usage.cache_write_tokens
        record["cost_total"] = usage.cost_total
    # When usage is None the cost keys are simply absent. A zero would be a lie: it
    # reads as a delegation that cost nothing rather than one nobody could price.

    return record


def append(record: dict[str, Any]) -> Path:
    """Append one record. Never rewrites and never truncates.

    Append-only is a convention here, not an enforced property: the store sits under
    the Prime Agent home and any child runs with the operator's permissions. The
    evidence layer's store-size assertion is the compensating check.
    """
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return path
