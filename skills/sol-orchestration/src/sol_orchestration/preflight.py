"""Decide whether a delegation can proceed, before it costs anything.

Everything here is free. Model search resolves against authenticated credentials
before any inference runs; reading the effort level is a file read; the retention and
reachability probes are read-only host requests. That is the point of doing all of it
first: this is the last moment the package can say no without having spent money.

Four checks, and the refuse/degrade split is deliberate in each:

* **Availability** — one query per declared entry, never one catalog enumeration. The
  host caps a search at twenty results, so a single enumeration would silently report
  authenticated entries as unavailable and corrupt both the recorded drop reason and
  the surviving-set size on every episode that followed.
* **Effort** — no host request returns the thinking level, so the only kernel-side
  read is the session transcript's latest level-change entry. Below the floor is a
  refusal that asks the operator to raise it, because nothing in the kernel can. An
  unreadable transcript is a degradation, not a refusal.
* **Correction mode** — a retained child with agent messaging can be corrected in
  place. When either capability is absent the lifecycle's existing fallback opens a
  new linked delegation on the same model. Preflight records that costlier restart-only
  mode as a degradation; it does not force callers into raw spawning that would bypass
  the episode ledger. ``agent_observe`` is not probed because collection uses the RLM
  registry and the file signal, never that host request.
* **Runtime version** — every contract this package depends on was read from one
  version's source, so a change is a re-verification trigger. It is a degradation
  rather than a refusal: the deliverable is the corpus, and freezing it on a routine
  patch bump costs more than running one version past verification.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import config as config_module
from . import home
from .contract import (
    ALLOWLIST_ENTRIES_DROPPED,
    RESTART_ONLY_CORRECTIONS,
    UNREADABLE_EFFORT,
    UNRECOGNIZED_RUNTIME_VERSION,
    Degradation,
    Refusal,
)
from .host import Host, Subagent, current

#: The kernel is pointed at its own session's artifact directory through this.
SESSION_DIR_ENV_VAR = "RLM_SESSION_DIR"

#: Written by Prime Agent into the kernel venv when it provisions Python skills.
BOOTSTRAP_VERSION_FILE = ".bootstrap-version"

#: Reasoning levels in ascending order, as Prime Agent's settings document them.
EFFORT_LEVELS = ("off", "low", "medium", "high", "xhigh")

#: Cheapness is pursued by moving work to the kernel and to cheaper models, never by
#: thinking less. The floor is a package constant rather than an operator setting so
#: it cannot be quietly lowered to make a run cheaper.
EFFORT_FLOOR = "high"

#: The optional direct-correction channel. Collection itself does not depend on it.
AGENT_MESSAGE_ROSTER_REQUEST = "agent_message.list_agents"


@dataclass(frozen=True)
class RuntimeFingerprint:
    """What the kernel can actually observe about the runtime it is running under.

    Neither field is the Prime Agent release number, which nothing exposes to the
    kernel. They are the two versioned contracts this package reads directly: the
    session transcript's record version, and the kernel venv's bootstrap schema.
    """

    session_record_version: int | None
    kernel_bootstrap_schema: int | None


#: The fingerprint every contract in this package was verified against, on the
#: homelab, against Prime Agent 0.7.0.
VERIFIED_RUNTIME = RuntimeFingerprint(session_record_version=3, kernel_bootstrap_schema=8)


@dataclass(frozen=True)
class DroppedEntry:
    """One declared allowlist entry that did not survive, and why."""

    selector: str
    reason: str


@dataclass(frozen=True)
class RetentionEvidence:
    """What was actually observed about child retention, rather than what was hoped.

    ``roster_reachable`` records the optional agent-message channel; it is not proof
    that a future child will be retained. The child counts are observation only, so a
    preflight with no live children makes no retention claim it did not measure.
    """

    roster_reachable: bool
    observed_children: int
    retained_children: int

    @property
    def proven_by_observation(self) -> bool:
        """Report whether a real child was seen carrying an active session id."""
        return self.retained_children > 0


@dataclass(frozen=True)
class PreflightReport:
    """The result of a passing preflight — never of a failing one, which raises."""

    config: config_module.Config
    surviving: tuple[str, ...]
    dropped: tuple[DroppedEntry, ...]
    effort: str | None
    retention: RetentionEvidence
    runtime: RuntimeFingerprint
    degradations: tuple[Degradation, ...]


def clears_floor(level: str | None) -> bool:
    """Report whether an observed effort level is at or above the floor."""
    if level is None or level not in EFFORT_LEVELS:
        return False
    return EFFORT_LEVELS.index(level) >= EFFORT_LEVELS.index(EFFORT_FLOOR)


async def resolve_availability(
    allowlist: tuple[str, ...],
    host: Host | None = None,
    parent_selector: str | None = None,
) -> tuple[tuple[str, ...], tuple[DroppedEntry, ...]]:
    """Reduce the declared allowlist to entries reachable under active credentials.

    One query per entry, using that entry's exact selector. Never one enumeration:
    the host caps a search at twenty results, so enumerating would drop authenticated
    entries whenever the operator's catalog is larger than the cap — and would record
    a drop reason that was never true.

    Args:
    The parent session's own model is a deliberate exception. The host resolves a
    spawn against the authenticated-model list **except** when the requested selector
    equals the parent's, which it returns directly — so that model is always spawnable
    even when the search omits it. A search-only check would drop the one entry
    guaranteed to work, which on a subscription-only credential can be the only entry
    the operator has.

    Args:
        allowlist: The operator's declared entries, in declared order.
        host: The host to query; the injected or live one when omitted.
        parent_selector: The session's own ``provider/id``; read from the host when
            omitted. Pass ``""`` to disable the exception entirely.

    Returns:
        The surviving entries in declared order, and the dropped ones with reasons.
    """
    host = host or current()
    if parent_selector is None:
        parent_selector = await host.parent_selector()
    parent = (parent_selector or "").lower()
    surviving: list[str] = []
    dropped: list[DroppedEntry] = []

    for selector in allowlist:
        try:
            matches = await host.find_models(selector)
        except Exception as error:  # an unreachable or unauthenticated entry is a drop, not a crash
            dropped.append(DroppedEntry(selector=selector, reason=f"model search failed: {error}"))
            continue
        # The spawn resolves by exact lowercased provider/id, so availability means an
        # exact match and never a near one: a preview or dated sibling is a different model.
        if any(match.selector.lower() == selector.lower() for match in matches):
            surviving.append(selector)
        elif parent and selector.lower() == parent:
            # Spawnable through the host's parent-model path even though the search
            # does not list it. Surviving, and not silently: the caller can see that
            # this delegation would run on the orchestrator's own model.
            surviving.append(selector)
        else:
            dropped.append(
                DroppedEntry(
                    selector=selector,
                    reason="no authenticated model matches this exact selector",
                )
            )

    return tuple(surviving), tuple(dropped)


def session_transcript_path() -> Path | None:
    """Return this session's transcript, or ``None`` when it cannot be located."""
    session_dir = os.environ.get(SESSION_DIR_ENV_VAR)
    if not session_dir or not session_dir.strip():
        return None
    session_id = Path(session_dir.strip()).name
    if not session_id:
        return None
    return home.agent_home() / "sessions" / f"{session_id}.jsonl"


def _read_transcript_entries(path: Path | None) -> tuple[list[dict], str | None]:
    """Return the transcript's parsable entries, and a reason when it is unusable."""
    if path is None:
        return [], f"{SESSION_DIR_ENV_VAR} is unset, so this session's transcript cannot be located"
    if not path.exists():
        return [], f"no transcript at {path}"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        return [], f"transcript at {path} could not be read: {error}"

    entries: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # one corrupt line must not lose the rest of the transcript
        if isinstance(entry, dict):
            entries.append(entry)

    if not entries:
        return [], f"transcript at {path} carried no readable entries"
    return entries, None


def read_effort(entries: list[dict], unreadable: str | None) -> tuple[str | None, Degradation | None]:
    """Read the effort level in force from the transcript's latest level change.

    No host request returns the thinking level — the model-info handler exposes only
    id, provider and input — so this is the only kernel-side read available.

    Returns:
        The level and ``None``, or ``None`` and the degradation explaining why not.
    """
    if unreadable is not None:
        return None, Degradation(kind=UNREADABLE_EFFORT, detail=unreadable)

    for entry in reversed(entries):
        if entry.get("type") == "thinking_level_change":
            level = entry.get("thinkingLevel")
            if isinstance(level, str) and level in EFFORT_LEVELS:
                return level, None
            return None, Degradation(
                kind=UNREADABLE_EFFORT,
                detail=f"latest thinking_level_change carried an unrecognized level {level!r}",
            )

    return None, Degradation(
        kind=UNREADABLE_EFFORT,
        detail="the transcript carries no thinking_level_change entry",
    )


def current_effort_reporting() -> tuple[str | None, Degradation | None]:
    """Return the effort level in force right now, and why it is absent when it is.

    Read at the moment it is asked for. The operator can move the dial mid-session, so
    a level captured earlier and carried forward would record a condition that was not
    actually in force when the spawn happened — which is exactly the confounder the
    episode's effort field exists to remove.

    The degradation is returned rather than discarded because a ``null`` effort with no
    stated reason is the same defect as a zero cost: it reads, to whoever fits a policy
    against this corpus later, as a fact rather than as an absence.
    """
    entries, unreadable = _read_transcript_entries(session_transcript_path())
    return read_effort(entries, unreadable)


def current_effort() -> str | None:
    """Return the effort level in force right now, or ``None`` when unreadable."""
    level, _ = current_effort_reporting()
    return level


def read_runtime_fingerprint(entries: list[dict]) -> RuntimeFingerprint:
    """Read the two versioned contracts this package depends on directly."""
    session_record_version: int | None = None
    for entry in entries:
        if entry.get("type") == "session" and isinstance(entry.get("version"), int):
            session_record_version = entry["version"]
            break

    kernel_bootstrap_schema: int | None = None
    bootstrap = home.kernel_venv() / BOOTSTRAP_VERSION_FILE
    try:
        document = json.loads(bootstrap.read_text(encoding="utf-8"))
        if isinstance(document, dict) and isinstance(document.get("schema"), int):
            kernel_bootstrap_schema = document["schema"]
    except (OSError, json.JSONDecodeError):
        kernel_bootstrap_schema = None

    return RuntimeFingerprint(
        session_record_version=session_record_version,
        kernel_bootstrap_schema=kernel_bootstrap_schema,
    )


def _runtime_degradation(observed: RuntimeFingerprint) -> Degradation | None:
    """Report an unrecognized runtime as a degradation. Never a refusal."""
    differences: list[str] = []
    if observed.session_record_version != VERIFIED_RUNTIME.session_record_version:
        differences.append(
            f"session record version {observed.session_record_version} "
            f"(verified against {VERIFIED_RUNTIME.session_record_version})"
        )
    if observed.kernel_bootstrap_schema != VERIFIED_RUNTIME.kernel_bootstrap_schema:
        differences.append(
            f"kernel bootstrap schema {observed.kernel_bootstrap_schema} "
            f"(verified against {VERIFIED_RUNTIME.kernel_bootstrap_schema})"
        )
    if not differences:
        return None
    return Degradation(
        kind=UNRECOGNIZED_RUNTIME_VERSION,
        detail="; ".join(differences) + " — re-verify the runtime contracts this package reads",
    )


async def correction_channel_reporting(host: Host) -> tuple[bool, str | None]:
    """Report whether in-place correction is reachable, without making it a gate.

    ``Lifecycle.correct`` already falls back to a new linked delegation on the same
    selector when messaging is absent. Refusing here made that implemented fallback
    unreachable and pushed the failing trace into raw spawns with no episode record.
    """
    try:
        await host.request(AGENT_MESSAGE_ROSTER_REQUEST)
    except Exception as error:
        return False, (
            f"{AGENT_MESSAGE_ROSTER_REQUEST} is unavailable "
            f"({type(error).__name__}); host error text omitted from the persistent corpus"
        )
    return True, None


async def read_retention(host: Host, *, roster_reachable: bool) -> RetentionEvidence:
    """Observe live RLM children and whether direct correction could address them.

    The RLM registry is the lifecycle's actual child-state source. A missing active
    session id no longer refuses the whole run: correction restarts on the same model
    under a new linked delegation id, and preflight records that mode as a degradation.
    """
    try:
        subagents: tuple[Subagent, ...] = await host.list_subagents()
    except Exception as error:
        raise Refusal(
            artifact="the RLM subagent registry (rlm.list_subagents)",
            remedy="run this session where the RLM child registry is reachable; it is the "
            f"state source used by bounded collection and correction. The host reported: {error}",
        ) from error

    live = tuple(entry for entry in subagents if entry.status == "running")
    retained = tuple(entry for entry in live if entry.active_session_id)
    return RetentionEvidence(
        roster_reachable=roster_reachable,
        observed_children=len(live),
        retained_children=len(retained),
    )


async def run(host: Host | None = None, config_path: Path | None = None) -> PreflightReport:
    """Run every gate and return what a delegation may proceed with.

    Args:
        host: The host to probe; the injected or live one when omitted.
        config_path: Read the config from here instead of the Prime Agent home.

    Returns:
        The surviving allowlist, the effort in force, the retention evidence, and
        every degradation recorded along the way.

    Raises:
        Refusal: Something must change before any delegation can run. The refusal
            names the artifact and the remedy.
    """
    host = host or current()
    degradations: list[Degradation] = []

    declared = config_module.load(config_path)

    entries, unreadable = _read_transcript_entries(session_transcript_path())

    observed_runtime = read_runtime_fingerprint(entries)
    runtime_degradation = _runtime_degradation(observed_runtime)
    if runtime_degradation is not None:
        degradations.append(runtime_degradation)

    effort, effort_degradation = read_effort(entries, unreadable)
    if effort_degradation is not None:
        degradations.append(effort_degradation)
    elif not clears_floor(effort):
        # The kernel's host bridge exposes no handler for setting a thinking level, so
        # asking is the only honest move: attempting a change here would be theatre.
        raise Refusal(
            artifact=f"the session's reasoning effort, currently {effort!r}",
            remedy=f"raise it to {EFFORT_FLOOR} or above with /effort {EFFORT_FLOOR}; no in-kernel "
            "code can change the level, so only the operator can clear this",
        )

    roster_reachable, correction_channel_problem = await correction_channel_reporting(host)
    retention = await read_retention(host, roster_reachable=roster_reachable)
    restart_only_reasons: list[str] = []
    if correction_channel_problem is not None:
        restart_only_reasons.append(correction_channel_problem)
    if retention.observed_children > retention.retained_children:
        restart_only_reasons.append(
            f"{retention.observed_children - retention.retained_children} live child(ren) "
            "carry no active session id"
        )
    if restart_only_reasons:
        degradations.append(
            Degradation(
                kind=RESTART_ONLY_CORRECTIONS,
                detail="; ".join(restart_only_reasons)
                + " — corrections will open linked delegations on the same model",
            )
        )

    surviving, dropped = await resolve_availability(declared.allowlist, host)
    if dropped:
        degradations.append(
            Degradation(
                kind=ALLOWLIST_ENTRIES_DROPPED,
                detail="; ".join(f"{entry.selector}: {entry.reason}" for entry in dropped),
            )
        )
    if not surviving:
        raise Refusal(
            artifact=str(declared.path),
            remedy="declare at least one allowlist entry reachable under the active credentials, or "
            "re-authenticate the ones already declared; this package does not route to the "
            "session's own model when nothing survives",
        )

    return PreflightReport(
        config=declared,
        surviving=surviving,
        dropped=dropped,
        effort=effort,
        retention=retention,
        runtime=observed_runtime,
        degradations=tuple(degradations),
    )
