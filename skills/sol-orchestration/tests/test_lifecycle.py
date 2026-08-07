"""Dispatch, collect, correct, cancel — all provable against the double, all free.

The spawn is asynchronous: it returns an admission handle and never the child's
answer. Dispatch and collection are therefore separate orchestrator turns, and the
ledger between them is what stops a crashed or abandoned delegation vanishing — which
would lose exactly the highest-information episodes in the corpus.

The ordering inside dispatch is a correctness requirement, not a style: snapshot,
then open the record, then spawn. Opening the record after the handle returns loses
every spawn that raises.
"""

from __future__ import annotations

import asyncio

import pytest

from sol_orchestration import config, contract, lifecycle as lifecycle_module, spec as spec_module

from conftest import FakeClock, RecordingHost, RecordingRecorder, RecordingSnapshotter
from test_config import WELL_FORMED, seed

SURVIVING = tuple(WELL_FORMED["allowlist"])
ROUTED = SURVIVING[0]


def a_spec(**overrides: object) -> spec_module.Spec:
    fields: dict[str, object] = {
        "objective": "Add a retry to the fetch helper",
        "domain": "python",
        "difficulty": "hard",
        "ownership": ("src/fetch.py",),
        "verification_command": "pytest",
    }
    fields.update(overrides)
    return spec_module.Spec(**fields)  # type: ignore[arg-type]


@pytest.fixture
def declared(agent_home) -> config.Config:
    seed(agent_home, WELL_FORMED)
    return config.load()


def build(
    declared: config.Config,
    host: RecordingHost | None = None,
    snapshotter: RecordingSnapshotter | None = None,
) -> tuple[lifecycle_module.Lifecycle, RecordingHost, RecordingRecorder, RecordingSnapshotter, FakeClock]:
    host = host or RecordingHost()
    recorder = RecordingRecorder()
    snapshotter = snapshotter or RecordingSnapshotter()
    clock = FakeClock()
    engine = lifecycle_module.Lifecycle(
        declared=declared,
        host=host,
        recorder=recorder,
        snapshotter=snapshotter,
        clock=clock,
        ids=iter(f"d-{index:04d}" for index in range(1, 100)),
    )
    return engine, host, recorder, snapshotter, clock


# --- dispatch -----------------------------------------------------------------


def test_dispatch_returns_a_handle_without_waiting_for_the_childs_answer(declared: config.Config) -> None:
    engine, host, _, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    assert delegation.handle is not None
    assert delegation.outcome is None, "dispatch settled an outcome, so it waited"
    assert host.spawns, "no spawn was issued"


def test_dispatch_without_a_routed_selector_refuses_before_the_host(declared: config.Config) -> None:
    engine, host, _, _, _ = build(declared)
    with pytest.raises(contract.Refusal):
        asyncio.run(engine.dispatch(a_spec(), selector=None, surviving=SURVIVING))
    assert host.spawns == [], "the host was reached without a routed selector"


def test_a_selector_the_router_did_not_return_is_refused_at_the_adapter(declared: config.Config) -> None:
    engine, host, _, _, _ = build(declared)
    with pytest.raises(contract.Refusal) as raised:
        asyncio.run(engine.dispatch(a_spec(), selector="provider-x/not-surviving", surviving=SURVIVING))
    assert "provider-x/not-surviving" in raised.value.remedy
    assert host.spawns == []


def test_dispatch_refuses_when_no_pre_spawn_snapshot_was_recorded(declared: config.Config) -> None:
    """Without a snapshot there is no baseline, so no ownership verdict is possible."""
    engine, host, _, _, _ = build(declared, snapshotter=RecordingSnapshotter(available=False))
    with pytest.raises(contract.Refusal) as raised:
        asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    assert "snapshot" in raised.value.remedy.lower()
    assert host.spawns == []


def test_dispatch_snapshots_and_opens_the_record_before_it_spawns(declared: config.Config) -> None:
    engine, host, recorder, snapshotter, _ = build(declared)
    asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    assert snapshotter.captures == 1
    assert recorder.opened() == ["d-0001"]
    assert recorder.events[0][0] == "open", "the record was opened after the spawn"


def test_a_spawn_that_raises_still_closes_an_episode_with_the_failure_recorded(
    declared: config.Config,
) -> None:
    """A spawn that fails after surviving preflight is among the most informative records."""
    host = RecordingHost()
    host.spawn_failures = (ROUTED,)
    engine, host, recorder, _, _ = build(declared, host=host)
    with pytest.raises(RuntimeError):
        asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    assert recorder.opened() == ["d-0001"]
    assert recorder.closed() == [("d-0001", "abandon")]
    closed = [payload for kind, _, payload in recorder.events if kind == "close"][0]
    kinds = {entry["kind"] for entry in closed["degradations"]}
    assert contract.SPAWN_RAISED in kinds


def test_the_open_record_carries_the_selector_that_was_actually_passed(declared: config.Config) -> None:
    engine, _, recorder, _, _ = build(declared)
    asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    opened = [payload for kind, _, payload in recorder.events if kind == "open"][0]
    assert opened["selector"] == ROUTED
    assert opened["surviving_size"] == len(SURVIVING)


def test_two_delegations_never_collide_on_a_child_session_name(declared: config.Config) -> None:
    engine, host, _, _, _ = build(declared)
    first = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    second = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    assert first.child_name != second.child_name
    assert first.delegation_id != second.delegation_id
    assert len({spawn["name"] for spawn in host.spawns}) == 2


def test_generated_child_names_fit_the_runtimes_own_length_cap(declared: config.Config) -> None:
    engine, host, _, _, _ = build(declared)
    asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    assert len(host.spawns[0]["name"]) <= 64


# --- collection ---------------------------------------------------------------


def test_completion_is_detected_from_the_file_signal_not_from_a_reply(declared: config.Config) -> None:
    engine, host, _, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    spec_module.write_signal(delegation.delegation_id, {"status": "done", "summary": "added a retry"})
    collection = asyncio.run(engine.collect(delegation, bound_seconds=60))
    assert collection.completed is True
    assert collection.signal is not None
    assert collection.signal["summary"] == "added a retry"


def test_a_child_that_never_reports_is_cancelled_and_closed_as_abandon(declared: config.Config) -> None:
    engine, host, recorder, _, clock = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    collection = asyncio.run(engine.collect(delegation, bound_seconds=30))
    assert collection.completed is False
    assert collection.timed_out is True
    assert delegation.child_name in host.deletions or delegation.handle.child_id in host.deletions
    assert recorder.closed() == [(delegation.delegation_id, "abandon")]
    assert clock.now >= 30


def test_a_timeout_is_recorded_as_a_degradation(declared: config.Config) -> None:
    engine, _, recorder, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    asyncio.run(engine.collect(delegation, bound_seconds=30))
    closed = [payload for kind, _, payload in recorder.events if kind == "close"][0]
    assert contract.CHILD_TIMEOUT in {entry["kind"] for entry in closed["degradations"]}


def test_a_child_the_registry_reports_as_errored_stops_the_wait(declared: config.Config) -> None:
    """Waiting out the full bound on a child the host already failed wastes the bound."""
    engine, host, _, _, clock = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    host.complete_child(delegation.child_name, status="error")
    collection = asyncio.run(engine.collect(delegation, bound_seconds=600))
    assert collection.completed is False
    assert collection.child_errored is True
    assert clock.now < 600


def test_a_child_that_completes_without_writing_a_signal_is_not_a_completion(
    declared: config.Config,
) -> None:
    """A child whose last act was a reply rather than the file must not read as done."""
    engine, host, _, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    host.complete_child(delegation.child_name, status="completed")
    collection = asyncio.run(engine.collect(delegation, bound_seconds=60))
    assert collection.completed is False
    assert collection.signal is None


# --- corrections --------------------------------------------------------------


def test_a_correction_to_a_live_retained_child_reaches_it_by_name(declared: config.Config) -> None:
    engine, host, _, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    result = asyncio.run(engine.correct(delegation, "the retry count is off by one"))
    assert result.delivered is True
    assert result.restarted is False
    assert host.messages[-1]["receiver_name"] == delegation.child_name
    assert host.messages[-1]["receiver_role"] == "child"
    assert delegation.correction_count == 1


def test_an_unreachable_message_channel_restarts_on_the_same_model(
    declared: config.Config,
) -> None:
    """Trace regression: no agent_message still has the lifecycle's recorded restart path."""
    engine, host, recorder, _, _ = build(declared)
    host.without_roster()
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))

    result = asyncio.run(engine.correct(delegation, "the retry count is off by one"))

    assert result.delivered is False
    assert result.restarted is True
    assert result.delegation is not None
    assert result.delegation.selector == delegation.selector
    assert result.delegation.restarted_from == delegation.delegation_id
    assert len(recorder.opened()) == 2, "the restart bypassed the episode lifecycle"
    assert contract.RESTART_ONLY_CORRECTIONS in {
        entry.kind for entry in delegation.degradations
    }, "the runtime fallback was absent from the episode detail"

    asyncio.run(engine.close(delegation, "fix-first"))
    asyncio.run(engine.close(result.delegation, "ship"))
    assert recorder.closed() == [
        (delegation.delegation_id, "fix-first"),
        (result.delegation.delegation_id, "ship"),
    ]
    original_close = next(
        payload
        for kind, delegation_id, payload in recorder.events
        if kind == "close" and delegation_id == delegation.delegation_id
    )
    assert contract.RESTART_ONLY_CORRECTIONS in {
        entry["kind"] for entry in original_close["degradations"]
    }


def test_a_correction_to_a_vanished_child_opens_a_new_linked_delegation(
    declared: config.Config,
) -> None:
    engine, host, recorder, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    host.forget_child(delegation.child_name)

    result = asyncio.run(engine.correct(delegation, "the retry count is off by one"))

    assert result.restarted is True
    assert result.delegation is not None
    assert result.delegation.delegation_id != delegation.delegation_id
    assert result.delegation.restarted_from == delegation.delegation_id
    assert result.delegation.selector == delegation.selector, "the restart changed model"
    assert delegation.correction_count == 0, "a restart incremented the original's count"
    opened = [payload for kind, _, payload in recorder.events if kind == "open"]
    assert opened[-1]["restarted_from"] == delegation.delegation_id
    assert opened[-1]["restarted_context"] is True


def test_the_fix_first_cap_forces_rethink_rather_than_another_round(declared: config.Config) -> None:
    engine, host, _, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    for _ in range(lifecycle_module.FIX_FIRST_CAP):
        assert asyncio.run(engine.correct(delegation, "again")).forced_rethink is False
    result = asyncio.run(engine.correct(delegation, "and again"))
    assert result.forced_rethink is True
    assert result.delivered is False
    assert delegation.correction_count == lifecycle_module.FIX_FIRST_CAP


def test_the_cap_is_a_package_constant_not_operator_configuration() -> None:
    """A stop an operator can raise is not a stop."""
    assert isinstance(lifecycle_module.FIX_FIRST_CAP, int)
    assert lifecycle_module.FIX_FIRST_CAP >= 1
    assert "fix_first_cap" not in str(WELL_FORMED)


# --- closing ------------------------------------------------------------------


def test_closing_writes_exactly_one_terminal_outcome(declared: config.Config) -> None:
    engine, _, recorder, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    asyncio.run(engine.close(delegation, "ship"))
    assert recorder.closed() == [(delegation.delegation_id, "ship")]


def test_closing_twice_does_not_write_a_second_record(declared: config.Config) -> None:
    engine, _, recorder, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    asyncio.run(engine.close(delegation, "ship"))
    asyncio.run(engine.close(delegation, "rethink"))
    assert recorder.closed() == [(delegation.delegation_id, "ship")]


def test_an_outcome_outside_the_declared_four_is_refused(declared: config.Config) -> None:
    engine, _, _, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    with pytest.raises(ValueError):
        asyncio.run(engine.close(delegation, "looks-good-to-me"))


def test_closing_removes_the_signal_file_so_the_next_delegation_starts_clean(
    declared: config.Config,
) -> None:
    engine, _, _, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    spec_module.write_signal(delegation.delegation_id, {"status": "done"})
    assert spec_module.signal_path(delegation.delegation_id).exists()
    asyncio.run(engine.close(delegation, "ship"))
    assert not spec_module.signal_path(delegation.delegation_id).exists()


def test_close_threads_caller_supplied_detail_into_the_record(declared: config.Config) -> None:
    """Without this the cost term never reaches the corpus.

    The lifecycle does not read transcripts — that is the episode layer's job — so the
    caller is the only one holding the child's usage and clamped effort at close time.
    Found by the live smoke run, which would otherwise have produced the epic's first
    real episode with no cost on it at all.
    """
    engine, _, recorder, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    asyncio.run(
        engine.close(
            delegation,
            "ship",
            {
                "child_session_id": "sess-child-1",
                "child_effort_clamped": "high",
                "usage": {"total_tokens": 1234},
            },
        )
    )
    closed = [payload for kind, _, payload in recorder.events if kind == "close"][0]
    assert closed["child_session_id"] == "sess-child-1"
    assert closed["child_effort_clamped"] == "high"
    assert closed["usage"] == {"total_tokens": 1234}
    assert closed["selector"] == ROUTED, "caller detail overwrote a lifecycle-owned field"


def test_caller_degradations_are_merged_with_the_lifecycles_own(declared: config.Config) -> None:
    engine, host, recorder, _, _ = build(declared)
    delegation = asyncio.run(engine.dispatch(a_spec(), selector=ROUTED, surviving=SURVIVING))
    delegation.degradations.append(
        contract.Degradation(kind=contract.CHILD_TIMEOUT, detail="from the lifecycle")
    )
    asyncio.run(
        engine.close(
            delegation, "abandon",
            {"degradations": [{"kind": contract.UNREADABLE_COST, "detail": "from the caller"}]},
        )
    )
    closed = [payload for kind, _, payload in recorder.events if kind == "close"][0]
    kinds = {entry["kind"] for entry in closed["degradations"]}
    assert kinds == {contract.CHILD_TIMEOUT, contract.UNREADABLE_COST}
