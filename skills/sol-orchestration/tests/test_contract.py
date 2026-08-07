"""The shared vocabulary: what the package refuses with, and what it degrades with.

A refusal and a degradation are not two flavours of the same thing. A refusal stops
the delegation and names the artifact the operator must change. A degradation lets it
proceed and is carried into every packet and every episode, so the corpus records the
conditions a result was produced under instead of quietly losing them.
"""

from __future__ import annotations

import pytest

from sol_orchestration import contract


def test_refusal_names_both_the_artifact_and_the_remedy() -> None:
    refusal = contract.Refusal(artifact="/home/x/config.json", remedy="declare at least one allowlist entry")
    assert refusal.artifact == "/home/x/config.json"
    assert refusal.remedy == "declare at least one allowlist entry"
    assert "/home/x/config.json" in str(refusal)
    assert "declare at least one allowlist entry" in str(refusal)


def test_a_refusal_without_a_remedy_is_not_constructible() -> None:
    """A refusal that does not say what to change is a dead end, not a refusal."""
    with pytest.raises(ValueError):
        contract.Refusal(artifact="/home/x/config.json", remedy="")


def test_degradation_kinds_cover_the_stated_vocabulary() -> None:
    """R32 names the minimum set every packet and episode must be able to report."""
    required = {
        contract.PYTHON_LOAD_FAILED,
        contract.UNREADABLE_COST,
        contract.UNREADABLE_EFFORT,
        contract.ALLOWLIST_ENTRIES_DROPPED,
        contract.PACKET_TRUNCATED,
        contract.NO_VERIFICATION_COMMAND,
        contract.REDACTION_OCCURRED,
        contract.CHILD_TIMEOUT,
        contract.SPAWN_RAISED,
        contract.UNRECOGNIZED_RUNTIME_VERSION,
        contract.RESTART_ONLY_CORRECTIONS,
    }
    assert required <= contract.DEGRADATION_KINDS


def test_an_unknown_degradation_kind_is_rejected() -> None:
    """Free-text kinds would make the corpus unqueryable one typo at a time."""
    with pytest.raises(ValueError):
        contract.Degradation(kind="something-went-wrong", detail="...")


def test_degradation_serialises_to_a_stable_pair() -> None:
    degradation = contract.Degradation(kind=contract.UNREADABLE_EFFORT, detail="no transcript")
    assert degradation.as_dict() == {"kind": contract.UNREADABLE_EFFORT, "detail": "no transcript"}
