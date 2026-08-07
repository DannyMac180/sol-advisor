"""Read and validate the corpus. Ships with the writer, because it has to.

A schema version stamped on every record is worthless if nothing can consume it. The
consumer here is a plan that does not exist yet, and it will run against records
written by code that may no longer exist either — so the reader ships alongside the
writer from the first record, rather than being written when someone finally needs it.

An unknown schema version is **reported, not crashed on**. A future reader meeting a
record from a version it does not know should be able to say so and carry on with the
records it does understand; refusing to load the file would make one new field cost
the whole corpus.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import episodes as episodes_module

#: Every schema version this reader can validate. Grows; never shrinks silently.
SUPPORTED_SCHEMA_VERSIONS = (episodes_module.SCHEMA_VERSION,)

#: Fields every record must carry to be usable as a training example at all.
REQUIRED_FIELDS = (
    "delegation_id",
    "outcome",
    "selector",
    "surviving_allowlist_size",
    "effort_at_spawn",
    "child_effort_clamped",
    "domain",
    "difficulty",
    "rounds",
    "correction_count",
    "degradations",
)


@dataclass(frozen=True)
class ValidationResult:
    """Whether one record is usable, and why not when it is not."""

    valid: bool
    errors: tuple[str, ...]
    unknown_version: bool


def validate(record: Any) -> ValidationResult:
    """Validate one record against the schema version it declares."""
    if not isinstance(record, dict):
        return ValidationResult(
            valid=False,
            errors=(f"a record must be a JSON object, got {type(record).__name__}",),
            unknown_version=True,
        )

    version = record.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        # Reported, not raised. A reader that crashed here would make one unknown
        # version cost every record in the file, including the ones it understands.
        return ValidationResult(
            valid=False,
            errors=(
                f"unknown schema version {version!r}; this reader supports "
                f"{', '.join(str(entry) for entry in SUPPORTED_SCHEMA_VERSIONS)}",
            ),
            unknown_version=True,
        )

    errors = [f"missing required field {field!r}" for field in REQUIRED_FIELDS if field not in record]

    if record.get("outcome") not in episodes_module.TERMINAL_OUTCOMES and "outcome" in record:
        errors.append(
            f"outcome {record.get('outcome')!r} is not one of "
            f"{', '.join(episodes_module.TERMINAL_OUTCOMES)}"
        )
    if "rounds" in record and not isinstance(record["rounds"], list):
        errors.append("rounds must be a list, so per-round outcomes stay recoverable")

    return ValidationResult(valid=not errors, errors=tuple(errors), unknown_version=False)


def read_all(path: Path | None = None) -> list[dict[str, Any]]:
    """Return every parsable record in the store, silently skipping corrupt lines."""
    records, _ = read_all_reporting(path)
    return records


def read_all_reporting(path: Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Return every parsable record, and a description of each line that was not.

    Returns:
        The records, and one problem string per unreadable line naming its line number.
    """
    store = path or episodes_module.store_path()
    if not store.exists():
        return [], []
    try:
        raw = store.read_text(encoding="utf-8")
    except OSError as error:
        return [], [f"the store at {store} could not be read: {error}"]

    records: list[dict[str, Any]] = []
    problems: list[str] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            problems.append(f"line {number} of {store} is not valid JSON: {error.msg}")
            continue
        if isinstance(record, dict):
            records.append(record)
        else:
            problems.append(f"line {number} of {store} is not a JSON object")
    return records, problems


def summarise(path: Path | None = None) -> dict[str, Any]:
    """Describe the corpus: how many records, how many usable, what is unknown.

    The first thing a policy-fitting plan will want, and cheap enough to ship now.
    """
    records, problems = read_all_reporting(path)
    results = [validate(record) for record in records]
    outcomes: dict[str, int] = {}
    for record, result in zip(records, results):
        if result.valid:
            outcomes[record["outcome"]] = outcomes.get(record["outcome"], 0) + 1
    return {
        "records": len(records),
        "valid": sum(1 for result in results if result.valid),
        "unknown_version": sum(1 for result in results if result.unknown_version),
        "unreadable_lines": len(problems),
        "problems": problems,
        "outcomes": outcomes,
        "missing_cost_term": sum(1 for record in records if "cost_total" not in record),
    }
