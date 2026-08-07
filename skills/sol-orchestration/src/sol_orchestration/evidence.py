"""Everything the orchestrator judges against, computed in the kernel for nothing.

This module is why the economics work. The orchestrator never reads a project file, so
if these signals cost a model call the learning substrate would cost more than the
routing saves. **Nothing here may become a host request under any condition** — a test
asserts it by reading this file's own source.

It is also where the design's biggest hole is closed. Without adversarial signals,
`ship` rests on an exit status and path membership, and a cheap model that weakens an
assertion, skips a test, stubs a function, or edits the file its own verification
command runs produces a packet indistinguishable from success.

Two orderings are correctness requirements rather than preferences:

**The tamper gate runs before the verification command executes.** The kernel runs
commands with the operator's full permissions. A child that edits ``conftest.py`` —
even one legitimately inside its ownership set — and then has the kernel run the tests
has arranged for its own code to run next to the operator's credentials. Classifying
that afterwards is too late, so the gate short-circuits and the command never launches.

**Detection is wider than git.** Every git-derived signal is blind to a write under
the Prime Agent home, to ``.git/hooks/``, or to a credential file. A hook written to
``.git/hooks/pre-commit`` fires later under the operator's own hands, outside any
delegation at all. So the package config, the episode store and the hooks directory
are hashed across every delegation and any mismatch is an **evidence-integrity
failure**, which is a different finding from an ownership violation and is labelled
as one.

One thing this module deliberately does not do: revert. A detected ownership violation
is reported and left in place. The next delegation snapshots the tree as it finds it,
so an unreverted foreign change is absorbed into the following baseline and stops
being visible after one delegation. That is a real limit of the design, named here
rather than papered over — automatically reverting a child's writes would be a worse
failure than reporting them.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import config as config_module
from . import home
from .contract import REDACTION_OCCURRED, Degradation

#: Files a test runner or build tool loads and **executes** before or around the work
#: under test. A delta touching any of them is ``fix-first`` by construction and its
#: command is never run, whether or not the path is inside the ownership set: the gate
#: is about execution safety, not ownership. Exactly which files a command loads is
#: undecidable in general, so this is a deliberately conservative declared set.
VERIFICATION_BOOTSTRAP_FILES = (
    "conftest.py",
    "pytest.ini",
    "tox.ini",
    "setup.cfg",
    "pyproject.toml",
    "setup.py",
    "Makefile",
    "makefile",
    "package.json",
    "noxfile.py",
    ".pre-commit-config.yaml",
    "sitecustomize.py",
    "usercustomize.py",
)

#: Machine-generated paths that appear whenever a verification command runs. They are
#: reported separately rather than counted as ownership violations: a child that runs
#: its own tests creates them, so counting them would make every Python delegation an
#: ownership violation and train the operator to ignore the signal that matters.
#:
#: They are **reported, never hidden**. A child could still drop something under one of
#: these paths — a poisoned .pyc is importable — so the packet carries them as their own
#: field rather than dropping them from the delta.
BUILD_ARTIFACT_PATTERNS = (
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    ".tox/",
    ".coverage",
    "node_modules/",
    ".gradle/",
    "target/debug/",
)

#: What a masked value is replaced with.
REDACTION_MASK = "[redacted]"

#: Environment values shorter than this are locales and terminal names, not secrets.
MIN_SECRET_LENGTH = 12

#: Verification output is bounded here so a runaway log cannot exhaust memory. The
#: failure-aware truncation that decides what survives belongs to packet assembly.
MAX_CAPTURED_OUTPUT_BYTES = 512_000

DEFAULT_VERIFICATION_TIMEOUT_SECONDS = 900

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)

_TEST_PATH = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|\.test\.[jt]sx?$")
_ASSERTION = re.compile(r"^\s*(assert\b|expect\(|self\.assert)")
_SKIP_MARK = re.compile(r"@(pytest\.mark\.)?(skip|skipif|xfail)\b|\.skip\(|\.only\(|it\.skip\b")


def _git(repo: Path, *args: str) -> str:
    """Run one git command and return its stdout, or an empty string on failure."""
    try:
        completed = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=False
        )
    except OSError:
        return ""
    return completed.stdout if completed.returncode == 0 else ""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_digest(path: Path) -> str | None:
    try:
        return _digest(path.read_bytes())
    except OSError:
        return None


def _tree_digest(root: Path) -> str:
    """Hash a directory's contents by path and bytes, ignoring mtimes.

    An mtime-inclusive hash is too tight a tripwire: unrelated activity moves it with
    no content change, and a tripwire that cries wolf gets ignored.
    """
    if not root.is_dir():
        return "absent"
    parts: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            parts.append(f"{path.relative_to(root)}:{_file_digest(path)}")
    return _digest("\n".join(parts).encode("utf-8"))


def episode_store_path() -> Path:
    """Where episodes are appended. Owned by the episode workstream, hashed here."""
    return home.agent_home() / config_module.CONFIG_DIR_NAME / "episodes.jsonl"


def _dirty_entries(repo: Path) -> dict[str, str]:
    """Return every path git reports as changed or untracked, with a content digest."""
    raw = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries: dict[str, str] = {}
    fields = [field for field in raw.split("\0") if field]
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if len(record) < 4:
            continue
        status, path = record[:2], record[3:]
        if "R" in status or "C" in status:
            index += 1  # a rename carries its source path in the next field
        entries[path] = _file_digest(repo / path) or "absent"
    return entries


@dataclass(frozen=True)
class Snapshot:
    """The repository and its environment as they were immediately before a spawn.

    Every delta is computed against this rather than against HEAD. A shared working
    tree carries operator edits and the previous delegation's accepted work, so a
    HEAD-relative diff would attribute both to this delegation — and a child that
    commits would make a HEAD-relative diff show nothing at all.
    """

    repo: Path
    head: str
    refs: str
    stash: str
    dirty: dict[str, str]
    config_digest: str | None
    episode_store_size: int
    hooks_digest: str


def snapshot(repo: Path, declared: config_module.Config | None = None) -> Snapshot:
    """Capture the pre-spawn state. Invoked by dispatch, owned here."""
    repo = Path(repo)
    config_path = declared.path if declared is not None else config_module.config_path()
    store = episode_store_path()
    return Snapshot(
        repo=repo,
        head=_git(repo, "rev-parse", "HEAD").strip(),
        refs=_git(repo, "show-ref").strip(),
        stash=_git(repo, "stash", "list").strip(),
        dirty=_dirty_entries(repo),
        config_digest=_file_digest(config_path),
        episode_store_size=store.stat().st_size if store.exists() else 0,
        hooks_digest=_tree_digest(repo / ".git" / "hooks"),
    )


@dataclass(frozen=True)
class Verification:
    """One verification run, captured after the tamper gate allowed it."""

    argv: tuple[str, ...]
    exit_status: int
    output: str
    timed_out: bool
    truncated: bool


@dataclass(frozen=True)
class Signals:
    """Adversarial signals over the delta, all computed without a model call."""

    test_files_changed: int = 0
    non_test_files_changed: int = 0
    test_lines_added: int = 0
    test_lines_removed: int = 0
    non_test_lines_added: int = 0
    non_test_lines_removed: int = 0
    net_lines_removed: int = 0
    removed_assertions: int = 0
    newly_skipped_tests: int = 0
    deleted_test_files: int = 0


def is_build_artifact(path: str) -> bool:
    """Report whether a path is machine-generated by running the verification command."""
    normalised = path.replace("\\", "/")
    for pattern in BUILD_ARTIFACT_PATTERNS:
        if pattern.endswith("/"):
            if normalised.startswith(pattern) or f"/{pattern}" in normalised:
                return True
        elif normalised == pattern or normalised.endswith(f"/{pattern}"):
            return True
    return False


@dataclass(frozen=True)
class Evidence:
    """Everything the packet's authoritative fields are built from."""

    changed_paths: tuple[str, ...]
    build_artifacts: tuple[str, ...]
    pre_existing_changes: tuple[str, ...]
    ownership_violations: tuple[str, ...]
    integrity_failures: tuple[str, ...]
    tamper_paths: tuple[str, ...]
    head_moved: bool
    refs_changed: bool
    stash_changed: bool
    empty_diff: bool
    verification: Verification | None
    signals: Signals
    diff: str
    verdict: str | None
    degradations: tuple[Degradation, ...] = field(default_factory=tuple)


def redact(text: str, environ: dict[str, str] | None = None) -> tuple[str, bool]:
    """Mask secrets in text, and report whether anything was masked.

    Two classes are masked: any environment value long enough to be a secret rather
    than a locale or a terminal name, and values matching a known secret shape even
    when they are nowhere in the environment.
    """
    environ = os.environ if environ is None else environ
    masked = text
    for value in sorted(environ.values(), key=len, reverse=True):
        if value and len(value) >= MIN_SECRET_LENGTH and value in masked:
            masked = masked.replace(value, REDACTION_MASK)
    for pattern in _SECRET_PATTERNS:
        masked = pattern.sub(REDACTION_MASK, masked)
    return masked, masked != text


def _is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(path))


def verification_targets(argv: tuple[str, ...], repo: Path) -> tuple[str, ...]:
    """Return the paths this command would load and execute.

    Conservative by design. An exact answer is undecidable, and the cost of being
    wrong in the permissive direction is the child's code running with the operator's
    credentials.
    """
    targets: set[str] = set()

    for argument in argv:
        for token in re.split(r"[\s=,:]+", argument):
            token = token.strip("'\"")
            if not token or token.startswith("-"):
                continue
            candidate = (repo / token).resolve()
            try:
                candidate.relative_to(repo.resolve())
            except ValueError:
                continue
            if candidate.exists() or "/" in token or token.endswith((".py", ".sh", ".js", ".ts")):
                targets.add(token.lstrip("./"))

    return tuple(sorted(targets))


def _touches_bootstrap(path: str) -> bool:
    name = Path(path).name
    if name in VERIFICATION_BOOTSTRAP_FILES:
        return True
    return path.startswith(".git/hooks/") or "/.git/hooks/" in path


def tamper_paths(changed: tuple[str, ...], argv: tuple[str, ...], repo: Path) -> tuple[str, ...]:
    """Return changed paths whose code the verification command would execute."""
    targets = set(verification_targets(argv, repo))
    hit = {path for path in changed if _touches_bootstrap(path) or path in targets}
    return tuple(sorted(hit))


def _diff_signals(diff: str, changed: tuple[str, ...]) -> Signals:
    """Compute the adversarial signals from a unified diff."""
    test_added = test_removed = non_test_added = non_test_removed = 0
    removed_assertions = newly_skipped = 0
    current_is_test = False

    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current_is_test = _is_test_path(path[2:] if path.startswith("b/") else path)
            continue
        if line.startswith(("--- ", "diff ", "index ", "@@", "new file", "deleted file")):
            continue
        if line.startswith("+") :
            body = line[1:]
            if current_is_test:
                test_added += 1
            else:
                non_test_added += 1
            if _SKIP_MARK.search(body):
                newly_skipped += 1
        elif line.startswith("-"):
            body = line[1:]
            if current_is_test:
                test_removed += 1
            else:
                non_test_removed += 1
            if _ASSERTION.match(body):
                removed_assertions += 1

    test_files = sum(1 for path in changed if _is_test_path(path))
    added = test_added + non_test_added
    removed = test_removed + non_test_removed

    return Signals(
        test_files_changed=test_files,
        non_test_files_changed=len(changed) - test_files,
        test_lines_added=test_added,
        test_lines_removed=test_removed,
        non_test_lines_added=non_test_added,
        non_test_lines_removed=non_test_removed,
        net_lines_removed=max(0, removed - added),
        removed_assertions=removed_assertions,
        newly_skipped_tests=newly_skipped,
        deleted_test_files=0,
    )


def _run(argv: tuple[str, ...], repo: Path, timeout_seconds: int) -> tuple[Verification, bool]:
    """Execute the verification command. Only ever reached past the tamper gate."""
    timed_out = False
    try:
        completed = subprocess.run(
            list(argv),
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        raw = (completed.stdout or "") + (completed.stderr or "")
        status = completed.returncode
    except subprocess.TimeoutExpired as expired:
        timed_out = True
        status = 124
        raw = ((expired.stdout or b"").decode("utf-8", "replace") if isinstance(expired.stdout, bytes) else (expired.stdout or "")) + (
            (expired.stderr or b"").decode("utf-8", "replace") if isinstance(expired.stderr, bytes) else (expired.stderr or "")
        )
    except OSError as error:
        return Verification(argv=argv, exit_status=127, output=str(error), timed_out=False, truncated=False), False

    truncated = len(raw.encode("utf-8")) > MAX_CAPTURED_OUTPUT_BYTES
    if truncated:
        raw = raw.encode("utf-8")[-MAX_CAPTURED_OUTPUT_BYTES:].decode("utf-8", "replace")

    # Redact before the output reaches anything that keeps it.
    clean, redacted = redact(raw)
    return (
        Verification(
            argv=argv, exit_status=status, output=clean, timed_out=timed_out, truncated=truncated
        ),
        redacted,
    )


def collect(
    *,
    repo: Path,
    snapshot: Snapshot,
    ownership: tuple[str, ...],
    verification_argv: tuple[str, ...],
    declared: config_module.Config | None = None,
    timeout_seconds: int = DEFAULT_VERIFICATION_TIMEOUT_SECONDS,
) -> Evidence:
    """Compute every deterministic signal for one completed delegation.

    Returns:
        The evidence, with ``verdict`` set to ``"fix-first"`` when the tamper gate or
        an integrity failure fired — in which case ``verification`` is ``None``
        because the command was never executed.
    """
    repo = Path(repo)
    degradations: list[Degradation] = []

    head_now = _git(repo, "rev-parse", "HEAD").strip()
    head_moved = bool(snapshot.head) and head_now != snapshot.head
    refs_changed = _git(repo, "show-ref").strip() != snapshot.refs
    stash_changed = _git(repo, "stash", "list").strip() != snapshot.stash

    dirty_now = _dirty_entries(repo)
    changed: set[str] = set()
    pre_existing: set[str] = set()
    for path, digest in dirty_now.items():
        if path in snapshot.dirty and snapshot.dirty[path] == digest:
            pre_existing.add(path)  # the operator's own work-in-progress, untouched
        else:
            changed.add(path)
    # A file the operator had dirty and the child reverted to HEAD leaves the dirty set.
    for path in snapshot.dirty:
        if path not in dirty_now:
            changed.add(path)

    # A child that commits empties the working tree, so the committed range is part of
    # the delta or the whole change would be invisible.
    if head_moved:
        committed = _git(repo, "diff", "--name-only", f"{snapshot.head}..{head_now}")
        changed.update(line.strip() for line in committed.splitlines() if line.strip())

    changed_paths = tuple(sorted(changed))

    diff = _git(repo, "diff", "--unified=0", snapshot.head) if snapshot.head else ""
    if not diff:
        diff = _git(repo, "diff", "--unified=0")
    signals = _diff_signals(diff, changed_paths)
    deleted_tests = sum(
        1 for path in changed_paths if _is_test_path(path) and not (repo / path).exists()
    )
    signals = Signals(
        test_files_changed=signals.test_files_changed,
        non_test_files_changed=signals.non_test_files_changed,
        test_lines_added=signals.test_lines_added,
        test_lines_removed=signals.test_lines_removed,
        non_test_lines_added=signals.non_test_lines_added,
        non_test_lines_removed=signals.non_test_lines_removed,
        net_lines_removed=signals.net_lines_removed,
        removed_assertions=signals.removed_assertions,
        newly_skipped_tests=signals.newly_skipped_tests,
        deleted_test_files=deleted_tests,
    )

    owned = set(ownership)
    build_artifacts = tuple(path for path in changed_paths if is_build_artifact(path))
    violations = tuple(
        path
        for path in changed_paths
        if path not in owned
        and not _inside_owned_dir(path, owned)
        and not is_build_artifact(path)
    )

    integrity = _integrity_failures(repo, snapshot, head_moved, head_now, declared)
    tampered = tamper_paths(changed_paths, verification_argv, repo)

    verdict: str | None = None
    verification: Verification | None = None

    if tampered or integrity:
        # Short-circuit. Executing first and classifying afterwards would already have
        # run the child's code with the operator's full permissions.
        verdict = "fix-first"
    else:
        verification, redacted = _run(verification_argv, repo, timeout_seconds)
        if redacted:
            degradations.append(
                Degradation(
                    kind=REDACTION_OCCURRED,
                    detail="verification output contained secret-shaped or environment values",
                )
            )

    return Evidence(
        changed_paths=changed_paths,
        build_artifacts=build_artifacts,
        pre_existing_changes=tuple(sorted(pre_existing)),
        ownership_violations=violations,
        integrity_failures=integrity,
        tamper_paths=tampered,
        head_moved=head_moved,
        refs_changed=refs_changed,
        stash_changed=stash_changed,
        empty_diff=not changed_paths,
        verification=verification,
        signals=signals,
        diff=diff,
        verdict=verdict,
        degradations=tuple(degradations),
    )


def _inside_owned_dir(path: str, owned: set[str]) -> bool:
    """Allow a declared directory to own the files beneath it."""
    for entry in owned:
        if entry.endswith("/") and path.startswith(entry):
            return True
        if path.startswith(entry.rstrip("/") + "/"):
            return True
    return False


def _integrity_failures(
    repo: Path,
    snapshot: Snapshot,
    head_moved: bool,
    head_now: str,
    declared: config_module.Config | None,
) -> tuple[str, ...]:
    """Report every mismatch a git-derived signal could not have seen."""
    failures: list[str] = []

    config_path = declared.path if declared is not None else config_module.config_path()
    if _file_digest(config_path) != snapshot.config_digest:
        failures.append(
            f"the package config at {config_path} changed during this delegation — the measured "
            "system wrote to the measurement"
        )

    store = episode_store_path()
    size_now = store.stat().st_size if store.exists() else 0
    if size_now != snapshot.episode_store_size:
        # Any change at all is wrong here. This package appends its own record when the
        # delegation closes, which is after evidence collection — so at this moment the
        # store should be byte-identical to what it was before the spawn. A child that
        # appends plausible records rather than editing existing ones would poison a
        # future policy fit without ever tripping the append-only convention.
        failures.append(
            f"the episode store at {store} changed size during this delegation "
            f"({snapshot.episode_store_size} to {size_now} bytes); nothing should write it "
            "between the spawn and the verdict"
        )

    if _tree_digest(repo / ".git" / "hooks") != snapshot.hooks_digest:
        failures.append(
            f"the repository hooks directory at {repo / '.git' / 'hooks'} changed during this "
            "delegation — a hook runs later under the operator's own hands, outside any delegation"
        )

    if head_moved:
        failures.append(
            f"HEAD moved from {snapshot.head[:12]} to {head_now[:12]} during this delegation; "
            "the child committed, which a HEAD-relative diff would have shown as no change at all"
        )

    return tuple(failures)


def episode_store_growth(snapshot: Snapshot, expected_records: int = 1) -> int | None:
    """Report how many records the store grew by, for the caller to compare.

    Kept separate from :func:`collect` because only the episode workstream knows how
    many records this delegation was entitled to append.
    """
    store = episode_store_path()
    if not store.exists():
        return None
    try:
        return sum(1 for line in store.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return None
