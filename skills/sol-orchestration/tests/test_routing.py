"""Routing is a pure function of declared features and the surviving set.

That purity is the point: it makes every case below testable with no session, no
host, and no quota. It is also what lets a fitted policy replace the hand-written
prior later by editing a config file rather than this package.
"""

from __future__ import annotations

import pytest

from sol_orchestration import config, contract, routing

ALPHA = "provider-one/alpha"
BETA = "provider-one/beta"
GAMMA = "provider-two/gamma"


def prior(rules: list[tuple[str, str, str]], default: str = ALPHA) -> config.RoutingPrior:
    return config.RoutingPrior(
        rules=tuple(config.RoutingRule(domain=d, difficulty=f, model=m) for d, f, m in rules),
        default=default,
    )


def test_a_matching_entry_selects_that_entrys_model() -> None:
    decision = routing.select(
        domain="python", difficulty="hard", prior=prior([("python", "hard", BETA)]), surviving=(ALPHA, BETA)
    )
    assert decision.selector == BETA
    assert decision.matched_rule is not None


def test_an_entry_naming_a_dropped_model_falls_through_to_the_next_applicable_one() -> None:
    """Falling through is the whole reason drops are resolved before selection."""
    decision = routing.select(
        domain="python",
        difficulty="hard",
        prior=prior([("python", "hard", GAMMA), ("python", "hard", BETA)]),
        surviving=(ALPHA, BETA),
    )
    assert decision.selector == BETA


def test_a_domain_with_no_match_takes_the_declared_default() -> None:
    decision = routing.select(
        domain="prose", difficulty="easy", prior=prior([("python", "hard", BETA)]), surviving=(ALPHA, BETA)
    )
    assert decision.selector == ALPHA
    assert decision.matched_rule is None


def test_selection_is_deterministic_for_identical_inputs() -> None:
    table = prior([("python", "hard", BETA), ("python", "hard", ALPHA)])
    first = routing.select(domain="python", difficulty="hard", prior=table, surviving=(ALPHA, BETA))
    for _ in range(20):
        assert routing.select(domain="python", difficulty="hard", prior=table, surviving=(ALPHA, BETA)) == first


def test_a_spec_missing_a_domain_is_rejected_before_selection() -> None:
    with pytest.raises(contract.Refusal) as raised:
        routing.select(domain="", difficulty="hard", prior=prior([]), surviving=(ALPHA,))
    assert "domain" in raised.value.remedy


def test_a_spec_missing_a_difficulty_is_rejected_before_selection() -> None:
    with pytest.raises(contract.Refusal) as raised:
        routing.select(domain="python", difficulty=None, prior=prior([]), surviving=(ALPHA,))
    assert "difficulty" in raised.value.remedy


def test_an_empty_surviving_set_refuses_naming_the_config_file() -> None:
    """Never a fallback to the session's own model: that is the expensive orchestrator."""
    with pytest.raises(contract.Refusal) as raised:
        routing.select(domain="python", difficulty="hard", prior=prior([]), surviving=())
    assert "config" in raised.value.artifact.lower()


def test_a_dropped_default_with_no_matching_rule_refuses_rather_than_guessing() -> None:
    with pytest.raises(contract.Refusal) as raised:
        routing.select(domain="prose", difficulty="easy", prior=prior([], default=GAMMA), surviving=(ALPHA,))
    assert GAMMA in raised.value.remedy


def test_the_decision_carries_the_surviving_set_size_it_chose_from() -> None:
    """Choosing among four candidates is not the same event as choosing among one."""
    decision = routing.select(
        domain="python", difficulty="hard", prior=prior([("python", "hard", BETA)]), surviving=(ALPHA, BETA, GAMMA)
    )
    assert decision.surviving_size == 3


def test_matching_is_case_insensitive_on_the_declared_features() -> None:
    decision = routing.select(
        domain="Python", difficulty="HARD", prior=prior([("python", "hard", BETA)]), surviving=(ALPHA, BETA)
    )
    assert decision.selector == BETA


def test_a_wildcard_difficulty_matches_any_difficulty_in_that_domain() -> None:
    decision = routing.select(
        domain="python", difficulty="trivial", prior=prior([("python", "*", BETA)]), surviving=(ALPHA, BETA)
    )
    assert decision.selector == BETA


def test_a_more_specific_rule_declared_first_wins_over_a_wildcard() -> None:
    """Rules are matched in declared order, so the operator controls precedence."""
    table = prior([("python", "hard", GAMMA), ("python", "*", BETA)])
    assert routing.select(domain="python", difficulty="hard", prior=table, surviving=(BETA, GAMMA)).selector == GAMMA
    assert routing.select(domain="python", difficulty="easy", prior=table, surviving=(BETA, GAMMA)).selector == BETA
