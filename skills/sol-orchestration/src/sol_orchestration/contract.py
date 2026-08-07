"""The two things this package says when reality does not match the plan.

A **refusal** stops a delegation and names the artifact the operator must change. It
is used where proceeding would spend money on work that cannot be corrected, or would
route around a declaration the operator made deliberately.

A **degradation** lets the delegation proceed and is carried into every packet and
every episode. It is used where the condition is real but not disqualifying — an
unreadable dial, a version this package has not been verified against. Recording it
is what stops the corpus attributing a result to a model when it was actually
produced under conditions nobody can see afterwards.

The split matters in both directions. A refusal where a degradation belongs freezes
the dataset on a routine patch bump; a degradation where a refusal belongs spends
quota on a child nothing can later correct.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The Python package failed to import; the skill runs from its written instructions.
PYTHON_LOAD_FAILED = "python-package-load-failed"
#: Per-child token cost could not be attributed; the outcome vector loses that term only.
UNREADABLE_COST = "unreadable-cost-attribution"
#: The session's reasoning effort could not be read from the transcript.
UNREADABLE_EFFORT = "unreadable-effort-level"
#: One or more declared allowlist entries did not survive the availability check.
ALLOWLIST_ENTRIES_DROPPED = "allowlist-entries-dropped"
#: The evidence packet exceeded its byte bound and was cut.
PACKET_TRUNCATED = "packet-truncated"
#: The spec named no verification command, so ``ship`` would rest on nothing.
NO_VERIFICATION_COMMAND = "spec-declares-no-verification-command"
#: Secret-shaped values were masked before output reached the packet or the record.
REDACTION_OCCURRED = "redaction-occurred"
#: A child neither completed nor reported within its bound.
CHILD_TIMEOUT = "child-timeout"
#: A spawn raised despite surviving preflight.
SPAWN_RAISED = "spawn-raised-after-preflight"
#: The runtime is not the version every contract in this package was verified against.
UNRECOGNIZED_RUNTIME_VERSION = "unrecognized-runtime-version"
#: Direct child messaging is unavailable; corrections open linked same-model restarts.
RESTART_ONLY_CORRECTIONS = "restart-only-corrections"

#: The closed vocabulary. Free-text kinds would make the corpus unqueryable one typo
#: at a time, and the corpus is this package's deliverable.
DEGRADATION_KINDS = frozenset(
    {
        PYTHON_LOAD_FAILED,
        UNREADABLE_COST,
        UNREADABLE_EFFORT,
        ALLOWLIST_ENTRIES_DROPPED,
        PACKET_TRUNCATED,
        NO_VERIFICATION_COMMAND,
        REDACTION_OCCURRED,
        CHILD_TIMEOUT,
        SPAWN_RAISED,
        UNRECOGNIZED_RUNTIME_VERSION,
        RESTART_ONLY_CORRECTIONS,
    }
)


class Refusal(Exception):
    """A delegation stopped before spending anything, with a way out.

    Args:
        artifact: What is wrong, named concretely enough to open — usually a path.
        remedy: What to change. A refusal without one is a dead end, not a refusal,
            so an empty remedy is a construction error rather than a runtime message.
    """

    def __init__(self, artifact: str, remedy: str) -> None:
        if not artifact or not artifact.strip():
            raise ValueError("a refusal must name the artifact that is wrong")
        if not remedy or not remedy.strip():
            raise ValueError("a refusal must name the remedy; a refusal without one is a dead end")
        self.artifact = artifact
        self.remedy = remedy
        super().__init__(f"{artifact}\n  fix: {remedy}")


@dataclass(frozen=True)
class Degradation:
    """One named condition in force, carried into the packet and the episode."""

    kind: str
    detail: str

    def __post_init__(self) -> None:
        if self.kind not in DEGRADATION_KINDS:
            raise ValueError(
                f"unknown degradation kind {self.kind!r}; add it to DEGRADATION_KINDS "
                "rather than passing free text, or the corpus cannot be queried on it"
            )

    def as_dict(self) -> dict[str, str]:
        """Return the stable two-field shape the packet and the episode both store."""
        return {"kind": self.kind, "detail": self.detail}
