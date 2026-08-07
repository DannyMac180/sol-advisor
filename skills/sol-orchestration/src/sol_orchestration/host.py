"""The one seam every host request passes through.

Two properties are load-bearing, and both are easy to lose by accident.

**A single injection point.** Without it the spawn path can only be exercised live,
and the rule that no automated gate spends model quota becomes aspirational. With it,
every later unit tests against a recording double that can assert on the *shape* of
the traffic — that availability was resolved one entry at a time, that a spawn
carried an explicit selector — not merely on return values.

**A lazy runtime import.** The runtime ships with Prime Agent and is not published on
PyPI, and the skill contract forbids declaring it as a dependency. A module-level
``import rlm`` would therefore make this package unimportable everywhere except a
kernel, including the standalone test run that proves it works. Every import here
sits inside a call, and the failure is reported as an unavailable host rather than an
ImportError escaping from module load.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The runtime rejects a search limit above its own cap of twenty, so this package
#: keeps its own copy and refuses locally: a live error is worth turning into a test.
MODEL_SEARCH_LIMIT = 20

#: The bundled runtime module. Imported lazily inside calls, never at module level.
RUNTIME_MODULE = "rlm"

#: The runtime caps a child session name at this length and raises above it.
CHILD_NAME_MAX_LENGTH = 64


class HostUnavailable(RuntimeError):
    """The Prime Agent host bridge is not reachable from this process."""


def checked_limit(limit: int) -> int:
    """Return ``limit`` if the host would accept it, else raise before the request.

    Raises:
        ValueError: The limit is outside the range the runtime accepts.
    """
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError(f"model search limit must be an int, got {type(limit).__name__}")
    if limit < 1 or limit > MODEL_SEARCH_LIMIT:
        raise ValueError(f"model search limit must be an integer from 1 to {MODEL_SEARCH_LIMIT}, got {limit}")
    return limit


@dataclass(frozen=True)
class ModelMatch:
    """One authenticated model, as the host's search reports it."""

    provider: str
    id: str
    name: str
    selector: str


@dataclass(frozen=True)
class SpawnHandle:
    """What a spawn returns: an admission, never the child's answer.

    The call is asynchronous. It resolves once the child's task is admitted, so
    dispatch and collection are separate orchestrator turns with a ledger between
    them — and a delegation that crashes between the two leaves a record rather than
    vanishing.
    """

    child_id: str
    name: str
    session_dir: Path
    model: str


@dataclass(frozen=True)
class Subagent:
    """One entry in the parent session's child registry.

    ``active_session_id`` is the retention signal and the only one that matters for
    corrections: the host populates it solely for daemon-backed children, and the
    bundled agent-message skill addresses a child only when it is present.
    """

    child_id: str
    active_session_id: str | None
    session_id: str | None
    session_name: str
    session_dir: Path
    status: str


class Host:
    """The host requests this package is allowed to make.

    Subclasses answer them from the live runtime, from a recording double, or by
    reporting the bridge as unavailable. Nothing outside this module talks to the
    runtime directly.
    """

    async def request(self, request_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Issue a typed host request and return the host's reply."""
        raise NotImplementedError

    async def find_models(self, query: str = "", limit: int = MODEL_SEARCH_LIMIT) -> tuple[ModelMatch, ...]:
        """Search the authenticated model catalog, bounded by the host's own cap."""
        raise NotImplementedError

    async def list_subagents(self) -> tuple[Subagent, ...]:
        """List the direct children the parent session currently retains."""
        raise NotImplementedError

    async def parent_selector(self) -> str | None:
        """Return the ``provider/id`` this session is itself running on.

        Load-bearing for availability: the host resolves a spawn against the
        authenticated-model list **except** when the requested selector equals the
        parent's own, which it returns directly. So the parent's model is always
        spawnable even when the catalog omits it, and a search-only availability check
        would drop the one entry that is guaranteed to work.
        """
        try:
            info = await self.request("model.info")
        except Exception:
            return None
        provider, model_id = info.get("provider"), info.get("id")
        if not provider or not model_id:
            return None
        return f"{provider}/{model_id}"

    async def spawn(self, prompt: str, *, name: str, selector: str) -> SpawnHandle:
        """Spawn one child on an explicitly routed selector.

        This is deliberately a concrete method rather than an override point. The
        guard below is the single most valuable one in the package and it must not be
        possible for a subclass — a double, a future transport — to be written without
        it. Subclasses implement :meth:`_spawn`, which is only ever reached once these
        checks have passed.

        A spawn with no model argument does **not** fail: the host resolves it to the
        parent's own model, which is the expensive orchestrator. So a bug that drops
        the selector routes every delegation to the most expensive model in the system
        and passes every gate while doing it.

        Raises:
            ValueError: The prompt, the name, or the selector is missing or unusable.
                Raised before any host request is issued.
        """
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("a spawn needs a non-empty prompt")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("a spawn needs a non-empty child name")
        if len(name) > CHILD_NAME_MAX_LENGTH:
            raise ValueError(
                f"child name must be at most {CHILD_NAME_MAX_LENGTH} characters, got {len(name)}"
            )
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError(
                "a spawn needs an explicitly routed provider/model selector; without one the host "
                "resolves the child to the parent's own model, silently routing this delegation "
                "to the most expensive model in the system"
            )
        return await self._spawn(prompt, name=name, selector=selector)

    async def _spawn(self, prompt: str, *, name: str, selector: str) -> SpawnHandle:
        """Issue the validated spawn. Implemented per transport."""
        raise NotImplementedError

    async def send_message(self, message: str, *, receiver_role: str, receiver_name: str) -> dict[str, Any]:
        """Deliver one direct message to a named child."""
        raise NotImplementedError

    async def delete_subagent(self, target: str) -> dict[str, Any]:
        """Tear down one child by id or session name."""
        raise NotImplementedError


class RuntimeHost(Host):
    """Answers from the bundled runtime, imported lazily on every call."""

    def _runtime(self) -> Any:
        try:
            return importlib.import_module(RUNTIME_MODULE)
        except Exception as error:  # ImportError in a kernel-less process, anything else in a broken one
            raise HostUnavailable(
                f"the Prime Agent runtime ({RUNTIME_MODULE}) is unavailable: {error}"
            ) from error

    async def request(self, request_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._runtime().host_request(request_type, payload)

    async def find_models(self, query: str = "", limit: int = MODEL_SEARCH_LIMIT) -> tuple[ModelMatch, ...]:
        models = await self._runtime().find_models(query, checked_limit(limit))
        return tuple(
            ModelMatch(provider=model.provider, id=model.id, name=model.name, selector=model.selector)
            for model in models
        )

    async def list_subagents(self) -> tuple[Subagent, ...]:
        entries = await self._runtime().list_subagents()
        return tuple(
            Subagent(
                child_id=entry.rlm_child_id,
                active_session_id=entry.active_session_id,
                session_id=entry.session_id,
                session_name=entry.session_name,
                session_dir=Path(entry.session_dir),
                status=entry.status,
            )
            for entry in entries
        )

    async def _spawn(self, prompt: str, *, name: str, selector: str) -> SpawnHandle:
        # Exactly a name and a model. The runtime rejects any other option with an
        # explicit unsupported-kwargs error rather than ignoring it, and there is no
        # thinking option here at all — a child inherits the parent's level, clamped
        # to what its own model supports.
        handle = await self._runtime().run(prompt, name=name, model=selector)
        return SpawnHandle(
            child_id=handle.rlm_child_id,
            name=handle.name,
            session_dir=Path(handle.session_dir),
            model=handle.model,
        )

    async def send_message(self, message: str, *, receiver_role: str, receiver_name: str) -> dict[str, Any]:
        return await self.request(
            "agent_message.send",
            {"message": message, "receiver_role": receiver_role, "receiver_name": receiver_name},
        )

    async def delete_subagent(self, target: str) -> dict[str, Any]:
        return await self.request("rlm.delete_subagent", {"target": target})


class UnavailableHost(Host):
    """Reports the bridge as unreachable, carrying the reason it was not reachable."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def _fail(self) -> HostUnavailable:
        return HostUnavailable(f"no Prime Agent host bridge in this process: {self.reason}")

    async def request(self, request_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        raise self._fail()

    async def find_models(self, query: str = "", limit: int = MODEL_SEARCH_LIMIT) -> tuple[ModelMatch, ...]:
        raise self._fail()

    async def list_subagents(self) -> tuple[Subagent, ...]:
        raise self._fail()

    async def _spawn(self, prompt: str, *, name: str, selector: str) -> SpawnHandle:
        raise self._fail()

    async def send_message(self, message: str, *, receiver_role: str, receiver_name: str) -> dict[str, Any]:
        raise self._fail()

    async def delete_subagent(self, target: str) -> dict[str, Any]:
        raise self._fail()


_installed: Host | None = None


def current() -> Host:
    """Return the host in force — the injected one, or the live runtime."""
    if _installed is not None:
        return _installed
    return RuntimeHost()


def install(host: Host) -> None:
    """Replace the host in force. The single injection point in the package."""
    global _installed
    _installed = host


def reset() -> None:
    """Drop any injected host and go back to the live runtime."""
    global _installed
    _installed = None


class using:
    """Install a host for the duration of a block, then restore the previous one."""

    def __init__(self, host: Host) -> None:
        self._host = host
        self._previous: Host | None = None

    def __enter__(self) -> Host:
        global _installed
        self._previous = _installed
        _installed = self._host
        return self._host

    def __exit__(self, *exc_info: object) -> None:
        global _installed
        _installed = self._previous
