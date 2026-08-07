"""Preflight is where the package decides it cannot proceed, before spending anything.

Each test below is one acceptance criterion from LS-2576. The distinction that runs
through all of them: a refusal names an artifact and stops; a degradation is recorded
and the delegation continues. Getting that split wrong in either direction is a
defect — a refusal where a degradation belongs freezes the corpus on a patch bump,
and a degradation where a refusal belongs spends money on a delegation that cannot
be corrected.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from sol_orchestration import config, contract, host as host_module, preflight

from conftest import RUNTIME_SEARCH_CAP, RecordingHost
from test_config import WELL_FORMED, seed


def child(active_session_id: str | None, status: str = "running") -> host_module.Subagent:
    return host_module.Subagent(
        child_id="sub-1",
        active_session_id=active_session_id,
        session_id="sess-child",
        session_name="subagent-worker-1",
        session_dir=Path("/tmp/child"),
        status=status,
    )


def write_transcript(home: Path, session_id: str, entries: list[dict]) -> Path:
    """Write a session transcript in the runtime's own JSONL shape."""
    sessions = home / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    path = sessions / f"{session_id}.jsonl"
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    return path


def use_session(monkeypatch: pytest.MonkeyPatch, home: Path, session_id: str) -> None:
    """Point the effort read at a session, exactly as the kernel is pointed at one."""
    artifacts = home / "session-artifacts" / session_id
    artifacts.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(preflight.SESSION_DIR_ENV_VAR, str(artifacts))


def at_effort(monkeypatch: pytest.MonkeyPatch, home: Path, level: str) -> None:
    session_id = "019fdc40-edf4-74ee-b080-c88acfcbbfaa"
    write_transcript(
        home,
        session_id,
        [
            {"type": "session", "version": preflight.VERIFIED_RUNTIME.session_record_version, "id": session_id},
            {"type": "thinking_level_change", "timestamp": "2026-08-07T10:00:00.000Z", "thinkingLevel": "low"},
            {"type": "thinking_level_change", "timestamp": "2026-08-07T12:44:30.632Z", "thinkingLevel": level},
        ],
    )
    use_session(monkeypatch, home, session_id)


def at_verified_runtime(home: Path) -> None:
    from sol_orchestration import home as home_module

    venv = home_module.kernel_venv()
    venv.mkdir(parents=True, exist_ok=True)
    (venv / preflight.BOOTSTRAP_VERSION_FILE).write_text(
        json.dumps({"schema": preflight.VERIFIED_RUNTIME.kernel_bootstrap_schema}), encoding="utf-8"
    )


# --- availability -------------------------------------------------------------


def test_an_unavailable_entry_is_dropped_with_a_reason_and_the_rest_survive(agent_home: Path) -> None:
    host = RecordingHost(catalog=("provider-one/alive",))
    surviving, dropped = asyncio.run(
        preflight.resolve_availability(("provider-one/alive", "provider-one/expired"), host)
    )
    assert surviving == ("provider-one/alive",)
    assert [entry.selector for entry in dropped] == ["provider-one/expired"]
    assert dropped[0].reason


def test_an_expired_credential_is_dropped_rather_than_raising(agent_home: Path) -> None:
    host = RecordingHost(catalog=("provider-one/alive", "provider-one/expired"), failures=("provider-one/expired",))
    surviving, dropped = asyncio.run(
        preflight.resolve_availability(("provider-one/alive", "provider-one/expired"), host)
    )
    assert surviving == ("provider-one/alive",)
    assert "authentication failed" in dropped[0].reason


def test_availability_issues_one_query_per_entry_and_never_an_enumeration(agent_home: Path) -> None:
    """The twenty-result cap makes a single catalog enumeration silently lossy."""
    allowlist = tuple(f"provider-one/model-{index:02d}" for index in range(RUNTIME_SEARCH_CAP + 5))
    host = RecordingHost(catalog=allowlist)
    surviving, dropped = asyncio.run(preflight.resolve_availability(allowlist, host))
    assert surviving == allowlist, "an authenticated entry was reported unavailable"
    assert dropped == ()
    assert [query for query, _ in host.searches] == list(allowlist)
    assert "" not in [query for query, _ in host.searches], "a catalog enumeration was issued"


def test_availability_matches_the_exact_selector_not_a_substring(agent_home: Path) -> None:
    """The spawn resolves by exact provider/id, so a near miss is not availability."""
    host = RecordingHost(catalog=("provider-one/model-alpha-preview",))
    surviving, dropped = asyncio.run(preflight.resolve_availability(("provider-one/model-alpha",), host))
    assert surviving == ()
    assert dropped[0].selector == "provider-one/model-alpha"


def test_availability_is_case_insensitive_on_the_selector(agent_home: Path) -> None:
    """The runtime lowercases before matching; the package must agree with it."""
    host = RecordingHost(catalog=("provider-one/model-alpha",))
    surviving, _ = asyncio.run(preflight.resolve_availability(("Provider-One/Model-Alpha",), host))
    assert surviving == ("Provider-One/Model-Alpha",)


# --- refusals -----------------------------------------------------------------


def test_no_surviving_entry_refuses_naming_the_config_and_never_falls_back(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(agent_home, WELL_FORMED)
    at_effort(monkeypatch, agent_home, "high")
    at_verified_runtime(agent_home)
    host = RecordingHost(catalog=())
    with pytest.raises(contract.Refusal) as raised:
        asyncio.run(preflight.run(host))
    assert str(config.config_path()) in raised.value.artifact
    assert "fall back" not in raised.value.remedy.lower()


def test_a_missing_config_refuses_naming_the_expected_path(agent_home: Path) -> None:
    with pytest.raises(contract.Refusal) as raised:
        asyncio.run(preflight.run(RecordingHost()))
    assert str(config.config_path()) in raised.value.artifact


def test_effort_below_the_floor_asks_the_operator_to_raise_it(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The package has no host request that sets a level, so it must not pretend to."""
    seed(agent_home, WELL_FORMED)
    at_effort(monkeypatch, agent_home, "medium")
    at_verified_runtime(agent_home)
    host = RecordingHost(catalog=tuple(WELL_FORMED["allowlist"]))
    with pytest.raises(contract.Refusal) as raised:
        asyncio.run(preflight.run(host))
    assert preflight.EFFORT_FLOOR in raised.value.remedy
    assert "/effort" in raised.value.remedy


def test_non_retained_children_degrade_to_restart_only_corrections(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lifecycle already restarts a correction on the same model when retention is absent."""
    seed(agent_home, WELL_FORMED)
    at_effort(monkeypatch, agent_home, "high")
    at_verified_runtime(agent_home)
    host = RecordingHost(catalog=tuple(WELL_FORMED["allowlist"]), subagents=(child(active_session_id=None),))
    report = asyncio.run(preflight.run(host))
    assert contract.RESTART_ONLY_CORRECTIONS in {entry.kind for entry in report.degradations}
    assert report.retention.retained_children == 0


def test_an_unreachable_agent_message_request_degrades_to_restart_only_corrections(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trace regression: missing agent_message must not force raw, unrecorded spawning."""
    seed(agent_home, WELL_FORMED)
    at_effort(monkeypatch, agent_home, "high")
    at_verified_runtime(agent_home)
    host = RecordingHost(catalog=tuple(WELL_FORMED["allowlist"])).without_roster()
    report = asyncio.run(preflight.run(host))
    assert report.surviving == tuple(WELL_FORMED["allowlist"])
    assert report.retention.roster_reachable is False
    assert contract.RESTART_ONLY_CORRECTIONS in {entry.kind for entry in report.degradations}


def test_preflight_does_not_probe_the_unused_agent_observe_host_request(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Collection observes the signal and RLM registry; agent_observe is not a dependency."""
    seed(agent_home, WELL_FORMED)
    at_effort(monkeypatch, agent_home, "high")
    at_verified_runtime(agent_home)
    host = RecordingHost(catalog=tuple(WELL_FORMED["allowlist"]), observe=False)
    report = asyncio.run(preflight.run(host))
    assert report.surviving == tuple(WELL_FORMED["allowlist"])
    assert all(request_type != "agent_observe.list" for request_type, _ in host.requests)


# --- degradations -------------------------------------------------------------


def test_an_unreadable_transcript_degrades_rather_than_blocking(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(agent_home, WELL_FORMED)
    monkeypatch.delenv(preflight.SESSION_DIR_ENV_VAR, raising=False)
    at_verified_runtime(agent_home)
    host = RecordingHost(catalog=tuple(WELL_FORMED["allowlist"]))
    report = asyncio.run(preflight.run(host))
    assert report.effort is None
    assert contract.UNREADABLE_EFFORT in {entry.kind for entry in report.degradations}
    assert report.surviving == tuple(WELL_FORMED["allowlist"])


def test_a_malformed_transcript_line_degrades_rather_than_blocking(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = "malformed-session"
    sessions = agent_home / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{session_id}.jsonl").write_text("{not json\n", encoding="utf-8")
    use_session(monkeypatch, agent_home, session_id)
    seed(agent_home, WELL_FORMED)
    at_verified_runtime(agent_home)
    report = asyncio.run(preflight.run(RecordingHost(catalog=tuple(WELL_FORMED["allowlist"]))))
    assert report.effort is None
    assert contract.UNREADABLE_EFFORT in {entry.kind for entry in report.degradations}


def test_an_unrecognized_runtime_version_degrades_and_continues(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A routine patch bump must not halt every delegation and stop the dataset."""
    seed(agent_home, WELL_FORMED)
    at_effort(monkeypatch, agent_home, "high")
    from sol_orchestration import home as home_module

    venv = home_module.kernel_venv()
    venv.mkdir(parents=True, exist_ok=True)
    (venv / preflight.BOOTSTRAP_VERSION_FILE).write_text(
        json.dumps({"schema": preflight.VERIFIED_RUNTIME.kernel_bootstrap_schema + 1}), encoding="utf-8"
    )
    report = asyncio.run(preflight.run(RecordingHost(catalog=tuple(WELL_FORMED["allowlist"]))))
    assert contract.UNRECOGNIZED_RUNTIME_VERSION in {entry.kind for entry in report.degradations}
    assert report.surviving == tuple(WELL_FORMED["allowlist"])


def test_dropped_entries_are_recorded_as_a_degradation(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(agent_home, WELL_FORMED)
    at_effort(monkeypatch, agent_home, "high")
    at_verified_runtime(agent_home)
    host = RecordingHost(catalog=(WELL_FORMED["allowlist"][0],))
    report = asyncio.run(preflight.run(host))
    assert report.surviving == (WELL_FORMED["allowlist"][0],)
    assert contract.ALLOWLIST_ENTRIES_DROPPED in {entry.kind for entry in report.degradations}


# --- the happy path -----------------------------------------------------------


def test_a_clean_preflight_reports_the_surviving_set_and_the_effort_in_force(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(agent_home, WELL_FORMED)
    at_effort(monkeypatch, agent_home, "xhigh")
    at_verified_runtime(agent_home)
    host = RecordingHost(
        catalog=tuple(WELL_FORMED["allowlist"]), subagents=(child(active_session_id="sess-active"),)
    )
    report = asyncio.run(preflight.run(host))
    assert report.surviving == tuple(WELL_FORMED["allowlist"])
    assert report.dropped == ()
    assert report.effort == "xhigh"
    assert report.degradations == ()
    assert report.retention.roster_reachable is True
    assert report.retention.retained_children == 1


def test_xhigh_clears_the_floor_and_medium_does_not() -> None:
    assert preflight.clears_floor("xhigh")
    assert preflight.clears_floor("high")
    assert not preflight.clears_floor("medium")
    assert not preflight.clears_floor("off")


def test_retention_evidence_does_not_claim_an_unobserved_child(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agent-message roster is not proof that a future child will be retained."""
    seed(agent_home, WELL_FORMED)
    at_effort(monkeypatch, agent_home, "high")
    at_verified_runtime(agent_home)
    report = asyncio.run(preflight.run(RecordingHost(catalog=tuple(WELL_FORMED["allowlist"]))))
    assert report.retention.observed_children == 0
    assert report.retention.retained_children == 0
    assert report.retention.roster_reachable is True
    assert report.retention.proven_by_observation is False


# --- the parent's own model is always spawnable -------------------------------


def test_the_parents_own_model_survives_even_when_the_search_omits_it(agent_home: Path) -> None:
    """Proven live: the host spawns the parent's model regardless of the catalog.

        SPAWNED  openai-codex/gpt-5.6-luna  -> sub-22538538   (parent's own model)
        REFUSED  openai-codex/gpt-5.6-sol   -> unavailable, unauthenticated, or expired

    `_resolveRlmSubagentModel` returns the parent model directly before consulting
    `_authenticatedRlmModels()`. A search-only availability check drops the one entry
    guaranteed to work — and on a subscription-only credential that can be the only
    entry the operator has.
    """
    host = RecordingHost(catalog=())          # search reports nothing at all
    host.parent_model = "provider-sub/model-parent"
    surviving, dropped = asyncio.run(
        preflight.resolve_availability(("provider-sub/model-parent",), host)
    )
    assert surviving == ("provider-sub/model-parent",)
    assert dropped == ()


def test_a_sibling_model_on_the_same_absent_provider_is_still_dropped(agent_home: Path) -> None:
    """The exception is the parent's exact selector, not its provider."""
    host = RecordingHost(catalog=())
    host.parent_model = "provider-sub/model-parent"
    surviving, dropped = asyncio.run(
        preflight.resolve_availability(
            ("provider-sub/model-parent", "provider-sub/model-sibling"), host
        )
    )
    assert surviving == ("provider-sub/model-parent",)
    assert [entry.selector for entry in dropped] == ["provider-sub/model-sibling"]


def test_the_parent_exception_is_case_insensitive(agent_home: Path) -> None:
    host = RecordingHost(catalog=())
    host.parent_model = "Provider-Sub/Model-Parent"
    surviving, _ = asyncio.run(
        preflight.resolve_availability(("provider-sub/model-parent",), host)
    )
    assert surviving == ("provider-sub/model-parent",)


def test_a_searchable_model_still_survives_without_being_the_parent(agent_home: Path) -> None:
    host = RecordingHost(catalog=("provider-one/searchable",))
    host.parent_model = "provider-sub/model-parent"
    surviving, dropped = asyncio.run(
        preflight.resolve_availability(("provider-one/searchable",), host)
    )
    assert surviving == ("provider-one/searchable",)
    assert dropped == ()


def test_an_unreadable_parent_model_does_not_rescue_anything(agent_home: Path) -> None:
    """model.info failing must not turn every dropped entry into a survivor."""
    host = RecordingHost(catalog=())
    host.parent_model = None
    surviving, dropped = asyncio.run(
        preflight.resolve_availability(("provider-sub/model-parent",), host)
    )
    assert surviving == ()
    assert len(dropped) == 1


def test_the_exception_can_be_disabled_explicitly(agent_home: Path) -> None:
    host = RecordingHost(catalog=())
    host.parent_model = "provider-sub/model-parent"
    surviving, _ = asyncio.run(
        preflight.resolve_availability(("provider-sub/model-parent",), host, parent_selector="")
    )
    assert surviving == ()
