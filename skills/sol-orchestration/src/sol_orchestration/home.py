"""Resolve the Prime Agent directories this package reads, writes, and is judged against.

Two variables matter and they are not interchangeable. Prime Agent resolves its home
from ``PRIME_AGENT_CODING_AGENT_DIR`` and its kernel venv from
``PRIME_AGENT_KERNEL_VENV``, falling back to a path hardcoded off the real user home.
The venv resolution never consults the home variable, so redirecting only the home
leaves an editable install landing in — and rebuilding — the operator's real kernel
venv. Every disposable-home gate in this epic depends on that distinction, which is
why :func:`is_isolated` requires both.
"""

from __future__ import annotations

import os
from pathlib import Path

HOME_ENV_VAR = "PRIME_AGENT_CODING_AGENT_DIR"
KERNEL_VENV_ENV_VAR = "PRIME_AGENT_KERNEL_VENV"
KERNEL_PYTHON_ENV_VAR = "PRIME_AGENT_KERNEL_PYTHON"

DEFAULT_HOME = Path("~/.prime/agent")
DEFAULT_KERNEL_VENV = Path("~/.prime/agent/kernel-venv")


def _override(variable: str) -> str | None:
    """Return a usable override, treating blank and whitespace-only values as unset.

    Prime Agent itself would accept a whitespace-only value as a literal path. This
    resolver deliberately does not: a path of spaces is always a shell accident, and
    silently pointing the package at it is worse than falling back to the default.
    """
    value = os.environ.get(variable)
    if value is None or not value.strip():
        return None
    return value


def _as_path(value: str) -> Path:
    """Expand ``~`` and make the result absolute against the current directory.

    Absolutising eagerly is a stated divergence from Prime Agent, which leaves a
    relative override relative. Callers here hold the result across directory
    changes inside a long-lived kernel, where a relative path silently retargets.
    """
    return Path(os.path.abspath(os.path.expanduser(value)))


def agent_home() -> Path:
    """Return the Prime Agent home directory in force for this process."""
    override = _override(HOME_ENV_VAR)
    if override is not None:
        return _as_path(override)
    return DEFAULT_HOME.expanduser()


def home_source() -> str:
    """Return the variable that decided the home, or ``"default"`` when none did."""
    return HOME_ENV_VAR if _override(HOME_ENV_VAR) is not None else "default"


def kernel_venv() -> Path:
    """Return the kernel venv directory in force for this process.

    The fallback is hardcoded off the real user home, exactly as Prime Agent does it.
    It is *not* derived from :func:`agent_home`, and must never be.
    """
    override = _override(KERNEL_VENV_ENV_VAR)
    if override is not None:
        return _as_path(override)
    return DEFAULT_KERNEL_VENV.expanduser()


def kernel_venv_source() -> str:
    """Return the variable that decided the kernel venv, or ``"default"``."""
    return KERNEL_VENV_ENV_VAR if _override(KERNEL_VENV_ENV_VAR) is not None else "default"


def is_isolated() -> bool:
    """Report whether both the home and the kernel venv are redirected.

    One without the other is not isolation, and an install cycle run under a
    half-redirected environment will mutate the operator's real venv.
    """
    return _override(HOME_ENV_VAR) is not None and _override(KERNEL_VENV_ENV_VAR) is not None


def kernel_python() -> str | None:
    """Return ``PRIME_AGENT_KERNEL_PYTHON`` when set.

    When it is set, Prime Agent installs nothing into that interpreter: a Python
    skill whose package is missing there is disabled with a warning. That is the
    degraded mode this skill has to state out loud rather than fail quietly in.
    """
    return _override(KERNEL_PYTHON_ENV_VAR)
