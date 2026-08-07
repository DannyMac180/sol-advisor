"""The operator's declarations: the allowlist, the prior, the reviewer, the commands.

This is the only place in the system where a model name may appear. The package ships
no default allowlist and no prior naming a specific model, because a default would
reintroduce exactly the hardcoded role-to-model map this design exists to reject —
and it would do it invisibly, by being the value nobody ever edits.

The file lives under the Prime Agent home rather than in Prime Agent's own settings,
so removing this package stays a file delete instead of an edit to a file the runtime
owns. It is JSON rather than TOML because the package declares no dependencies and
``tomllib`` does not exist on the oldest interpreter this package supports.

Every absence here is a refusal that names the file to change. Nothing falls back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import home
from .contract import Refusal

#: Directory under the Prime Agent home that this package owns end to end.
CONFIG_DIR_NAME = "sol-orchestration"
CONFIG_FILE_NAME = "config.json"

#: A rule may name this in place of a difficulty to match every difficulty in a domain.
WILDCARD = "*"

_REQUIRED_KEYS = ("allowlist", "review_model", "verification_commands", "routing_prior")


def config_path() -> Path:
    """Return the config file's path under the Prime Agent home in force."""
    return home.agent_home() / CONFIG_DIR_NAME / CONFIG_FILE_NAME


@dataclass(frozen=True)
class RoutingRule:
    """One declared mapping from a task's features to a model."""

    domain: str
    difficulty: str
    model: str

    def matches(self, domain: str, difficulty: str) -> bool:
        """Report whether this rule applies to the given declared features."""
        if self.domain.lower() != domain.lower():
            return False
        return self.difficulty == WILDCARD or self.difficulty.lower() == difficulty.lower()


@dataclass(frozen=True)
class RoutingPrior:
    """The operator's hand-written prior, in declared order.

    Order is precedence: the first applicable rule whose model survived availability
    wins. Keeping it declarative is what lets a fitted policy replace it later by
    editing this file rather than this package.
    """

    rules: tuple[RoutingRule, ...]
    default: str


@dataclass(frozen=True)
class Config:
    """Everything the operator declared, validated against itself."""

    path: Path
    allowlist: tuple[str, ...]
    review_model: str
    verification_commands: dict[str, tuple[str, ...]]
    prior: RoutingPrior


def _refuse(path: Path, remedy: str) -> Refusal:
    return Refusal(artifact=str(path), remedy=remedy)


def _require_selector(path: Path, value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _refuse(path, f"{where} must be a non-empty provider/model selector string")
    selector = value.strip()
    provider, separator, model_id = selector.partition("/")
    if not separator or not provider.strip() or not model_id.strip():
        raise _refuse(
            path,
            f"{where} is {selector!r}; it must be a full provider/model selector, because the "
            "spawn resolves an exact provider/id match and a bare id can never resolve",
        )
    return selector


def load(path: Path | None = None) -> Config:
    """Read and validate the operator's config.

    Args:
        path: Read this file instead of resolving one under the Prime Agent home.
            Used by the gates, which run against a disposable home.

    Returns:
        The validated declarations.

    Raises:
        Refusal: The file is absent, unreadable, or internally inconsistent. The
            refusal names the file and what to change in it.
    """
    resolved = Path(path) if path is not None else config_path()

    if not resolved.exists():
        raise _refuse(
            resolved,
            "create this file declaring allowlist, review_model, verification_commands and "
            "routing_prior; this package ships no default allowlist, because a default would "
            "silently reintroduce a hardcoded model choice",
        )

    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError as error:
        raise _refuse(resolved, f"make this file readable; reading it failed with: {error}") from error
    except json.JSONDecodeError as error:
        raise _refuse(resolved, f"fix the JSON in this file; it failed to parse at line {error.lineno}") from error

    if not isinstance(document, dict):
        raise _refuse(resolved, "the top level of this file must be a JSON object")

    missing = [key for key in _REQUIRED_KEYS if key not in document]
    if missing:
        raise _refuse(resolved, f"add the missing key(s): {', '.join(missing)}")

    allowlist = _load_allowlist(resolved, document["allowlist"])
    review_model = _require_selector(resolved, document["review_model"], "review_model")
    if review_model not in allowlist:
        raise _refuse(
            resolved,
            f"review_model is {review_model!r}, which is not in the allowlist; the review child "
            "runs on a declared model like every other child",
        )

    commands = _load_commands(resolved, document["verification_commands"])
    prior = _load_prior(resolved, document["routing_prior"], allowlist)

    return Config(
        path=resolved,
        allowlist=allowlist,
        review_model=review_model,
        verification_commands=commands,
        prior=prior,
    )


def _load_allowlist(path: Path, raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise _refuse(path, "allowlist must be a non-empty list of provider/model selectors")
    entries = tuple(_require_selector(path, entry, f"allowlist entry {index}") for index, entry in enumerate(raw))
    duplicates = {entry for entry in entries if entries.count(entry) > 1}
    if duplicates:
        raise _refuse(
            path,
            f"remove the duplicated allowlist entr(y/ies): {', '.join(sorted(duplicates))}; a duplicate "
            "would double-count a model in the surviving-set size recorded on every episode",
        )
    return entries


def _load_commands(path: Path, raw: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw, dict) or not raw:
        raise _refuse(
            path,
            "verification_commands must declare at least one named command; a delegation with "
            "nothing to verify makes ship a rubber stamp",
        )
    commands: dict[str, tuple[str, ...]] = {}
    for name, argv in raw.items():
        if not isinstance(argv, list) or not argv or not all(isinstance(part, str) and part for part in argv):
            raise _refuse(path, f"verification_commands[{name!r}] must be a non-empty list of string arguments")
        commands[name] = tuple(argv)
    return commands


def _load_prior(path: Path, raw: object, allowlist: tuple[str, ...]) -> RoutingPrior:
    if not isinstance(raw, dict):
        raise _refuse(path, "routing_prior must be an object with a default and a rules list")
    if "default" not in raw:
        raise _refuse(path, "add routing_prior.default naming the model to use when no rule matches")

    default = _require_selector(path, raw["default"], "routing_prior.default")
    if default not in allowlist:
        raise _refuse(path, f"routing_prior.default names {default!r}, which is not in the allowlist")

    raw_rules = raw.get("rules", [])
    if not isinstance(raw_rules, list):
        raise _refuse(path, "routing_prior.rules must be a list")

    rules: list[RoutingRule] = []
    for index, entry in enumerate(raw_rules):
        where = f"routing_prior.rules[{index}]"
        if not isinstance(entry, dict):
            raise _refuse(path, f"{where} must be an object with domain, difficulty and model")
        for field in ("domain", "difficulty"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise _refuse(path, f"{where}.{field} must be a non-empty string")
        model = _require_selector(path, entry.get("model"), f"{where}.model")
        if model not in allowlist:
            raise _refuse(path, f"{where}.model names {model!r}, which is not in the allowlist")
        rules.append(
            RoutingRule(domain=entry["domain"].strip(), difficulty=entry["difficulty"].strip(), model=model)
        )

    return RoutingPrior(rules=tuple(rules), default=default)
