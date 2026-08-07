"""The spawn seam. Every one of these guards exists because the failure is silent.

A spawn with no model argument does not fail — it inherits the parent's model, which
is the expensive orchestrator. So a bug that drops the selector routes every
delegation to the most expensive model in the system and passes every gate while
doing it. That is the single most expensive failure this package can have, and it is
invisible without a guard here.
"""

from __future__ import annotations

import asyncio

import pytest

from sol_orchestration import host as host_module

from conftest import RecordingHost


def test_spawn_passes_exactly_a_name_and_a_selector() -> None:
    """The runtime rejects any other option outright; the adapter must not send one."""
    host = RecordingHost()
    handle = asyncio.run(host.spawn("do the thing", name="sol-d-0001", selector="provider-a/model-one"))
    assert host.spawns == [{"prompt": "do the thing", "name": "sol-d-0001", "selector": "provider-a/model-one"}]
    assert set(host.spawns[0]) == {"prompt", "name", "selector"}
    assert handle.model == "provider-a/model-one"
    assert handle.name == "sol-d-0001"


def test_spawn_without_a_selector_raises_before_reaching_the_host() -> None:
    host = RecordingHost()
    for missing in (None, "", "   "):
        with pytest.raises(ValueError):
            asyncio.run(host.spawn("do the thing", name="sol-d-0001", selector=missing))
    assert host.spawns == [], "the host was reached despite a missing selector"


def test_spawn_without_a_name_raises_before_reaching_the_host() -> None:
    host = RecordingHost()
    with pytest.raises(ValueError):
        asyncio.run(host.spawn("do the thing", name="", selector="provider-a/model-one"))
    assert host.spawns == []


def test_a_child_name_longer_than_the_runtime_allows_is_refused_locally() -> None:
    """The runtime caps a subagent name at 64 characters and raises above it."""
    host = RecordingHost()
    with pytest.raises(ValueError):
        asyncio.run(host.spawn("x", name="s" * 65, selector="provider-a/model-one"))
    assert host.spawns == []


def test_an_empty_prompt_is_refused_before_reaching_the_host() -> None:
    host = RecordingHost()
    with pytest.raises(ValueError):
        asyncio.run(host.spawn("   ", name="sol-d-0001", selector="provider-a/model-one"))
    assert host.spawns == []


def test_a_spawn_that_raises_propagates_rather_than_returning_a_null_handle() -> None:
    """Swallowing this would leave a delegation that looks dispatched and never was."""
    host = RecordingHost()
    host.spawn_failures = ("provider-a/gone",)
    with pytest.raises(RuntimeError):
        asyncio.run(host.spawn("x", name="sol-d-0001", selector="provider-a/gone"))


def test_the_spawn_guard_lives_on_the_base_class_so_no_host_can_bypass_it() -> None:
    """A guard implemented per-subclass is a guard one new subclass forgets."""
    assert "_spawn" in dir(host_module.Host)
    source = host_module.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "async def spawn(" in text
    assert "async def _spawn(" in text


def test_a_correction_is_addressed_by_role_and_name() -> None:
    host = RecordingHost()
    asyncio.run(host.send_message("fix the import", receiver_role="child", receiver_name="sol-d-0001"))
    assert host.messages == [
        {"message": "fix the import", "receiver_role": "child", "receiver_name": "sol-d-0001"}
    ]


def test_the_unavailable_host_refuses_a_spawn_with_the_import_failure() -> None:
    host = host_module.UnavailableHost("No module named 'rlm'")
    with pytest.raises(host_module.HostUnavailable) as raised:
        asyncio.run(host.spawn("x", name="sol-d-0001", selector="provider-a/model-one"))
    assert "rlm" in str(raised.value)
