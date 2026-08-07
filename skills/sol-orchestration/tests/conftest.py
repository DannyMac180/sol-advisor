"""Shared fixtures — chiefly the recording host double every later unit tests against.

The double is the reason no gate in this package spends model quota. It records every
host request the package makes, so a test can assert on the *shape of the traffic*
rather than only on the return value: that availability was resolved with one query
per allowlist entry and never with a single catalog enumeration, that a limit above
the runtime's cap was never sent, and later that a spawn carried an explicit selector.

``find_models`` deliberately reimplements the runtime's own matching and truncation
(``findRlmModelMatches`` in ``dist/core/rlm-runtime.js``: normalise, score exact then
prefix then partial, sort, slice to the limit). A double that returned everything it
was asked for would make the twenty-result cap invisible, which is precisely the
failure the per-entry query exists to prevent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from sol_orchestration import host as host_module

#: Mirrors the runtime's own MAX_RLM_MODEL_SEARCH_LIMIT.
RUNTIME_SEARCH_CAP = 20


def _normalise(value: str) -> str:
    """Mirror the runtime's normalizeModelSearchText."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


class RecordingHost(host_module.Host):
    """A host double that answers from a seeded catalog and records every request.

    Args:
        catalog: Selectors the authenticated model search should be able to return.
        subagents: Registry entries ``list_subagents`` should report.
        roster: Reply for ``agent_message.list_agents``; call ``without_roster`` to
            model a session where direct messaging is unavailable.
        observe: Legacy tripwire used to prove preflight does not depend on
            ``agent_observe.list``.
        failures: Selectors whose availability query should raise, standing in for an
            expired credential.
    """

    def __init__(
        self,
        catalog: tuple[str, ...] = (),
        subagents: tuple[host_module.Subagent, ...] = (),
        roster: dict[str, Any] | None = None,
        observe: bool = True,
        failures: tuple[str, ...] = (),
    ) -> None:
        self.catalog = catalog
        self.subagents_registry = subagents
        self.roster = roster or {
            "current": {"name": "orchestrator", "id": "sess-1", "depth": 0},
            "entries": [],
        }
        self._roster_unreachable = False
        self.observe = observe
        self.failures = failures
        #: What this session is itself running on. The host resolves a spawn against
        #: the authenticated list except for this selector, which it returns directly.
        self.parent_model: str | None = None
        #: Every ``find_models`` call, as ``(query, limit)`` — the enumeration tripwire.
        self.searches: list[tuple[str, int]] = []
        #: Every generic host request, as ``(type, payload)``.
        self.requests: list[tuple[str, dict[str, Any] | None]] = []
        #: Every spawn, as the full keyword set the adapter passed. A spawn carrying
        #: anything beyond a name and a selector is a defect the runtime would reject,
        #: and a spawn carrying no selector silently inherits the parent's model.
        self.spawns: list[dict[str, Any]] = []
        #: Every correction delivered, as the payload the bundled skill would send.
        self.messages: list[dict[str, Any]] = []
        #: Every child deleted, by target.
        self.deletions: list[str] = []
        #: Selectors whose spawn should raise, standing in for a model that went away
        #: between preflight and dispatch.
        self.spawn_failures: tuple[str, ...] = ()
        #: Child names that should be treated as gone when a correction is delivered.
        self.vanished: tuple[str, ...] = ()
        self._child_counter = 0

    def without_roster(self) -> RecordingHost:
        """Present as a session whose agent-family roster is unavailable."""
        self._roster_unreachable = True
        return self

    async def request(self, request_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.requests.append((request_type, payload))
        if request_type == "agent_message.list_agents":
            if self._roster_unreachable:
                raise RuntimeError("agent family roster is not available in this session")
            return dict(self.roster)
        if request_type == "model.info":
            if self.parent_model is None:
                return {"id": None, "provider": None, "input": []}
            provider, model_id = self.parent_model.split("/", 1)
            return {"id": model_id, "provider": provider, "input": []}
        if request_type == "agent_observe.list":
            if not self.observe:
                raise RuntimeError("agent observation is not available in this session")
            return {"agents": []}
        raise RuntimeError(f'no handler for host request "{request_type}" in this session')

    async def find_models(
        self, query: str = "", limit: int = host_module.MODEL_SEARCH_LIMIT
    ) -> tuple[host_module.ModelMatch, ...]:
        self.searches.append((query, limit))
        if limit > RUNTIME_SEARCH_CAP:
            raise RuntimeError(f"rlm.find_models limit must be an integer from 1 to {RUNTIME_SEARCH_CAP}")
        if query in self.failures:
            raise RuntimeError(f"authentication failed for {query}")
        normalised_query = _normalise(query.strip())
        scored: list[tuple[float, str]] = []
        for selector in self.catalog:
            fields = [_normalise(selector), _normalise(selector.split("/", 1)[-1])]
            score = float("inf") if normalised_query else 0.0
            if normalised_query:
                if normalised_query in fields:
                    score = float(fields.index(normalised_query))
                elif any(field.startswith(normalised_query) for field in fields):
                    score = 3.0
                elif any(normalised_query in field for field in fields):
                    score = 6.0
            if score != float("inf") or not normalised_query:
                scored.append((score, selector))
        scored.sort(key=lambda item: (item[0], item[1]))
        return tuple(
            host_module.ModelMatch(
                provider=selector.split("/", 1)[0],
                id=selector.split("/", 1)[1],
                name=selector.split("/", 1)[1],
                selector=selector,
            )
            for _, selector in scored[:limit]
        )

    async def list_subagents(self) -> tuple[host_module.Subagent, ...]:
        self.requests.append(("rlm.list_subagents", None))
        return self.subagents_registry

    async def _spawn(self, prompt: str, *, name: str, selector: str) -> host_module.SpawnHandle:
        # Record the whole keyword set, not just the two fields expected: a test can
        # only prove "nothing else was passed" if the double captures everything.
        self.spawns.append({"prompt": prompt, "name": name, "selector": selector})
        if selector in self.spawn_failures:
            raise RuntimeError(f"model {selector} is not available or not authenticated")
        self._child_counter += 1
        child_id = f"sub-{self._child_counter:04d}"
        handle = host_module.SpawnHandle(
            child_id=child_id,
            name=name,
            session_dir=Path(f"/tmp/{child_id}"),
            model=selector,
        )
        self.subagents_registry = self.subagents_registry + (
            host_module.Subagent(
                child_id=child_id,
                active_session_id=f"active-{child_id}",
                session_id=f"sess-{child_id}",
                session_name=name,
                session_dir=Path(f"/tmp/{child_id}"),
                status="running",
            ),
        )
        return handle

    async def send_message(self, message: str, *, receiver_role: str, receiver_name: str) -> dict[str, Any]:
        if self._roster_unreachable:
            raise RuntimeError("agent messaging is not available in this session")
        if receiver_name in self.vanished:
            raise RuntimeError(f"no child named {receiver_name} in this agent family")
        payload = {"message": message, "receiver_role": receiver_role, "receiver_name": receiver_name}
        self.messages.append(payload)
        return {"deliveryStatus": "delivered"}

    async def delete_subagent(self, target: str) -> dict[str, Any]:
        self.deletions.append(target)
        self.subagents_registry = tuple(
            entry for entry in self.subagents_registry if entry.child_id != target and entry.session_name != target
        )
        return {"subagent": {"rlm_child_id": target}, "outcome": "deleted"}

    def complete_child(self, name: str, status: str = "completed") -> None:
        """Move a child to a terminal registry status, as the host would."""
        self.subagents_registry = tuple(
            host_module.Subagent(
                child_id=entry.child_id,
                active_session_id=entry.active_session_id,
                session_id=entry.session_id,
                session_name=entry.session_name,
                session_dir=entry.session_dir,
                status=status if entry.session_name == name else entry.status,
            )
            for entry in self.subagents_registry
        )

    def forget_child(self, name: str) -> None:
        """Drop a child from the registry, as a lost or torn-down child would be."""
        self.vanished = self.vanished + (name,)
        self.subagents_registry = tuple(
            entry for entry in self.subagents_registry if entry.session_name != name
        )


class FakeClock:
    """A clock that only moves when a test moves it, so timeouts are provable fast."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class RecordingRecorder:
    """Stands in for the episode store the next-but-one workstream owns.

    It exists here so the ordering this workstream is responsible for — snapshot,
    then open the record, then spawn — is provable now rather than asserted later.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def open(self, delegation_id: str, record: dict[str, Any]) -> None:
        self.events.append(("open", delegation_id, dict(record)))

    def close(self, delegation_id: str, outcome: str, detail: dict[str, Any]) -> None:
        self.events.append(("close", delegation_id, {"outcome": outcome, **detail}))

    def opened(self) -> list[str]:
        return [delegation_id for kind, delegation_id, _ in self.events if kind == "open"]

    def closed(self) -> list[tuple[str, str]]:
        return [
            (delegation_id, payload["outcome"])
            for kind, delegation_id, payload in self.events
            if kind == "close"
        ]


class RecordingSnapshotter:
    """Stands in for the repository snapshot the evidence workstream owns."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.captures = 0

    def capture(self) -> object | None:
        self.captures += 1
        return {"snapshot": self.captures} if self.available else None


@pytest.fixture
def recording_host() -> RecordingHost:
    return RecordingHost()


@pytest.fixture
def agent_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A disposable Prime Agent home with both isolation variables redirected.

    Redirecting the home alone is not isolation: Prime Agent resolves the kernel venv
    from its own variable and otherwise from a path hardcoded off the real user home.
    """
    from sol_orchestration import home

    disposable = tmp_path / "agent-home"
    disposable.mkdir()
    monkeypatch.setenv(home.HOME_ENV_VAR, str(disposable))
    monkeypatch.setenv(home.KERNEL_VENV_ENV_VAR, str(tmp_path / "kernel-venv"))
    return disposable
