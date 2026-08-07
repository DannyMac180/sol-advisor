"""The home resolver is what every disposable-home gate downstream depends on."""

from pathlib import Path

import pytest

from sol_orchestration import home


def test_environment_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(home.HOME_ENV_VAR, str(tmp_path))
    assert home.agent_home() == tmp_path
    assert home.home_source() == home.HOME_ENV_VAR


def test_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(home.HOME_ENV_VAR, raising=False)
    assert home.agent_home() == Path.home() / ".prime" / "agent"
    assert home.home_source() == "default"


def test_override_expands_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(home.HOME_ENV_VAR, "~/disposable-home")
    assert home.agent_home() == Path.home() / "disposable-home"


def test_blank_override_is_not_an_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty or whitespace variable must not resolve the home to the process cwd."""
    monkeypatch.setenv(home.HOME_ENV_VAR, "   ")
    assert home.agent_home() == Path.home() / ".prime" / "agent"
    assert home.home_source() == "default"


def test_relative_override_is_made_absolute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(home.HOME_ENV_VAR, "relative-home")
    resolved = home.agent_home()
    assert resolved.is_absolute()
    assert resolved == tmp_path / "relative-home"


def test_kernel_venv_is_resolved_separately(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirecting the home must not be mistaken for redirecting the kernel venv.

    Prime Agent reads the venv from PRIME_AGENT_KERNEL_VENV and otherwise falls back
    to a path hardcoded off the real user home, never to the redirected agent home.
    Isolation therefore needs both variables, and the resolver reports them
    independently so a caller cannot mistake one for the other.
    """
    monkeypatch.setenv(home.HOME_ENV_VAR, str(tmp_path / "home"))
    monkeypatch.delenv(home.KERNEL_VENV_ENV_VAR, raising=False)
    assert home.kernel_venv() == Path.home() / ".prime" / "agent" / "kernel-venv"
    assert home.kernel_venv() != home.agent_home() / "kernel-venv"
    assert home.is_isolated() is False

    monkeypatch.setenv(home.KERNEL_VENV_ENV_VAR, str(tmp_path / "venv"))
    assert home.kernel_venv() == tmp_path / "venv"
    assert home.is_isolated() is True
