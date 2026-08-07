"""The single documented callable must work outside a kernel and degrade explicitly."""

import asyncio
import builtins
import os
from pathlib import Path
import subprocess
import sys

import pytest

import sol_orchestration


def call(**kwargs: object) -> str:
    return asyncio.run(sol_orchestration.run(**kwargs))  # type: ignore[arg-type]


def test_run_reports_the_resolved_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(sol_orchestration.home.HOME_ENV_VAR, str(tmp_path))
    report = call()
    assert str(tmp_path) in report
    assert sol_orchestration.home.HOME_ENV_VAR in report


def test_run_names_the_four_boundary_outcomes() -> None:
    report = call()
    for outcome in ("ship", "fix-first", "rethink", "abandon"):
        assert outcome in report


def test_run_reports_isolation_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Half-redirected is not isolated, and the report must not imply that it is."""
    monkeypatch.setenv(sol_orchestration.home.HOME_ENV_VAR, str(tmp_path / "home"))
    monkeypatch.delenv(sol_orchestration.home.KERNEL_VENV_ENV_VAR, raising=False)
    assert "isolated from the real installation: no" in call()

    monkeypatch.setenv(sol_orchestration.home.KERNEL_VENV_ENV_VAR, str(tmp_path / "venv"))
    assert "isolated from the real installation: yes" in call()


def test_run_flags_a_kernel_python_that_installs_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(sol_orchestration.home.KERNEL_PYTHON_ENV_VAR, str(tmp_path / "python"))
    report = call()
    assert sol_orchestration.home.KERNEL_PYTHON_ENV_VAR in report
    assert "SKILL.md" in report


def test_run_reports_runtime_degradation_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    """No kernel runtime must produce a stated degradation, never an exception."""
    real_import = builtins.__import__

    def refuse_runtime(name: str, *args: object, **kwargs: object) -> object:
        if name == sol_orchestration.RUNTIME_MODULE:
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", refuse_runtime)
    report = call()
    assert "degraded" in report
    assert "SKILL.md" in report


def test_an_importable_runtime_is_not_reported_as_verified_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failing trace imported rlm but its required host request was unavailable."""
    real_import = builtins.__import__

    def importable_runtime(name: str, *args: object, **kwargs: object) -> object:
        if name == sol_orchestration.RUNTIME_MODULE:
            return object()
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", importable_runtime)
    report = call()
    assert "runtime module: importable" in report
    assert "delegation capability: unverified" in report
    assert "in-kernel delegation is reachable" not in report
    assert "preflight.run" in report


def test_documented_modules_are_exposed_after_a_fresh_package_import() -> None:
    """Package-root examples must not depend on a prior submodule import."""
    package_root = Path(sol_orchestration.__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(package_root)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sol_orchestration; "
            "assert callable(sol_orchestration.preflight.run); "
            "assert callable(sol_orchestration.routing.select)",
        ],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_verbose_adds_the_interpreter_and_module_path() -> None:
    terse = call()
    verbose = call(verbose=True)
    assert len(verbose) > len(terse)
    assert sol_orchestration.__file__ in verbose


def test_run_is_the_documented_entry_point() -> None:
    """help(sol_orchestration) in the kernel shows run()'s signature and docstring."""
    import inspect
    import typing

    # inspect.iscoroutinefunction, not the asyncio alias: the alias is deprecated in
    # 3.14 and removed in 3.16, and the kernel venv tracks a recent Python.
    assert inspect.iscoroutinefunction(sol_orchestration.run)
    assert (sol_orchestration.run.__doc__ or "").strip()

    parameters = inspect.signature(sol_orchestration.run).parameters
    assert list(parameters) == ["verbose"]
    assert parameters["verbose"].default is False
    # The module uses PEP 563 annotations, so resolve them the way tyro and help() do.
    assert typing.get_type_hints(sol_orchestration.run)["verbose"] is bool
