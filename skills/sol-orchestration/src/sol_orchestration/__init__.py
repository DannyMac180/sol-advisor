"""Sol orchestration — cost-routed delegation for Prime Agent.

The package root carries the environment report and exposes the documented preflight
and routing modules without depending on import order. Its environment callable,
:func:`run`, is
wrapped by Prime Agent so the module itself is awaitable in the kernel::

    await sol_orchestration()
    await sol_orchestration.run(verbose=True)
    help(sol_orchestration)

Nothing here imports the bundled Prime Agent runtime at module level. The runtime
ships with Prime Agent and is not on PyPI, so a module-level import would make this
package unimportable everywhere except a kernel — including the standalone test run
that proves it works. :func:`run` probes for it lazily and reports its absence as a
stated degradation instead of raising.
"""

from __future__ import annotations

from . import home, preflight, routing

__all__ = [
    "run",
    "home",
    "preflight",
    "routing",
    "BOUNDARY_OUTCOMES",
    "RUNTIME_MODULE",
    "__version__",
]

__version__ = "0.1.0"

#: The bundled Prime Agent runtime. Imported lazily, never declared as a dependency.
RUNTIME_MODULE = "rlm"

#: The only verdicts a delegation boundary may return. See SKILL.md for each one.
BOUNDARY_OUTCOMES = ("ship", "fix-first", "rethink", "abandon")


def _runtime_status() -> str:
    """Report importability without mistaking it for a verified host capability.

    Importing ``rlm`` proves only that the kernel bootstrap installed the module. The
    trace that prompted this distinction imported it successfully while a host request
    required by preflight was unavailable. Capability is verified only by preflight.
    """
    try:
        __import__(RUNTIME_MODULE)
    except ImportError as error:
        return (
            f"runtime module: degraded — {RUNTIME_MODULE} is unavailable ({error}); "
            "delegation capability: unavailable — follow the recovery procedure in SKILL.md"
        )
    return (
        f"runtime module: importable — {RUNTIME_MODULE} imported; "
        "delegation capability: unverified — run "
        "await sol_orchestration.preflight.run() before delegating"
    )


async def run(verbose: bool = False) -> str:
    """Report the orchestration environment and the delegation contract in force.

    Args:
        verbose: Also report the interpreter and the module path backing this skill.

    Returns:
        A short plain-text report: package version, the resolved Prime Agent home and
        kernel venv with the variable that decided each, whether the environment is
        isolated from the operator's real installation, whether the kernel runtime
        imports (without claiming capability before preflight), and the boundary
        outcomes a delegation may return.
    """
    lines = [
        f"sol-orchestration {__version__}",
        f"agent home: {home.agent_home()} (source: {home.home_source()})",
        f"kernel venv: {home.kernel_venv()} (source: {home.kernel_venv_source()})",
        f"isolated from the real installation: {'yes — isolated' if home.is_isolated() else 'no'}",
        _runtime_status(),
        f"boundary outcomes: {' | '.join(BOUNDARY_OUTCOMES)}",
    ]

    kernel_python = home.kernel_python()
    if kernel_python is not None:
        lines.append(
            f"{home.KERNEL_PYTHON_ENV_VAR} is set ({kernel_python}): Prime Agent installs "
            "nothing into that interpreter, so treat any missing import as degraded and "
            "follow the unrecorded recovery discipline in SKILL.md"
        )

    if verbose:
        import sys

        lines.append(f"interpreter: {sys.executable}")
        lines.append(f"module: {__file__}")

    return "\n".join(lines)
