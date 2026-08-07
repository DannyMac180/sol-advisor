"""What survives between dispatch and collection, and across a lost orchestrator turn.

The spawn is asynchronous and the orchestrator's memory does not survive compaction.
Without something on disk between the two, a delegation that crashed, hung, or was
abandoned leaves nothing at all — and those are the highest-information episodes in
the corpus, so a design that only writes on success loses exactly them.

The ledger is an **append-only event log**, not a mutable open-delegations file.
Reconstruction replays it: an open with no matching close is still open. A crash
mid-write therefore costs one truncated line rather than the whole state, and a
truncated line is skipped rather than fatal.

**Reconstruction is ledger-only.** Reconciling against live child sessions is
deliberately out of scope: it depends on a runtime path this epic never read, and the
requirement asks only that a lost session keep its open record. A test reads this
module's own source to keep that true.

:class:`Ledger` implements the recorder protocol the delegation lifecycle already
expects, so nothing in that path changes. Per-round outcomes arrive through
:meth:`record_round`, called by the evidence path, rather than by widening a protocol
the lifecycle was built against.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config as config_module
from . import episodes as episodes_module
from . import home
from .contract import Degradation

LEDGER_FILE_NAME = "ledger.jsonl"

#: Degradations observed at open time, carried on the open record until the close
#: merges them. Stripped before the record is written.
PENDING_DEGRADATIONS_KEY = "_pending_degradations"

#: Distinguishes "the caller passed no effort" from "the caller passed None".
_MISSING = object()


def ledger_path() -> Path:
    """Where open delegations are journalled, beside the episode store."""
    return home.agent_home() / config_module.CONFIG_DIR_NAME / LEDGER_FILE_NAME


@dataclass
class OpenDelegation:
    """One delegation the ledger says is still open, reconstructed from the log alone."""

    delegation_id: str
    record: dict[str, Any]
    rounds: list[episodes_module.RoundOutcome] = field(default_factory=list)


class Ledger:
    """Two-phase episode writer: open before the spawn, close at the terminal outcome."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or ledger_path()

    # --- the recorder protocol the lifecycle expects ---------------------------

    def open(self, delegation_id: str, record: dict[str, Any]) -> None:
        """Journal the opening half. Called before the host spawn, never after it.

        The delegation lifecycle passes the fields *it* knows about, which is not the
        record schema — it was written against a protocol, not against this file. So
        this is where the two are reconciled: whatever arrives is normalised into a
        properly versioned open record before it is journalled. Storing the lifecycle's
        own dict verbatim would put records in the corpus with no schema version and no
        effort confounder, and nothing downstream could tell why.
        """
        self._emit(
            {
                "event": "open",
                "delegation_id": delegation_id,
                "record": self._normalise(delegation_id, record),
            }
        )

    @staticmethod
    def _normalise(delegation_id: str, record: dict[str, Any]) -> dict[str, Any]:
        """Turn whatever the caller passed into a versioned open record."""
        if record.get("schema_version") == episodes_module.SCHEMA_VERSION:
            return record

        pending: list[dict[str, str]] = []
        effort = record.get("effort_at_spawn", _MISSING)
        if effort is _MISSING:
            # Read now rather than earlier. The operator can move the dial mid-session,
            # so a level captured before dispatch would record a condition that was not
            # in force at the spawn — the exact confounder this field exists to remove.
            from . import preflight

            effort, degradation = preflight.current_effort_reporting()
            if degradation is not None:
                # Carried to the close so the record says *why* the effort is absent. A
                # null with no stated reason reads as a fact rather than as an absence.
                pending.append(degradation.as_dict())

        opened = episodes_module.open_record(
            delegation_id=record.get("delegation_id") or delegation_id,
            selector=record.get("selector") or "",
            surviving_size=int(
                record.get("surviving_size") or record.get("surviving_allowlist_size") or 0
            ),
            domain=record.get("domain") or "",
            difficulty=record.get("difficulty") or "",
            ownership=tuple(record.get("ownership") or ()),
            effort_at_spawn=effort,
            child_name=record.get("child_name") or "",
            restarted_from=record.get("restarted_from"),
        )
        if pending:
            opened[PENDING_DEGRADATIONS_KEY] = pending
        return opened

    def close(self, delegation_id: str, outcome: str, detail: dict[str, Any]) -> None:
        """Append exactly one episode for this delegation, and close it in the ledger.

        Idempotent by construction: a delegation the ledger no longer lists as open has
        already been closed, and closing it again writes nothing.

        Raises:
            KeyError: The delegation was never opened. Writing a record with no spawn
                behind it would put a delegation in the corpus that never happened.
        """
        state = self._state()
        if delegation_id not in state:
            if self._was_closed(delegation_id):
                return
            raise KeyError(
                f"delegation {delegation_id!r} was never opened; a record with no spawn behind it "
                "would put a delegation in the corpus that never happened"
            )

        entry = state[delegation_id]
        opened_record = dict(entry.record)
        carried = opened_record.pop(PENDING_DEGRADATIONS_KEY, [])
        degradations = tuple(
            Degradation(kind=item["kind"], detail=item.get("detail", ""))
            for item in list(carried) + list(detail.get("degradations", ()))
            if isinstance(item, dict) and "kind" in item
        )

        record = episodes_module.close_record(
            opened=opened_record,
            outcome=outcome,
            rounds=tuple(entry.rounds),
            child_effort_clamped=detail.get("child_effort_clamped"),
            usage=detail.get("usage"),
            degradations=degradations,
            child_session_id=detail.get("child_session_id"),
        )
        episodes_module.append(record)
        self._emit({"event": "close", "delegation_id": delegation_id, "outcome": outcome})

    # --- per-round accumulation ------------------------------------------------

    def record_round(self, delegation_id: str, outcome: episodes_module.RoundOutcome) -> None:
        """Journal one correction round's deterministic result."""
        self._emit(
            {"event": "round", "delegation_id": delegation_id, "round": outcome.as_dict()}
        )

    # --- reconstruction --------------------------------------------------------

    def open_delegations(self) -> tuple[OpenDelegation, ...]:
        """Rebuild every still-open delegation from the ledger alone.

        A fresh orchestrator turn with no in-memory state can call this and see what a
        lost session left behind, then close it.
        """
        return tuple(self._state().values())

    # --- internals -------------------------------------------------------------

    def _emit(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def _events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            return []
        events: list[dict[str, Any]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # a crash mid-write costs one line, not the reconstruction
            if isinstance(event, dict) and "event" in event and "delegation_id" in event:
                events.append(event)
        return events

    def _state(self) -> dict[str, OpenDelegation]:
        """Replay the log: an open with no matching close is still open."""
        state: dict[str, OpenDelegation] = {}
        for event in self._events():
            delegation_id = event["delegation_id"]
            kind = event["event"]
            if kind == "open" and isinstance(event.get("record"), dict):
                state[delegation_id] = OpenDelegation(
                    delegation_id=delegation_id, record=event["record"]
                )
            elif kind == "round" and delegation_id in state:
                payload = event.get("round")
                if isinstance(payload, dict):
                    try:
                        state[delegation_id].rounds.append(
                            episodes_module.RoundOutcome(**payload)
                        )
                    except TypeError:
                        continue  # an unreadable round must not lose the delegation
            elif kind == "close":
                state.pop(delegation_id, None)
        return state

    def _was_closed(self, delegation_id: str) -> bool:
        return any(
            event["event"] == "close" and event["delegation_id"] == delegation_id
            for event in self._events()
        )
