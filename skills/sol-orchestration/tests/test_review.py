"""The review child is the one place a model should read code — and the one that must not judge.

A starved orchestrator that never reads a file is a weak judge of a diff, and the
context that wrote the spec is a weak judge of the result. So a fresh child on the
operator-declared review model reads the actual changed files. Its findings are
evidence the orchestrator weighs, never a verdict: acceptance stays with the
orchestrator.

Its read-only posture is a prompt, not an enforced isolation, and the package must say
so in those words.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sol_orchestration import config, contract, review

from conftest import FakeClock, RecordingHost
from test_config import WELL_FORMED, seed


@pytest.fixture
def declared(agent_home: Path) -> config.Config:
    seed(agent_home, WELL_FORMED)
    return config.load()


def run_review(declared: config.Config, host: RecordingHost, clock: FakeClock, **kw):
    return asyncio.run(
        review.request(
            declared=declared,
            host=host,
            clock=clock,
            delegation_id="d-0001",
            changed_paths=("src/fetch.py",),
            objective="Add a retry to the fetch helper",
            **kw,
        )
    )


def test_the_review_child_runs_on_the_operator_declared_review_entry(declared, ) -> None:
    host, clock = RecordingHost(), FakeClock()
    review.write_findings("d-0001", {"findings": ["looks fine"]})
    run_review(declared, host, clock)
    assert host.spawns[0]["selector"] == declared.review_model


def test_the_review_child_never_runs_on_an_inferred_cheapest(declared) -> None:
    """The allowlist carries no price field, so "cheapest" has no meaning against it."""
    host, clock = RecordingHost(), FakeClock()
    review.write_findings("d-0001", {"findings": []})
    run_review(declared, host, clock)
    selector = host.spawns[0]["selector"]
    assert selector == declared.review_model
    assert selector in declared.allowlist


def test_the_review_prompt_names_the_changed_files_and_forbids_edits(declared) -> None:
    host, clock = RecordingHost(), FakeClock()
    review.write_findings("d-0001", {"findings": []})
    run_review(declared, host, clock)
    prompt = host.spawns[0]["prompt"]
    assert "src/fetch.py" in prompt
    assert "Add a retry to the fetch helper" in prompt
    lowered = prompt.lower()
    assert "do not edit" in lowered or "do not modify" in lowered
    assert "do not reply" in lowered


def test_the_review_prompt_never_claims_enforced_isolation(declared) -> None:
    host, clock = RecordingHost(), FakeClock()
    review.write_findings("d-0001", {"findings": []})
    run_review(declared, host, clock)
    lowered = host.spawns[0]["prompt"].lower()
    assert "sandbox" not in lowered
    assert "read-only environment" not in lowered


def test_the_package_reports_the_review_as_prompt_constrained(declared) -> None:
    host, clock = RecordingHost(), FakeClock()
    review.write_findings("d-0001", {"findings": []})
    result = run_review(declared, host, clock)
    assert result.posture == review.PROMPT_CONSTRAINED
    assert "prompt" in result.posture.lower()
    assert "enforced" not in result.posture.lower()


def test_findings_are_captured_as_untrusted_child_authored_text(declared) -> None:
    host, clock = RecordingHost(), FakeClock()
    review.write_findings("d-0001", {"findings": ["the retry is unbounded"]})
    result = run_review(declared, host, clock)
    assert result.findings == ("the retry is unbounded",)
    assert result.trusted is False


def test_a_review_child_that_does_not_report_degrades_rather_than_blocking(declared) -> None:
    """The review is evidence, not a gate; losing it must not lose the delegation."""
    host, clock = RecordingHost(), FakeClock()
    result = run_review(declared, host, clock, bound_seconds=30)
    assert result.findings == ()
    assert result.timed_out is True
    assert contract.CHILD_TIMEOUT in {entry.kind for entry in result.degradations}


def test_a_review_child_that_times_out_is_torn_down(declared) -> None:
    host, clock = RecordingHost(), FakeClock()
    run_review(declared, host, clock, bound_seconds=30)
    assert host.deletions, "a timed-out review child was left running"


def test_a_review_spawn_that_raises_degrades_rather_than_propagating(declared) -> None:
    host, clock = RecordingHost(), FakeClock()
    host.spawn_failures = (declared.review_model,)
    result = run_review(declared, host, clock)
    assert result.findings == ()
    assert {entry.kind for entry in result.degradations} & {
        contract.SPAWN_RAISED,
        contract.CHILD_TIMEOUT,
    }


def test_malformed_findings_are_not_read_as_findings(declared) -> None:
    """Child-authored bytes decide nothing; unparsable ones decide less."""
    host, clock = RecordingHost(), FakeClock()
    review.findings_path("d-0001").parent.mkdir(parents=True, exist_ok=True)
    review.findings_path("d-0001").write_text("not json at all", encoding="utf-8")
    result = run_review(declared, host, clock, bound_seconds=30)
    assert result.findings == ()


def test_the_review_child_is_named_distinctly_from_the_implementation_child(declared) -> None:
    host, clock = RecordingHost(), FakeClock()
    review.write_findings("d-0001", {"findings": []})
    run_review(declared, host, clock)
    name = host.spawns[0]["name"]
    assert "review" in name
    assert len(name) <= 64


def test_findings_are_evidence_and_carry_no_verdict(declared) -> None:
    """Acceptance belongs to the orchestrator; a reviewer that shipped would take it."""
    host, clock = RecordingHost(), FakeClock()
    review.write_findings("d-0001", {"findings": ["fine"], "verdict": "ship"})
    result = run_review(declared, host, clock)
    assert not hasattr(result, "verdict")
    prompt = host.spawns[0]["prompt"].lower()
    assert "ship" not in prompt or "do not" in prompt
