from __future__ import annotations

import pytest
from pydantic import ValidationError

from cursorfleet.config.io import loads_roster
from cursorfleet.config.roster import AgentSpec, CoordinatorSpec, Role, Roster, default_roster

SEVEN = [
    "architect",
    "repo-scout",
    "implementer-alpha",
    "test-engineer",
    "reviewer",
    "patch-engineer",
    "qa-release",
]


def test_default_roster_contents() -> None:
    roster = default_roster()
    assert roster.coordinator.id == "coordinator"
    assert [a.id for a in roster.enabled_agents()] == SEVEN
    beta = next(a for a in roster.agents if a.id == "implementer-beta")
    assert beta.enabled is False
    assert len(roster.agents) == 8


def test_default_roster_readonly_and_models() -> None:
    by_id = {a.id: a for a in default_roster().agents}
    for readonly in ("architect", "repo-scout", "reviewer"):
        assert by_id[readonly].readonly is True
    for writer in ("implementer-alpha", "test-engineer", "patch-engineer", "qa-release"):
        assert by_id[writer].readonly is False
    assert all(a.model == "inherit" for a in by_id.values())
    assert not any(a.is_background for a in by_id.values())


def test_coordinator_is_not_a_subagent() -> None:
    roster = default_roster()
    assert "coordinator" not in {a.id for a in roster.agents}
    with pytest.raises(ValidationError, match="not a subagent"):
        AgentSpec(id="boss", role=Role.COORDINATOR, description="x" * 30, readonly=True)


def test_duplicate_ids_rejected() -> None:
    roster = default_roster()
    with pytest.raises(ValidationError, match="unique"):
        Roster(coordinator=roster.coordinator, agents=(roster.agents[0], roster.agents[0]))
    clash = AgentSpec.model_construct(**{**roster.agents[0].model_dump(), "id": "coordinator"})
    with pytest.raises(ValidationError, match="unique"):
        Roster(coordinator=roster.coordinator, agents=(clash,))


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentSpec.model_validate(
            {
                "id": "x-agent",
                "role": "qa",
                "description": "d" * 30,
                "readonly": True,
                "tools": ["Shell"],
            }
        )
    with pytest.raises(ValidationError):
        CoordinatorSpec.model_validate({"description": "d" * 30, "id": "other"})


@pytest.mark.parametrize("bad_id", ["Reviewer", "../x", "a", "x y", "-x"])
def test_bad_ids_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        AgentSpec(id=bad_id, role=Role.QA, description="d" * 30, readonly=True)


def test_cursor_name_and_role_mapping() -> None:
    roster = default_roster()
    assert roster.cursor_name("reviewer") == "cf-reviewer"
    assert roster.role_for_subagent_type("cf-reviewer") == "reviewer"
    assert roster.role_for_subagent_type("reviewer") == "reviewer"
    assert roster.role_for_subagent_type("generalPurpose") is None
    assert roster.role_for_subagent_type("explore") is None
    assert roster.role_for_subagent_type("") is None


def test_empty_prefix_supported() -> None:
    roster = default_roster().model_copy(update={"name_prefix": ""})
    assert roster.cursor_name("architect") == "architect"
    assert roster.role_for_subagent_type("architect") == "architect"


def test_roundtrip_through_json_and_toml() -> None:
    roster = default_roster()
    assert Roster.model_validate_json(roster.model_dump_json()) == roster
    toml = (
        'name_prefix = "x-"\n\n'
        '[coordinator]\ndescription = "Main agent playbook for the fleet."\n\n'
        '[[agents]]\nid = "solo"\nrole = "implementer"\nreadonly = false\n'
        'description = "Implements things when asked to."\ncapability_notes = ["docs only"]\n'
    )
    parsed = loads_roster(toml)
    assert parsed.cursor_name("solo") == "x-solo"
    assert parsed.agents[0].capability_notes == ("docs only",)
