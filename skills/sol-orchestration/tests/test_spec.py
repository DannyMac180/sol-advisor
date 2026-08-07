"""The child prompt is the whole of what the child knows, and the whole of the boundary.

Two properties are doing real work here. The prompt is assembled from the spec's
fields and the ownership set alone, so the orchestrator never reads a file to build it
— that is what keeps its context starved. And the completion instruction names a file,
never a reply: the host delivers a child's last output straight to the parent and the
spawn offers no way to suppress it, so a child that replies has written directly into
the orchestrator's context outside the packet.

Every prohibition is prompt text. The kernel is a durable control environment, not a
sandbox. Nothing here is enforced, and the package must not claim otherwise.
"""

from __future__ import annotations

import pytest

from sol_orchestration import config, contract, spec as spec_module

from test_config import WELL_FORMED, seed


def a_spec(**overrides: object) -> spec_module.Spec:
    fields: dict[str, object] = {
        "objective": "Add a retry to the fetch helper",
        "domain": "python",
        "difficulty": "hard",
        "ownership": ("src/fetch.py", "tests/test_fetch.py"),
        "verification_command": "pytest",
        "interfaces": "fetch(url, *, retries=3) keeps its current signature",
        "constraints": "no new dependencies",
    }
    fields.update(overrides)
    return spec_module.Spec(**fields)  # type: ignore[arg-type]


@pytest.fixture
def declared(agent_home) -> config.Config:
    seed(agent_home, WELL_FORMED)
    return config.load()


def test_the_prompt_carries_the_ownership_set_and_every_spec_field(declared: config.Config) -> None:
    prompt = spec_module.assemble(a_spec(), delegation_id="d-0001", declared=declared)
    for owned in ("src/fetch.py", "tests/test_fetch.py"):
        assert owned in prompt
    assert "Add a retry to the fetch helper" in prompt
    assert "fetch(url, *, retries=3) keeps its current signature" in prompt
    assert "no new dependencies" in prompt


def test_the_prompt_carries_the_resolved_verification_command_not_a_free_text_one(
    declared: config.Config,
) -> None:
    """Accepting spec free text would let a spec name a command the operator never declared."""
    prompt = spec_module.assemble(a_spec(), delegation_id="d-0001", declared=declared)
    assert "python -m pytest -q" in prompt


def test_a_verification_command_outside_the_declared_set_is_refused(declared: config.Config) -> None:
    with pytest.raises(contract.Refusal) as raised:
        spec_module.assemble(
            a_spec(verification_command="curl-evil-thing"), delegation_id="d-0001", declared=declared
        )
    assert "curl-evil-thing" in raised.value.remedy


def test_every_prohibition_appears_verbatim(declared: config.Config) -> None:
    prompt = spec_module.assemble(a_spec(), delegation_id="d-0001", declared=declared)
    for prohibition in spec_module.PROHIBITIONS:
        assert prohibition in prompt, f"missing prohibition: {prohibition}"


def test_the_prohibitions_name_every_boundary_the_requirement_lists(declared: config.Config) -> None:
    joined = "\n".join(spec_module.PROHIBITIONS).lower()
    for boundary in ("commit", "push", "pull request", "publish", "credential", "network", "repl"):
        assert boundary in joined, f"no prohibition mentions {boundary}"
    assert "prime agent home" in joined


def test_the_completion_instruction_names_a_file_and_never_a_reply(declared: config.Config) -> None:
    prompt = spec_module.assemble(a_spec(), delegation_id="d-0001", declared=declared)
    signal = spec_module.signal_path("d-0001")
    assert str(signal) in prompt
    lowered = prompt.lower()
    assert "do not reply" in lowered or "never reply" in lowered
    assert "agent_message.send" not in prompt


def test_the_signal_path_is_the_only_carve_out_under_the_agent_home(declared: config.Config) -> None:
    """The child is told exactly one path it may write there, and nothing it may read."""
    prompt = spec_module.assemble(a_spec(), delegation_id="d-0001", declared=declared)
    signal = spec_module.signal_path("d-0001")
    assert signal.parent.name == spec_module.SIGNAL_DIR_NAME
    assert str(signal) in prompt
    assert "only file" in prompt.lower() or "only path" in prompt.lower()


def test_a_spec_missing_a_domain_is_rejected_before_assembly(declared: config.Config) -> None:
    with pytest.raises(contract.Refusal) as raised:
        spec_module.assemble(a_spec(domain=""), delegation_id="d-0001", declared=declared)
    assert "domain" in raised.value.remedy


def test_a_spec_missing_a_difficulty_is_rejected_before_assembly(declared: config.Config) -> None:
    with pytest.raises(contract.Refusal) as raised:
        spec_module.assemble(a_spec(difficulty=""), delegation_id="d-0001", declared=declared)
    assert "difficulty" in raised.value.remedy


def test_a_spec_with_an_empty_ownership_set_is_rejected(declared: config.Config) -> None:
    """An unbounded child cannot produce an ownership verdict, so it is not specified."""
    with pytest.raises(contract.Refusal):
        spec_module.assemble(a_spec(ownership=()), delegation_id="d-0001", declared=declared)


def test_a_spec_declaring_no_verification_command_is_refused(declared: config.Config) -> None:
    """Nothing to verify makes ship a rubber stamp."""
    with pytest.raises(contract.Refusal) as raised:
        spec_module.assemble(a_spec(verification_command=""), delegation_id="d-0001", declared=declared)
    assert "verification" in raised.value.remedy.lower()


def test_the_prompt_contains_no_file_content_the_orchestrator_did_not_supply(
    declared: config.Config,
) -> None:
    """Whatever is in the prompt came from the spec — this is what keeps context starved."""
    prompt = spec_module.assemble(a_spec(), delegation_id="d-0001", declared=declared)
    supplied = spec_module.assemble(a_spec(), delegation_id="d-0001", declared=declared)
    assert prompt == supplied, "assembly is not deterministic, so something outside the spec leaked in"
    assert "def fetch" not in prompt


def test_the_package_never_claims_enforced_isolation(declared: config.Config) -> None:
    """The kernel is documented as a durable control environment, not a sandbox."""
    prompt = spec_module.assemble(a_spec(), delegation_id="d-0001", declared=declared)
    lowered = prompt.lower()
    assert "sandbox" not in lowered
    assert "you are isolated" not in lowered
