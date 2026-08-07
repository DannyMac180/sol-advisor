"""Dispatch, collect, correct, cancel — the whole delegation path, none of it live.

The spawn is asynchronous. It returns an admission handle and never the child's
answer, so dispatch and collection are separate orchestrator turns and something has
to survive between them. That is the ledger, and it is why a delegation that crashes,
hangs, or is abandoned still leaves a record instead of vanishing — those are the
highest-information episodes in the corpus, and a design that only writes on success
loses exactly them.

Ordering inside dispatch is a correctness requirement: **snapshot, then open the
record, then spawn.** A record opened after the handle returns loses every spawn that
raised. A snapshot taken after the spawn races the child.

Nothing here spends model quota when it runs against a double, and nothing here can
reach the host except through the adapter.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol

from . import config as config_module
from . import host as host_module
from . import spec as spec_module
from .contract import (
    CHILD_TIMEOUT,
    RESTART_ONLY_CORRECTIONS,
    SPAWN_RAISED,
    Degradation,
    Refusal,
)

#: The verdicts a delegation boundary may close with.
BOUNDARY_OUTCOMES = ("ship", "fix-first", "rethink", "abandon")

#: How many corrections one delegation may receive before ``rethink`` is forced.
#: A package constant rather than operator configuration: the cap exists to stop a
#: loop, and a stop an operator can raise is not a stop.
FIX_FIRST_CAP = 3

#: Default bound on collection, in seconds.
DEFAULT_COLLECTION_BOUND_SECONDS = 900.0

#: How often collection re-checks the signal and the registry.
DEFAULT_POLL_SECONDS = 5.0

#: Child session names are prefixed so they are recognisable in the registry.
CHILD_NAME_PREFIX = "sol-"


class Snapshotter(Protocol):
    """Captures the pre-spawn repository state. Implemented by the evidence layer."""

    def capture(self) -> Any | None: ...


class Recorder(Protocol):
    """Two-phase episode writer. Implemented by the episode store."""

    def open(self, delegation_id: str, record: dict[str, Any]) -> None: ...

    def close(self, delegation_id: str, outcome: str, detail: dict[str, Any]) -> None: ...


class Clock(Protocol):
    """Time, injected so a bound can be proven without waiting for one."""

    def time(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class _RealClock:
    def time(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


@dataclass
class Delegation:
    """One delegation's mutable state between dispatch and its terminal outcome."""

    delegation_id: str
    child_name: str
    selector: str
    spec: spec_module.Spec
    surviving_size: int
    snapshot: Any = None
    handle: host_module.SpawnHandle | None = None
    correction_count: int = 0
    restarted_from: str | None = None
    outcome: str | None = None
    degradations: list[Degradation] = field(default_factory=list)


@dataclass(frozen=True)
class Collection:
    """The result of one bounded wait."""

    completed: bool
    timed_out: bool
    child_errored: bool
    signal: dict[str, Any] | None
    waited_seconds: float


@dataclass(frozen=True)
class CorrectionResult:
    """What happened to one correction attempt."""

    delivered: bool
    restarted: bool
    forced_rethink: bool
    delegation: Delegation | None = None


class Lifecycle:
    """Owns every host interaction a delegation makes.

    Args:
        declared: The operator's config, which resolves verification commands.
        host: The host to talk to; the injected or live one when omitted.
        recorder: Two-phase episode writer.
        snapshotter: Captures the pre-spawn repository state.
        clock: Time source, injected so bounds are testable.
        ids: Delegation ids; UUID-backed when omitted.
    """

    def __init__(
        self,
        *,
        declared: config_module.Config,
        recorder: Recorder,
        snapshotter: Snapshotter,
        host: host_module.Host | None = None,
        clock: Clock | None = None,
        ids: Iterator[str] | None = None,
    ) -> None:
        self.declared = declared
        self.recorder = recorder
        self.snapshotter = snapshotter
        self.host = host or host_module.current()
        self.clock = clock or _RealClock()
        self._ids = ids

    def _next_id(self) -> str:
        if self._ids is not None:
            return next(self._ids)
        return f"d-{uuid.uuid4().hex[:12]}"

    @staticmethod
    def child_name_for(delegation_id: str) -> str:
        """Name a child after its delegation, so the two are never confused."""
        name = f"{CHILD_NAME_PREFIX}{delegation_id}"
        return name[: host_module.CHILD_NAME_MAX_LENGTH]

    async def dispatch(
        self,
        spec: spec_module.Spec,
        *,
        selector: str | None,
        surviving: tuple[str, ...],
        restarted_from: str | None = None,
    ) -> Delegation:
        """Spawn one child and return immediately with its handle.

        Raises:
            Refusal: No routed selector, a selector that did not survive preflight, or
                no pre-spawn snapshot.
        """
        if not selector or not str(selector).strip():
            raise Refusal(
                artifact="this delegation's routing",
                remedy="route the delegation with routing.select before dispatching it; a spawn "
                "with no selector inherits the parent's model, which is the expensive "
                "orchestrator, and would pass every gate while doing it",
            )
        if selector not in surviving:
            raise Refusal(
                artifact="this delegation's routing",
                remedy=f"selector {selector!r} is not in the surviving allowlist "
                f"({', '.join(surviving) or 'empty'}); re-run preflight and route again rather "
                "than dispatching a selector nothing verified",
            )

        # Snapshot first. A shared working tree carries operator edits and the previous
        # delegation's accepted work, so a snapshot taken after the spawn races the child
        # and a HEAD-relative diff would attribute both to this delegation.
        snapshot = self.snapshotter.capture()
        if snapshot is None:
            raise Refusal(
                artifact="the pre-spawn repository snapshot",
                remedy="capture a snapshot before dispatching; without a baseline there is nothing "
                "to compute this delegation's delta against, so no ownership verdict is possible",
            )

        delegation_id = self._next_id()
        prompt = spec_module.assemble(spec, delegation_id=delegation_id, declared=self.declared)

        delegation = Delegation(
            delegation_id=delegation_id,
            child_name=self.child_name_for(delegation_id),
            selector=selector,
            spec=spec,
            surviving_size=len(surviving),
            snapshot=snapshot,
            restarted_from=restarted_from,
        )

        # Open the record before the host call, never after the handle returns: a spawn
        # that raises must still close a record rather than leaving the failure unlogged.
        self.recorder.open(
            delegation_id,
            {
                "delegation_id": delegation_id,
                "selector": selector,
                "surviving_size": len(surviving),
                "domain": spec.domain,
                "difficulty": spec.difficulty,
                "ownership": list(spec.ownership),
                "child_name": delegation.child_name,
                "restarted_from": restarted_from,
                "restarted_context": restarted_from is not None,
            },
        )

        try:
            delegation.handle = await self.host.spawn(
                prompt, name=delegation.child_name, selector=selector
            )
        except Exception as error:
            delegation.degradations.append(
                Degradation(kind=SPAWN_RAISED, detail=f"{type(error).__name__}: {error}")
            )
            await self.close(delegation, "abandon")
            raise

        return delegation

    async def collect(
        self,
        delegation: Delegation,
        *,
        bound_seconds: float = DEFAULT_COLLECTION_BOUND_SECONDS,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
    ) -> Collection:
        """Wait, bounded, for the child's file signal.

        Completion is read from the signal file and from nothing else. The host
        delivers the child's last output to the parent whatever this does, so treating
        a reply as completion would accept the one channel the boundary exists to close.

        A child that never reports within the bound is cancelled and closed as
        ``abandon``, with its record written.
        """
        started = self.clock.time()

        while True:
            signal = spec_module.read_signal(delegation.delegation_id)
            if signal is not None:
                return Collection(
                    completed=True,
                    timed_out=False,
                    child_errored=False,
                    signal=signal,
                    waited_seconds=self.clock.time() - started,
                )

            if await self._child_errored(delegation):
                return Collection(
                    completed=False,
                    timed_out=False,
                    child_errored=True,
                    signal=None,
                    waited_seconds=self.clock.time() - started,
                )

            elapsed = self.clock.time() - started
            if elapsed >= bound_seconds:
                break
            await self.clock.sleep(min(poll_seconds, bound_seconds - elapsed))

        waited = self.clock.time() - started
        delegation.degradations.append(
            Degradation(
                kind=CHILD_TIMEOUT,
                detail=f"no completion signal within {bound_seconds:g}s; child cancelled",
            )
        )
        await self._teardown(delegation)
        await self.close(delegation, "abandon")
        return Collection(
            completed=False, timed_out=True, child_errored=False, signal=None, waited_seconds=waited
        )

    async def _child_errored(self, delegation: Delegation) -> bool:
        """Report whether the host has already failed this child."""
        try:
            registry = await self.host.list_subagents()
        except Exception:
            return False  # an unreadable registry is not evidence the child failed
        for entry in registry:
            if entry.session_name == delegation.child_name:
                return entry.status == "error"
        return False

    async def correct(self, delegation: Delegation, message: str) -> CorrectionResult:
        """Deliver a correction to the same retained child, or restart on the same model.

        A correction can only reach a child that is still retained and addressable.
        When it is gone the correction opens a **new linked delegation id** on the same
        model, marked restarted-context — and the original's correction count does not
        move, because a restarted context is not another round against the same child.
        """
        if delegation.correction_count >= FIX_FIRST_CAP:
            return CorrectionResult(delivered=False, restarted=False, forced_rethink=True)

        restart_reason = "the child is not retained or addressable"
        if await self._child_is_addressable(delegation):
            try:
                await self.host.send_message(
                    message, receiver_role="child", receiver_name=delegation.child_name
                )
            except Exception as error:
                restart_reason = (
                    f"direct correction failed ({type(error).__name__}); "
                    "host error text omitted from the persistent corpus"
                )
            else:
                delegation.correction_count += 1
                return CorrectionResult(delivered=True, restarted=False, forced_rethink=False)

        if not any(entry.kind == RESTART_ONLY_CORRECTIONS for entry in delegation.degradations):
            delegation.degradations.append(
                Degradation(
                    kind=RESTART_ONLY_CORRECTIONS,
                    detail=restart_reason + " — correction restarted on the same model",
                )
            )

        restarted = await self.dispatch(
            delegation.spec,
            selector=delegation.selector,
            surviving=(delegation.selector,),
            restarted_from=delegation.delegation_id,
        )
        return CorrectionResult(
            delivered=False, restarted=True, forced_rethink=False, delegation=restarted
        )

    async def _child_is_addressable(self, delegation: Delegation) -> bool:
        """Report whether this child is still retained and reachable by name."""
        try:
            registry = await self.host.list_subagents()
        except Exception:
            return False
        for entry in registry:
            if entry.session_name == delegation.child_name:
                return bool(entry.active_session_id)
        return False

    async def _teardown(self, delegation: Delegation) -> None:
        """Cancel a child. Best effort: a failed teardown must not lose the record."""
        target = delegation.handle.child_id if delegation.handle else delegation.child_name
        try:
            await self.host.delete_subagent(target)
        except Exception:
            pass

    async def close(
        self, delegation: Delegation, outcome: str, detail: dict[str, Any] | None = None
    ) -> None:
        """Close the delegation's record with exactly one terminal outcome.

        Args:
            delegation: The delegation to close.
            outcome: One of the four terminal outcomes.
            detail: Anything the caller learned that the lifecycle cannot observe —
                the child's usage, its clamped effort, its session id. The lifecycle
                deliberately does not read transcripts itself, but without a way to
                pass what the caller read, the cost term never reaches the record and
                every episode in the corpus loses it.

        Idempotent: a delegation the lifecycle already closed as ``abandon`` must not
        get a second record when the orchestrator later returns a verdict for it.
        """
        if outcome not in BOUNDARY_OUTCOMES:
            raise ValueError(
                f"outcome must be one of {', '.join(BOUNDARY_OUTCOMES)}, got {outcome!r}"
            )
        if delegation.outcome is not None:
            return
        delegation.outcome = outcome
        payload: dict[str, Any] = {
            "selector": delegation.selector,
            "correction_count": delegation.correction_count,
            "surviving_size": delegation.surviving_size,
            "restarted_from": delegation.restarted_from,
            "degradations": [entry.as_dict() for entry in delegation.degradations],
        }
        if detail:
            merged = list(payload["degradations"]) + list(detail.get("degradations", ()))
            payload.update(detail)
            payload["degradations"] = merged
        self.recorder.close(delegation.delegation_id, outcome, payload)
        spec_module.clear_signal(delegation.delegation_id)
