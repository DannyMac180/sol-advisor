"""One seam owns every host request, and it imports the runtime lazily.

Two properties are load-bearing. Without a single injection point the spawn path can
only ever be exercised live, and the rule that no automated gate spends model quota
becomes aspirational. Without the lazy import every module in this package fails to
import outside a kernel, because the runtime ships with Prime Agent rather than on
PyPI and the skill contract forbids declaring it as a dependency.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

import pytest

from sol_orchestration import host as host_module

from conftest import RUNTIME_SEARCH_CAP, RecordingHost


def test_the_module_imports_with_the_runtime_absent() -> None:
    """This whole suite runs outside a kernel, so the runtime is genuinely absent here.

    Asserting it in a subprocess as well keeps the guarantee honest if a future edit
    makes the import succeed only because some earlier test already imported it.
    """
    assert "rlm" not in sys.modules
    completed = subprocess.run(
        [sys.executable, "-c", "import sol_orchestration.host as h; print(h.MODEL_SEARCH_LIMIT)"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(RUNTIME_SEARCH_CAP)


def test_no_module_level_runtime_import_exists() -> None:
    """A module-level import would break the standalone run that proves this works."""
    from pathlib import Path

    source = Path(host_module.__file__).read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import rlm", "from rlm")):
            assert line.startswith((" ", "\t")), "the runtime import must sit inside a call"


def test_the_search_limit_never_exceeds_the_runtime_cap() -> None:
    """Above the cap the host raises, so a local guard turns a live failure into a test."""
    assert host_module.MODEL_SEARCH_LIMIT <= RUNTIME_SEARCH_CAP


def test_a_limit_above_the_cap_is_refused_before_the_host_sees_it() -> None:
    with pytest.raises(ValueError):
        host_module.checked_limit(RUNTIME_SEARCH_CAP + 1)
    assert host_module.checked_limit(RUNTIME_SEARCH_CAP) == RUNTIME_SEARCH_CAP


def test_the_injection_point_replaces_the_current_host() -> None:
    double = RecordingHost()
    with host_module.using(double):
        assert host_module.current() is double
    assert host_module.current() is not double


def test_the_default_host_outside_a_kernel_reports_unavailable() -> None:
    """Outside a kernel there is no comm bridge, so every request must say so plainly."""
    host_module.reset()
    with pytest.raises(host_module.HostUnavailable):
        asyncio.run(host_module.current().find_models("a/b"))


def test_an_unavailable_host_names_the_underlying_import_failure() -> None:
    host = host_module.UnavailableHost("No module named 'rlm'")
    with pytest.raises(host_module.HostUnavailable) as raised:
        asyncio.run(host.list_subagents())
    assert "rlm" in str(raised.value)


def test_the_recording_double_answers_an_exact_selector() -> None:
    host = RecordingHost(catalog=("provider-one/model-a", "provider-one/model-b"))
    matches = asyncio.run(host.find_models("provider-one/model-a"))
    assert matches[0].selector == "provider-one/model-a"
    assert host.searches == [("provider-one/model-a", host_module.MODEL_SEARCH_LIMIT)]


def test_the_recording_double_truncates_an_enumeration_at_the_cap() -> None:
    """The double must reproduce the cap, or the per-entry-query test proves nothing."""
    catalog = tuple(f"provider-one/model-{index:02d}" for index in range(RUNTIME_SEARCH_CAP + 5))
    host = RecordingHost(catalog=catalog)
    enumerated = asyncio.run(host.find_models(""))
    assert len(enumerated) == RUNTIME_SEARCH_CAP
    assert len(enumerated) < len(catalog)
