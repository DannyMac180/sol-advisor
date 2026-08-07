"""Select a model for one delegation from the surviving allowlist.

Selection is a pure function of the declared features and the surviving set. That is
not an aesthetic choice: it is what makes every routing case testable with no session,
no host, and no quota, and it is what lets a fitted policy replace the hand-written
prior later by editing a config file rather than this module.

There is no fallback to the session's own model. That model is the expensive
orchestrator, so a fallback would quietly route the cheap tier to the most expensive
model in the system and still pass every gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import RoutingPrior, RoutingRule
from .contract import Refusal


@dataclass(frozen=True)
class Decision:
    """One routing decision, carrying what the episode needs to be un-confounded."""

    selector: str
    matched_rule: RoutingRule | None
    #: How many candidates the choice was made from. Choosing among four is not the
    #: same event as choosing among one, and the corpus cannot tell them apart later
    #: unless the size is recorded at the moment of the choice.
    surviving_size: int


def select(
    domain: str | None,
    difficulty: str | None,
    prior: RoutingPrior,
    surviving: tuple[str, ...],
    config_artifact: str = "the sol-orchestration config file",
) -> Decision:
    """Choose a model for a delegation.

    Args:
        domain: The task domain the orchestrator declared on the spec.
        difficulty: The difficulty the orchestrator declared on the spec.
        prior: The operator's declared prior, in precedence order.
        surviving: Allowlist entries that survived the availability check.
        config_artifact: Named in a refusal so the operator knows what to edit.

    Returns:
        The decision, including the surviving-set size it was made from.

    Raises:
        Refusal: A feature is missing, nothing survived, or no applicable rule and no
            default names a surviving model.
    """
    if not domain or not str(domain).strip():
        raise Refusal(
            artifact="the delegation spec",
            remedy="declare a domain on the spec; routing on a guessed domain would record a "
            "routing feature that was never actually declared",
        )
    if not difficulty or not str(difficulty).strip():
        raise Refusal(
            artifact="the delegation spec",
            remedy="declare a difficulty on the spec; routing on a guessed difficulty would "
            "record a routing feature that was never actually declared",
        )
    if not surviving:
        raise Refusal(
            artifact=config_artifact,
            remedy="declare at least one allowlist entry that is reachable under the active "
            "credentials; this package does not route to the session's own model, which is "
            "the expensive orchestrator",
        )

    domain = str(domain).strip()
    difficulty = str(difficulty).strip()
    available = set(surviving)

    for rule in prior.rules:
        if rule.matches(domain, difficulty) and rule.model in available:
            return Decision(selector=rule.model, matched_rule=rule, surviving_size=len(surviving))

    if prior.default in available:
        return Decision(selector=prior.default, matched_rule=None, surviving_size=len(surviving))

    raise Refusal(
        artifact=config_artifact,
        remedy=f"no rule applies to domain {domain!r} at difficulty {difficulty!r}, and the declared "
        f"default {prior.default!r} did not survive the availability check; add a rule naming a "
        "surviving model, or declare a default that is reachable",
    )
