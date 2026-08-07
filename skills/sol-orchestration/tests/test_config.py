"""The operator's config is the only place a model name may appear.

No default allowlist ships. A prior that named a specific model would reintroduce
exactly the hardcoded role-to-model map this design exists to reject, so every
absence here is a refusal naming the file to change — never a fallback.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sol_orchestration import config, contract

WELL_FORMED = {
    "allowlist": ["openai-codex/gpt-5.6-terra", "openai-codex/gpt-5.6-luna"],
    "review_model": "openai-codex/gpt-5.6-luna",
    "verification_commands": {"pytest": ["python", "-m", "pytest", "-q"]},
    "routing_prior": {
        "default": "openai-codex/gpt-5.6-terra",
        "rules": [{"domain": "python", "difficulty": "hard", "model": "openai-codex/gpt-5.6-luna"}],
    },
}


def seed(home: Path, document: object) -> Path:
    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_config_path_sits_under_the_resolved_agent_home(agent_home: Path) -> None:
    assert config.config_path().parent.parent == agent_home
    assert config.config_path().name.endswith(".json")


def test_a_well_formed_config_loads_every_declared_field(agent_home: Path) -> None:
    seed(agent_home, WELL_FORMED)
    loaded = config.load()
    assert loaded.allowlist == ("openai-codex/gpt-5.6-terra", "openai-codex/gpt-5.6-luna")
    assert loaded.review_model == "openai-codex/gpt-5.6-luna"
    assert loaded.verification_commands["pytest"] == ("python", "-m", "pytest", "-q")
    assert loaded.prior.default == "openai-codex/gpt-5.6-terra"
    assert loaded.prior.rules[0].domain == "python"
    assert loaded.prior.rules[0].difficulty == "hard"
    assert loaded.prior.rules[0].model == "openai-codex/gpt-5.6-luna"


def test_a_missing_config_refuses_naming_the_expected_path(agent_home: Path) -> None:
    with pytest.raises(contract.Refusal) as raised:
        config.load()
    assert str(config.config_path()) in raised.value.artifact
    assert raised.value.remedy


def test_no_default_allowlist_ships(agent_home: Path) -> None:
    """The package must carry no model name of its own, anywhere in its source."""
    package_root = Path(config.__file__).parent
    for module in package_root.rglob("*.py"):
        text = module.read_text(encoding="utf-8")
        assert "gpt-5.6" not in text, f"{module} names a specific model"
        assert "claude-" not in text, f"{module} names a specific model"


def test_an_empty_allowlist_refuses_rather_than_loading(agent_home: Path) -> None:
    seed(agent_home, {**WELL_FORMED, "allowlist": []})
    with pytest.raises(contract.Refusal) as raised:
        config.load()
    assert str(config.config_path()) in raised.value.artifact


def test_a_missing_required_key_refuses_naming_the_key(agent_home: Path) -> None:
    document = {key: value for key, value in WELL_FORMED.items() if key != "review_model"}
    seed(agent_home, document)
    with pytest.raises(contract.Refusal) as raised:
        config.load()
    assert "review_model" in raised.value.remedy


def test_malformed_json_refuses_naming_the_file(agent_home: Path) -> None:
    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(contract.Refusal) as raised:
        config.load()
    assert str(path) in raised.value.artifact


def test_a_review_model_outside_the_allowlist_refuses(agent_home: Path) -> None:
    """The review child runs on an allowlist model; naming one outside it is a typo."""
    seed(agent_home, {**WELL_FORMED, "review_model": "openai-codex/not-declared"})
    with pytest.raises(contract.Refusal) as raised:
        config.load()
    assert "review_model" in raised.value.remedy


def test_a_prior_naming_a_model_outside_the_allowlist_refuses(agent_home: Path) -> None:
    document = {
        **WELL_FORMED,
        "routing_prior": {"default": "openai-codex/undeclared", "rules": []},
    }
    seed(agent_home, document)
    with pytest.raises(contract.Refusal) as raised:
        config.load()
    assert "openai-codex/undeclared" in raised.value.remedy


def test_an_empty_verification_command_set_refuses(agent_home: Path) -> None:
    """A delegation with nothing to verify makes ship a rubber stamp."""
    seed(agent_home, {**WELL_FORMED, "verification_commands": {}})
    with pytest.raises(contract.Refusal):
        config.load()


def test_an_explicit_path_overrides_the_home_resolution(agent_home: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(json.dumps(WELL_FORMED), encoding="utf-8")
    assert config.load(elsewhere).allowlist == tuple(WELL_FORMED["allowlist"])


def test_a_duplicated_allowlist_entry_refuses(agent_home: Path) -> None:
    """Duplicates would double-count a model in the surviving-set feature."""
    seed(agent_home, {**WELL_FORMED, "allowlist": ["a/b", "a/b"], "review_model": "a/b",
                      "routing_prior": {"default": "a/b", "rules": []}})
    with pytest.raises(contract.Refusal):
        config.load()


def test_an_allowlist_entry_without_a_provider_prefix_refuses(agent_home: Path) -> None:
    """The spawn resolves an exact provider/id selector; a bare id can never match."""
    seed(agent_home, {**WELL_FORMED, "allowlist": ["gpt-only-id"], "review_model": "gpt-only-id",
                      "routing_prior": {"default": "gpt-only-id", "rules": []}})
    with pytest.raises(contract.Refusal) as raised:
        config.load()
    assert "provider/" in raised.value.remedy
