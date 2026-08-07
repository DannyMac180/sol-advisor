"""The episode corpus is this epic's deliverable, so its honesty is the thing to get right.

Everything else in this package exists so that a later plan can fit a routing policy
against real evidence instead of intuition. A record that is missing, collapsed, or
confounded cannot be backfilled — the delegation it described is gone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sol_orchestration import contract, episodes, evidence

from test_config import WELL_FORMED, seed


def a_round(index: int = 0, exit_status: int | None = 0, **kw) -> episodes.RoundOutcome:
    fields = {
        "round_index": index,
        "verification_exit_status": exit_status,
        "verification_timed_out": False,
        "ownership_violation": False,
        "integrity_failure": False,
        "empty_diff": False,
        "wall_clock_seconds": 12.5,
    }
    fields.update(kw)
    return episodes.RoundOutcome(**fields)


def write_transcript(home: Path, session_id: str, entries: list[dict]) -> Path:
    sessions = home / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    path = sessions / f"{session_id}.jsonl"
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    return path


def assistant(input_tokens: int, output_tokens: int, cost: float, level: str | None = None) -> dict:
    return {
        "type": "message",
        "message": {
            "role": "assistant",
            "model": "model-one",
            "provider": "provider-a",
            "usage": {
                "input": input_tokens,
                "output": output_tokens,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": input_tokens + output_tokens,
                "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0, "cacheWrite": 0, "total": cost},
            },
        },
    }


# --- the store ----------------------------------------------------------------


def test_the_store_sits_under_the_agent_home_and_outside_any_git_repository(agent_home: Path) -> None:
    path = episodes.store_path()
    assert agent_home in path.parents
    for parent in [path] + list(path.parents):
        assert not (parent / ".git").exists(), f"the episode store lives inside a git repo at {parent}"


def test_the_store_path_is_the_one_the_evidence_layer_hashes(agent_home: Path) -> None:
    """A tamper check watching a different file from the one being written is theatre."""
    assert episodes.store_path() == evidence.episode_store_path()


def test_appending_never_rewrites_or_truncates_an_existing_record(agent_home: Path) -> None:
    episodes.append({"delegation_id": "d-1", "schema_version": episodes.SCHEMA_VERSION})
    first = episodes.store_path().read_text(encoding="utf-8")
    episodes.append({"delegation_id": "d-2", "schema_version": episodes.SCHEMA_VERSION})
    after = episodes.store_path().read_text(encoding="utf-8")
    assert after.startswith(first)
    assert len(after.splitlines()) == 2


def test_every_record_carries_a_schema_version(agent_home: Path) -> None:
    record = episodes.close_record(
        opened=episodes.open_record(
            delegation_id="d-1", selector="provider-a/model-one", surviving_size=3,
            domain="python", difficulty="hard", ownership=("src/a.py",),
            effort_at_spawn="high", child_name="sol-d-1",
        ),
        outcome="ship",
        rounds=(a_round(),),
    )
    assert record["schema_version"] == episodes.SCHEMA_VERSION
    assert isinstance(record["schema_version"], int)


# --- confounder controls ------------------------------------------------------


def test_every_record_carries_all_four_confounder_controls(agent_home: Path) -> None:
    """Without these the corpus cannot separate a model from the conditions it ran under."""
    opened = episodes.open_record(
        delegation_id="d-1", selector="provider-a/model-one", surviving_size=4,
        domain="python", difficulty="hard", ownership=("src/a.py",), effort_at_spawn="xhigh",
        child_name="sol-d-1",
    )
    record = episodes.close_record(opened=opened, outcome="ship", rounds=(a_round(),),
                                   child_effort_clamped="high")
    assert record["selector"] == "provider-a/model-one"
    assert record["effort_at_spawn"] == "xhigh"
    assert record["child_effort_clamped"] == "high"
    assert record["surviving_allowlist_size"] == 4


def test_the_clamped_child_effort_is_recorded_separately_from_the_parents(agent_home: Path) -> None:
    """A child receives the parent's level clamped to what its own model supports."""
    opened = episodes.open_record(
        delegation_id="d-1", selector="a/b", surviving_size=1, domain="x", difficulty="y",
        ownership=("f",), effort_at_spawn="xhigh", child_name="sol-d-1",
    )
    record = episodes.close_record(opened=opened, outcome="ship", rounds=(a_round(),),
                                   child_effort_clamped="medium")
    assert record["effort_at_spawn"] != record["child_effort_clamped"]


def test_the_routing_features_ride_on_the_record(agent_home: Path) -> None:
    opened = episodes.open_record(
        delegation_id="d-1", selector="a/b", surviving_size=2, domain="python",
        difficulty="hard", ownership=("src/a.py", "src/b.py"), effort_at_spawn="high",
        child_name="sol-d-1",
    )
    assert opened["domain"] == "python"
    assert opened["difficulty"] == "hard"
    assert opened["ownership"] == ["src/a.py", "src/b.py"]


# --- per-round outcomes -------------------------------------------------------


def test_per_round_outcomes_are_recoverable_and_not_collapsed(agent_home: Path) -> None:
    """First-try pass and pass-after-three-corrections must be distinguishable."""
    opened = episodes.open_record(
        delegation_id="d-1", selector="a/b", surviving_size=1, domain="x", difficulty="y",
        ownership=("f",), effort_at_spawn="high", child_name="sol-d-1",
    )
    rounds = (
        a_round(0, exit_status=1),
        a_round(1, exit_status=1, ownership_violation=True),
        a_round(2, exit_status=1),
        a_round(3, exit_status=0),
    )
    record = episodes.close_record(opened=opened, outcome="ship", rounds=rounds)
    assert len(record["rounds"]) == 4
    assert [entry["verification_exit_status"] for entry in record["rounds"]] == [1, 1, 1, 0]
    assert record["rounds"][1]["ownership_violation"] is True
    assert record["correction_count"] == 3


def test_a_first_try_pass_is_distinguishable_from_a_recovered_one(agent_home: Path) -> None:
    opened = episodes.open_record(
        delegation_id="d-1", selector="a/b", surviving_size=1, domain="x", difficulty="y",
        ownership=("f",), effort_at_spawn="high", child_name="sol-d-1",
    )
    clean = episodes.close_record(opened=opened, outcome="ship", rounds=(a_round(0, 0),))
    recovered = episodes.close_record(
        opened=opened, outcome="ship",
        rounds=(a_round(0, 1), a_round(1, 1), a_round(2, 0)),
    )
    assert clean["correction_count"] == 0
    assert recovered["correction_count"] == 2
    assert clean["rounds"] != recovered["rounds"]


def test_the_outcome_vector_is_built_only_from_deterministic_signals(agent_home: Path) -> None:
    """A model-graded reward would make every training example cost a model call."""
    source = Path(episodes.__file__).read_text(encoding="utf-8")
    for forbidden in ("host_request", "find_models", "spawn(", "import rlm"):
        assert forbidden not in source, f"episodes.py reaches a model via {forbidden}"


# --- cost ---------------------------------------------------------------------


def test_per_child_cost_is_read_from_the_childs_own_transcript(agent_home: Path) -> None:
    write_transcript(
        agent_home,
        "child-session-1",
        [
            {"type": "session", "version": 3, "id": "child-session-1"},
            assistant(1000, 100, 0.011),
            assistant(500, 50, 0.0055),
        ],
    )
    usage, degradation = episodes.read_usage("child-session-1")
    assert degradation is None
    assert usage.input_tokens == 1500
    assert usage.output_tokens == 150
    assert usage.total_tokens == 1650
    assert usage.cost_total == pytest.approx(0.0165)


def test_an_unreadable_cost_signal_yields_a_record_without_the_cost_term(agent_home: Path) -> None:
    """Never an exception, never a silent zero — a zero would read as a free delegation."""
    usage, degradation = episodes.read_usage("no-such-session")
    assert usage is None
    assert degradation is not None
    assert degradation.kind == contract.UNREADABLE_COST

    opened = episodes.open_record(
        delegation_id="d-1", selector="a/b", surviving_size=1, domain="x", difficulty="y",
        ownership=("f",), effort_at_spawn="high", child_name="sol-d-1",
    )
    record = episodes.close_record(opened=opened, outcome="ship", rounds=(a_round(),), usage=None,
                                   degradations=(degradation,))
    assert "cost_total" not in record
    assert "total_tokens" not in record
    assert contract.UNREADABLE_COST in {entry["kind"] for entry in record["degradations"]}


def test_a_transcript_with_no_usage_blocks_degrades_rather_than_reporting_zero(
    agent_home: Path,
) -> None:
    write_transcript(agent_home, "child-2", [{"type": "session", "version": 3, "id": "child-2"}])
    usage, degradation = episodes.read_usage("child-2")
    assert usage is None
    assert degradation is not None


def test_a_readable_cost_signal_lands_on_the_record(agent_home: Path) -> None:
    write_transcript(agent_home, "child-3", [assistant(200, 20, 0.003)])
    usage, _ = episodes.read_usage("child-3")
    opened = episodes.open_record(
        delegation_id="d-1", selector="a/b", surviving_size=1, domain="x", difficulty="y",
        ownership=("f",), effort_at_spawn="high", child_name="sol-d-1",
    )
    record = episodes.close_record(opened=opened, outcome="ship", rounds=(a_round(),), usage=usage)
    assert record["cost_total"] == pytest.approx(0.003)
    assert record["total_tokens"] == 220


def test_the_childs_clamped_effort_is_read_from_the_same_transcript(agent_home: Path) -> None:
    write_transcript(
        agent_home,
        "child-4",
        [
            {"type": "thinking_level_change", "thinkingLevel": "xhigh"},
            {"type": "thinking_level_change", "thinkingLevel": "high"},
            assistant(10, 1, 0.001),
        ],
    )
    assert episodes.read_clamped_effort("child-4") == "high"


def test_an_absent_child_transcript_gives_no_clamped_effort_rather_than_a_guess(
    agent_home: Path,
) -> None:
    assert episodes.read_clamped_effort("missing") is None


# --- outcomes -----------------------------------------------------------------


@pytest.mark.parametrize("outcome", ["ship", "fix-first", "rethink", "abandon"])
def test_every_boundary_outcome_can_close_a_record(agent_home: Path, outcome: str) -> None:
    opened = episodes.open_record(
        delegation_id="d-1", selector="a/b", surviving_size=1, domain="x", difficulty="y",
        ownership=("f",), effort_at_spawn="high", child_name="sol-d-1",
    )
    assert episodes.close_record(opened=opened, outcome=outcome, rounds=())["outcome"] == outcome


def test_an_outcome_outside_the_declared_four_is_refused(agent_home: Path) -> None:
    opened = episodes.open_record(
        delegation_id="d-1", selector="a/b", surviving_size=1, domain="x", difficulty="y",
        ownership=("f",), effort_at_spawn="high", child_name="sol-d-1",
    )
    with pytest.raises(ValueError):
        episodes.close_record(opened=opened, outcome="looks-good", rounds=())


def test_a_restarted_context_record_links_back_and_is_marked(agent_home: Path) -> None:
    opened = episodes.open_record(
        delegation_id="d-2", selector="a/b", surviving_size=1, domain="x", difficulty="y",
        ownership=("f",), effort_at_spawn="high", child_name="sol-d-2",
        restarted_from="d-1",
    )
    assert opened["restarted_from"] == "d-1"
    assert opened["restarted_context"] is True


def test_a_normal_record_is_not_marked_restarted(agent_home: Path) -> None:
    opened = episodes.open_record(
        delegation_id="d-1", selector="a/b", surviving_size=1, domain="x", difficulty="y",
        ownership=("f",), effort_at_spawn="high", child_name="sol-d-1",
    )
    assert opened["restarted_from"] is None
    assert opened["restarted_context"] is False


# --- what the live smoke run taught us about where a child's transcript lives ---


def test_a_childs_transcript_is_found_under_its_own_session_dir(agent_home: Path) -> None:
    """A child's transcript is NOT in <home>/sessions/. The live smoke run proved it.

    The runtime nests it under the parent's artifact directory, as
    <home>/session-artifacts/<parent-id>/sub-<child-id>/<child-session-id>.jsonl. The
    first real delegation recorded its cost as unreadable purely because this resolved
    to the root-session layout — a defect no fixture caught, because every fixture
    wrote the transcript where the code already looked.
    """
    child_session_id = "019fdd1e-5ead-779c-a84a-1ebc8f4168a0"
    child_dir = agent_home / "session-artifacts" / "019fdd1e-parent" / "sub-b9dca848"
    child_dir.mkdir(parents=True)
    (child_dir / f"{child_session_id}.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"type": "thinking_level_change", "thinkingLevel": "high"}),
                json.dumps(assistant(140, 2835, 0.046319)),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    # Without the session dir it is not findable, and that is reported honestly.
    usage, degradation = episodes.read_usage(child_session_id)
    assert usage is None
    assert degradation.kind == contract.UNREADABLE_COST

    # With it, the real numbers come back.
    usage, degradation = episodes.read_usage(child_session_id, session_dir=child_dir)
    assert degradation is None
    assert usage.input_tokens == 140
    assert usage.output_tokens == 2835
    assert usage.cost_total == pytest.approx(0.046319)
    assert episodes.read_clamped_effort(child_session_id, session_dir=child_dir) == "high"


def test_a_root_session_transcript_still_resolves_without_a_session_dir(agent_home: Path) -> None:
    write_transcript(agent_home, "root-1", [assistant(10, 20, 0.001)])
    usage, degradation = episodes.read_usage("root-1")
    assert degradation is None
    assert usage.total_tokens == 30
