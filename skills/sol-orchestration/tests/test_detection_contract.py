"""The detection contract fails silently in Prime Agent, so assert it mechanically.

A violation does not error at startup: the skill just degrades to markdown with a
load warning nobody reads. These tests, and scripts/verify-prime-agent-package.sh,
are the only things that make a violation loud.
"""

import ast
import re
from pathlib import Path

import sol_orchestration

SKILL_DIR = Path(__file__).resolve().parent.parent
IMPORT_NAME = "sol_orchestration"


def frontmatter() -> dict[str, str]:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must open with a YAML frontmatter block"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def test_skill_name_directory_and_import_name_agree() -> None:
    name = frontmatter()["name"]
    assert name == SKILL_DIR.name
    assert name.replace("-", "_") == IMPORT_NAME
    assert IMPORT_NAME.isidentifier()


def test_description_is_present_and_within_the_specification_limit() -> None:
    description = frontmatter()["description"]
    assert description
    assert len(description) <= 1024


def test_src_layout_matches_the_import_name() -> None:
    assert (SKILL_DIR / "src" / IMPORT_NAME / "__init__.py").is_file()


def test_wheel_packages_match_the_source_directory() -> None:
    pyproject = (SKILL_DIR / "pyproject.toml").read_text(encoding="utf-8")
    assert f'packages = ["src/{IMPORT_NAME}"]' in pyproject


def test_the_bundled_runtime_is_not_declared_as_a_dependency() -> None:
    """prime-agent-runtime is bundled, not on PyPI: declaring it breaks this test run."""
    pyproject = (SKILL_DIR / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r"^dependencies\s*=\s*\[(.*?)\]", pyproject, re.DOTALL | re.MULTILINE)
    assert declared
    assert "prime-agent-runtime" not in declared.group(1)


def test_no_module_level_import_of_the_kernel_runtime() -> None:
    """Every module must import outside a kernel; the runtime is imported inside run()."""
    for module in sorted((SKILL_DIR / "src" / IMPORT_NAME).rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in tree.body:
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            roots = {name.split(".")[0] for name in names}
            assert sol_orchestration.RUNTIME_MODULE not in roots, (
                f"{module} imports the kernel runtime at module level"
            )


def test_manual_recovery_is_honest_about_the_missing_episode_and_host_bridge() -> None:
    """Raw spawning cannot impersonate the package lifecycle that the trace bypassed."""
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "unrecorded-manual-delegation" in skill
    assert "does not produce a valid episode" in skill
    assert "Do not start a nested `prime-agent` process" in skill
    assert "runnable by hand, with no Python module and no runtime" not in skill
