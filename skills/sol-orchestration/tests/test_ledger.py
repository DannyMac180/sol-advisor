"""The ledger is what stops a crashed delegation vanishing instead of being recorded.

The spawn is asynchronous and the orchestrator's memory does not survive compaction.
Without something on disk between dispatch and collection, a delegation that crashed,
hung, or was abandoned leaves nothing at all — and those are the highest-information
episodes in the corpus, so a design that only writes on success loses exactly them.

Reconstruction is deliberately ledger-only. Reconciling against live child sessions
depends on a runtime path this epic never read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sol_orchestration import contract, episodes, ledger as ledger_module, reader


def a_round(index: int = 0, exit_status: int | None = 0) -> episodes.RoundOutcome:
    return episodes.RoundOutcome(
        round_index=index,
        verification_exit_status=exit_status,
        verification_timed_out=False,
        ownership_violation=False,
        integrity_failure=False,
        empty_diff=False,
        wall_clock_seconds=1.0,
    )


def opened(delegation_id: str = "d-1", **kw) -> dict:
    fields = {
        "delegation_id": delegation_id,
        "selector": "provider-a/model-one",
        "surviving_size": 3,
        "domain": "python",
        "difficulty": "hard",
        "ownership": ("src/a.py",),
        "effort_at_spawn": "high",
        "child_name": f"sol-{delegation_id}",
    }
    fields.update(kw)
    return episodes.open_record(**fields)


# --- two-phase write ----------------------------------------------------------


def test_the_open_record_exists_before_any_close(agent_home: Path) -> None:
    book = ledger_module.Ledger()
    book.open("d-1", opened("d-1"))
    assert [entry.delegation_id for entry in book.open_delegations()] == ["d-1"]
    assert not episodes.store_path().exists(), "an episode was written before a terminal outcome"


def test_the_ledger_records_the_open_even_with_no_episode_yet(agent_home: Path) -> None:
    book = ledger_module.Ledger()
    book.open("d-1", opened("d-1"))
    assert book.path.exists()
    lines = [json.loads(line) for line in book.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines[0]["event"] == "open"
    assert lines[0]["delegation_id"] == "d-1"


@pytest.mark.parametrize("outcome", ["ship", "fix-first", "rethink", "abandon"])
def test_a_terminal_outcome_closes_exactly_one_record(agent_home: Path, outcome: str) -> None:
    book = ledger_module.Ledger()
    book.open("d-1", opened("d-1"))
    book.close("d-1", outcome, {})
    records = reader.read_all()
    assert len(records) == 1
    assert records[0]["delegation_id"] == "d-1"
    assert records[0]["outcome"] == outcome
    assert book.open_delegations() == ()


def test_closing_twice_writes_no_second_record(agent_home: Path) -> None:
    book = ledger_module.Ledger()
    book.open("d-1", opened("d-1"))
    book.close("d-1", "ship", {})
    book.close("d-1", "rethink", {})
    records = reader.read_all()
    assert len(records) == 1
    assert records[0]["outcome"] == "ship"


def test_a_spawn_that_raised_still_closes_a_record(agent_home: Path) -> None:
    book = ledger_module.Ledger()
    book.open("d-1", opened("d-1"))
    book.close(
        "d-1", "abandon",
        {"degradations": [{"kind": contract.SPAWN_RAISED, "detail": "model went away"}]},
    )
    records = reader.read_all()
    assert len(records) == 1
    assert contract.SPAWN_RAISED in {entry["kind"] for entry in records[0]["degradations"]}


def test_closing_a_delegation_that_was_never_opened_is_refused(agent_home: Path) -> None:
    """Closing an unopened delegation would write a record with no spawn behind it."""
    book = ledger_module.Ledger()
    with pytest.raises(KeyError):
        book.close("never-opened", "ship", {})
    assert not episodes.store_path().exists()


# --- restarted context --------------------------------------------------------


def test_a_restarted_context_writes_a_second_record_under_a_new_id(agent_home: Path) -> None:
    book = ledger_module.Ledger()
    book.open("d-1", opened("d-1"))
    book.open("d-2", opened("d-2", restarted_from="d-1"))
    book.close("d-1", "abandon", {})
    book.close("d-2", "ship", {})

    records = {entry["delegation_id"]: entry for entry in reader.read_all()}
    assert set(records) == {"d-1", "d-2"}
    assert records["d-2"]["restarted_from"] == "d-1"
    assert records["d-2"]["restarted_context"] is True
    assert records["d-1"]["correction_count"] == 0, "the restart incremented the original's count"


# --- per-round accumulation ---------------------------------------------------


def test_rounds_accumulate_on_the_open_delegation_and_land_on_the_record(agent_home: Path) -> None:
    book = ledger_module.Ledger()
    book.open("d-1", opened("d-1"))
    book.record_round("d-1", a_round(0, 1))
    book.record_round("d-1", a_round(1, 1))
    book.record_round("d-1", a_round(2, 0))
    book.close("d-1", "ship", {})
    record = reader.read_all()[0]
    assert [entry["verification_exit_status"] for entry in record["rounds"]] == [1, 1, 0]
    assert record["correction_count"] == 2


# --- reconstruction -----------------------------------------------------------


def test_an_open_delegation_survives_a_simulated_orchestrator_restart(agent_home: Path) -> None:
    """A lost session must keep its open record rather than losing the delegation."""
    first = ledger_module.Ledger()
    first.open("d-1", opened("d-1"))
    first.record_round("d-1", a_round(0, 1))
    del first

    fresh = ledger_module.Ledger()  # a brand-new turn, no in-memory state at all
    reconstructed = fresh.open_delegations()
    assert [entry.delegation_id for entry in reconstructed] == ["d-1"]
    assert reconstructed[0].record["selector"] == "provider-a/model-one"
    assert len(reconstructed[0].rounds) == 1


def test_a_reconstructed_delegation_is_closable_as_abandon(agent_home: Path) -> None:
    ledger_module.Ledger().open("d-1", opened("d-1"))
    fresh = ledger_module.Ledger()
    fresh.close("d-1", "abandon", {})
    records = reader.read_all()
    assert len(records) == 1
    assert records[0]["outcome"] == "abandon"
    assert fresh.open_delegations() == ()


def test_reconstruction_is_ledger_only_and_consults_no_live_session(agent_home: Path) -> None:
    """Reconciling against live children depends on a runtime path this epic never read."""
    source = Path(ledger_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("list_subagents", "host_request", "import rlm", "spawn("):
        assert forbidden not in source, f"ledger.py consults a live session via {forbidden}"


def test_a_truncated_ledger_line_does_not_lose_the_rest(agent_home: Path) -> None:
    """A crash mid-write should cost one line, not the whole reconstruction."""
    book = ledger_module.Ledger()
    book.open("d-1", opened("d-1"))
    book.open("d-2", opened("d-2"))
    with book.path.open("a", encoding="utf-8") as handle:
        handle.write('{"event": "open", "delegation_id": "d-3", "reco')
    fresh = ledger_module.Ledger()
    assert {entry.delegation_id for entry in fresh.open_delegations()} == {"d-1", "d-2"}


# --- the reader ---------------------------------------------------------------


def test_the_reader_accepts_a_current_version_record(agent_home: Path) -> None:
    book = ledger_module.Ledger()
    book.open("d-1", opened("d-1"))
    book.close("d-1", "ship", {})
    result = reader.validate(reader.read_all()[0])
    assert result.valid is True
    assert result.errors == ()
    assert result.unknown_version is False


def test_the_reader_rejects_a_malformed_record() -> None:
    result = reader.validate({"schema_version": episodes.SCHEMA_VERSION, "delegation_id": "d-1"})
    assert result.valid is False
    assert result.errors


def test_the_reader_rejects_something_that_is_not_a_record_at_all() -> None:
    assert reader.validate("a string").valid is False
    assert reader.validate({}).valid is False


def test_an_unknown_schema_version_is_reported_not_crashed_on() -> None:
    """Records outlive the code that wrote them; the consumer is a plan that does not exist."""
    result = reader.validate({"schema_version": 999, "delegation_id": "d-1"})
    assert result.unknown_version is True
    assert result.valid is False
    assert any("999" in error for error in result.errors)
    assert "schema" in " ".join(result.errors).lower()


def test_a_record_with_no_schema_version_is_reported_as_unknown() -> None:
    result = reader.validate({"delegation_id": "d-1"})
    assert result.unknown_version is True


def test_the_reader_reports_a_corrupt_store_line_rather_than_crashing(agent_home: Path) -> None:
    store = episodes.store_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text('{"delegation_id": "d-1", "schema_version": 1}\n{ broken\n', encoding="utf-8")
    records, problems = reader.read_all_reporting()
    assert len(records) == 1
    assert len(problems) == 1
    assert "2" in problems[0], "the problem does not name the offending line"


def test_the_reader_ships_with_the_writer(agent_home: Path) -> None:
    """A version contract nothing can consume is worthless."""
    assert reader.SUPPORTED_SCHEMA_VERSIONS
    assert episodes.SCHEMA_VERSION in reader.SUPPORTED_SCHEMA_VERSIONS


# --- the ledger really is the lifecycle's recorder -----------------------------


def test_the_ledger_satisfies_the_protocol_the_lifecycle_dispatches_against(
    agent_home: Path,
) -> None:
    """Two modules agreeing on a protocol in principle is not the same as in practice.

    This wires the real lifecycle to the real ledger and asserts the two-phase write
    landed on disk in the right order — which is the property the whole corpus rests
    on and the one no unit test on either side can see by itself.
    """
    import asyncio

    from sol_orchestration import config, lifecycle as lifecycle_module, spec as spec_module

    from conftest import RecordingHost, RecordingSnapshotter
    from test_config import WELL_FORMED, seed

    seed(agent_home, WELL_FORMED)
    declared = config.load()
    book = ledger_module.Ledger()
    host = RecordingHost()

    engine = lifecycle_module.Lifecycle(
        declared=declared,
        host=host,
        recorder=book,
        snapshotter=RecordingSnapshotter(),
        ids=iter(["d-live-1"]),
    )
    delegation = asyncio.run(
        engine.dispatch(
            spec_module.Spec(
                objective="add a retry",
                domain="python",
                difficulty="hard",
                ownership=("src/fetch.py",),
                verification_command="pytest",
            ),
            selector=WELL_FORMED["allowlist"][0],
            surviving=tuple(WELL_FORMED["allowlist"]),
        )
    )

    # Open is on disk and no episode exists yet: the record outlives a lost turn.
    assert [entry.delegation_id for entry in book.open_delegations()] == ["d-live-1"]
    assert not episodes.store_path().exists()

    book.record_round("d-live-1", a_round(0, 1))
    book.record_round("d-live-1", a_round(1, 0))
    asyncio.run(engine.close(delegation, "ship"))

    records = reader.read_all()
    assert len(records) == 1
    assert records[0]["delegation_id"] == "d-live-1"
    assert records[0]["outcome"] == "ship"
    assert records[0]["selector"] == WELL_FORMED["allowlist"][0]
    assert records[0]["surviving_allowlist_size"] == len(WELL_FORMED["allowlist"])
    assert records[0]["correction_count"] == 1
    assert reader.validate(records[0]).valid is True
    assert book.open_delegations() == ()


def test_a_spawn_that_raises_through_the_real_lifecycle_still_leaves_one_record(
    agent_home: Path,
) -> None:
    """The failure that must never be the one case that vanishes."""
    import asyncio

    from sol_orchestration import config, lifecycle as lifecycle_module, spec as spec_module

    from conftest import RecordingHost, RecordingSnapshotter
    from test_config import WELL_FORMED, seed

    seed(agent_home, WELL_FORMED)
    declared = config.load()
    book = ledger_module.Ledger()
    host = RecordingHost()
    host.spawn_failures = (WELL_FORMED["allowlist"][0],)

    engine = lifecycle_module.Lifecycle(
        declared=declared, host=host, recorder=book,
        snapshotter=RecordingSnapshotter(), ids=iter(["d-boom"]),
    )
    with pytest.raises(RuntimeError):
        asyncio.run(
            engine.dispatch(
                spec_module.Spec(
                    objective="x", domain="python", difficulty="hard",
                    ownership=("src/fetch.py",), verification_command="pytest",
                ),
                selector=WELL_FORMED["allowlist"][0],
                surviving=tuple(WELL_FORMED["allowlist"]),
            )
        )

    records = reader.read_all()
    assert len(records) == 1
    assert records[0]["outcome"] == "abandon"
    assert contract.SPAWN_RAISED in {entry["kind"] for entry in records[0]["degradations"]}
    assert reader.validate(records[0]).valid is True


def test_a_record_opened_through_the_lifecycle_carries_the_full_schema(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lifecycle was written against a protocol, not against the record schema.

    It passes the fields it knows about, which is a different shape. The ledger is
    where the two are reconciled, and without that reconciliation every record written
    through the real delegation path would land with no schema version and no effort
    confounder — invisible to unit tests on either side.
    """
    from sol_orchestration import preflight

    session_id = "orchestrator-session"
    sessions = agent_home / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{session_id}.jsonl").write_text(
        json.dumps({"type": "thinking_level_change", "thinkingLevel": "xhigh"}) + "\n",
        encoding="utf-8",
    )
    artifacts = agent_home / "session-artifacts" / session_id
    artifacts.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(preflight.SESSION_DIR_ENV_VAR, str(artifacts))

    book = ledger_module.Ledger()
    # Exactly the shape lifecycle.dispatch emits — no schema version, no effort.
    book.open(
        "d-1",
        {
            "delegation_id": "d-1",
            "selector": "provider-a/model-one",
            "surviving_size": 3,
            "domain": "python",
            "difficulty": "hard",
            "ownership": ["src/a.py"],
            "child_name": "sol-d-1",
            "restarted_from": None,
            "restarted_context": False,
        },
    )
    book.close("d-1", "ship", {"child_effort_clamped": "high"})

    record = reader.read_all()[0]
    assert reader.validate(record).valid is True
    assert record["schema_version"] == episodes.SCHEMA_VERSION
    # All four confounder controls present on a record the lifecycle opened.
    assert record["selector"] == "provider-a/model-one"
    assert record["effort_at_spawn"] == "xhigh", "the effort in force at the spawn was not captured"
    assert record["child_effort_clamped"] == "high"
    assert record["surviving_allowlist_size"] == 3


def test_the_effort_is_read_at_the_spawn_and_not_carried_forward(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The operator can move the dial mid-session; two delegations may differ."""
    from sol_orchestration import preflight

    session_id = "s1"
    sessions = agent_home / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    transcript = sessions / f"{session_id}.jsonl"
    artifacts = agent_home / "session-artifacts" / session_id
    artifacts.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(preflight.SESSION_DIR_ENV_VAR, str(artifacts))

    lifecycle_shape = {
        "selector": "a/b", "surviving_size": 1, "domain": "x", "difficulty": "y",
        "ownership": ["f"], "child_name": "c", "restarted_from": None,
    }

    transcript.write_text(
        json.dumps({"type": "thinking_level_change", "thinkingLevel": "high"}) + "\n", encoding="utf-8"
    )
    book = ledger_module.Ledger()
    book.open("d-1", {**lifecycle_shape, "delegation_id": "d-1"})

    # The operator raises the dial between the two delegations.
    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "thinking_level_change", "thinkingLevel": "xhigh"}) + "\n")
    book.open("d-2", {**lifecycle_shape, "delegation_id": "d-2"})

    book.close("d-1", "ship", {})
    book.close("d-2", "ship", {})
    records = {entry["delegation_id"]: entry for entry in reader.read_all()}
    assert records["d-1"]["effort_at_spawn"] == "high"
    assert records["d-2"]["effort_at_spawn"] == "xhigh"


def test_an_unreadable_effort_records_why_rather_than_a_bare_null(agent_home: Path) -> None:
    """A null with no stated reason reads as a fact rather than as an absence.

    The first live delegation recorded effort_at_spawn: null with an empty degradations
    list — indistinguishable, to whoever fits a policy against this corpus later, from
    a session that genuinely ran at no effort level.
    """
    from sol_orchestration import preflight

    monkey = pytest.MonkeyPatch()
    monkey.delenv(preflight.SESSION_DIR_ENV_VAR, raising=False)
    try:
        book = ledger_module.Ledger()
        book.open("d-1", {
            "delegation_id": "d-1", "selector": "a/b", "surviving_size": 1,
            "domain": "x", "difficulty": "y", "ownership": ["f"], "child_name": "c",
        })
        book.close("d-1", "ship", {})
    finally:
        monkey.undo()

    record = reader.read_all()[0]
    assert record["effort_at_spawn"] is None
    kinds = {entry["kind"] for entry in record["degradations"]}
    assert contract.UNREADABLE_EFFORT in kinds, "the effort is null with no reason given"
    assert reader.validate(record).valid is True
    assert ledger_module.PENDING_DEGRADATIONS_KEY not in record, "plumbing leaked into the corpus"


def test_a_readable_effort_records_no_degradation(agent_home: Path, monkeypatch) -> None:
    from sol_orchestration import preflight

    session_id = "s-clean"
    sessions = agent_home / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{session_id}.jsonl").write_text(
        json.dumps({"type": "thinking_level_change", "thinkingLevel": "high"}) + "\n",
        encoding="utf-8",
    )
    artifacts = agent_home / "session-artifacts" / session_id
    artifacts.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(preflight.SESSION_DIR_ENV_VAR, str(artifacts))

    book = ledger_module.Ledger()
    book.open("d-1", {"delegation_id": "d-1", "selector": "a/b", "surviving_size": 1,
                      "domain": "x", "difficulty": "y", "ownership": ["f"], "child_name": "c"})
    book.close("d-1", "ship", {})
    record = reader.read_all()[0]
    assert record["effort_at_spawn"] == "high"
    assert record["degradations"] == []
