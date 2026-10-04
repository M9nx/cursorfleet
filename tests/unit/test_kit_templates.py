from __future__ import annotations

import pytest

from cursorfleet.adapters.cursor import kit
from cursorfleet.adapters.cursor.templates import TemplateError, read_template, render
from cursorfleet.config.io import loads_config, loads_roster
from cursorfleet.config.models import FleetConfig
from cursorfleet.config.roster import Role, default_roster
from cursorfleet.workflow.frontmatter import parse_frontmatter


def test_every_role_has_an_agent_template() -> None:
    for role in Role:
        if role is not Role.COORDINATOR:
            assert read_template(f"agents/{role.value}.md").strip()


def test_render_rejects_unknown_placeholder() -> None:
    with pytest.raises(TemplateError):
        render("hi {{nope}}", {})
    with pytest.raises(TemplateError):
        read_template("agents/does-not-exist.md")


def test_seed_files_parse_and_match_defaults() -> None:
    assert loads_config(kit.seed_config_text()) == FleetConfig()
    assert loads_roster(kit.seed_roster_text(default_roster())) == default_roster()


def test_kit_is_deterministic_and_has_no_coordinator_agent() -> None:
    roster, config = default_roster(), FleetConfig()
    first = kit.build_kit(roster, config)
    assert first == kit.build_kit(roster, config)
    assert not any("coordinator" in p and p.startswith(".cursor/agents/") for p in first.files)
    assert ".cursor/skills/cursorfleet-coordinator/SKILL.md" in first.files
    assert ".cursor/agents/cf-implementer-beta.md" not in first.files  # disabled by default


def test_agent_files_carry_only_the_five_supported_keys() -> None:
    roster, config = default_roster(), FleetConfig()
    for agent in roster.enabled_agents():
        meta = parse_frontmatter(kit.render_agent(roster, config, agent)).meta
        assert tuple(meta) == kit.SUBAGENT_FRONTMATTER_KEYS


def test_reviewer_independence_and_patcher_mapping_are_encoded() -> None:
    roster, config = default_roster(), FleetConfig()
    by_id = {a.id: kit.render_agent(roster, config, a) for a in roster.agents}
    assert "not-independent" in by_id["reviewer"]
    assert "Never fix anything yourself" in by_id["reviewer"]
    assert "Map every finding id" in by_id["patch-engineer"]
    assert "Verdict:" in by_id["qa-release"] and "Evidence:" in by_id["qa-release"]
    for text in by_id.values():
        assert "Do not paste your reasoning" in text


def test_coordinator_delivery_modes() -> None:
    config = FleetConfig()
    base = default_roster()
    for delivery, expect_skill, expect_rule in (
        ("skill", True, False),
        ("rule", False, True),
        ("both", True, True),
    ):
        roster = base.model_copy(
            update={"coordinator": base.coordinator.model_copy(update={"delivery": delivery})}
        )
        files = kit.build_kit(roster, config).files
        assert (".cursor/skills/cursorfleet-coordinator/SKILL.md" in files) is expect_skill
        assert (".cursor/rules/cursorfleet-coordinator.mdc" in files) is expect_rule
    off = base.model_copy(
        update={"coordinator": base.coordinator.model_copy(update={"enabled": False})}
    )
    files = kit.build_kit(off, config).files
    assert not any("coordinator" in p for p in files)


def test_rule_templates_have_valid_frontmatter_and_fit_the_limit() -> None:
    files = kit.build_kit(default_roster(), FleetConfig()).files
    for path, text in files.items():
        if path.startswith(".cursor/rules/"):
            assert path.endswith(".mdc")
            assert set(parse_frontmatter(text).meta) <= {"description", "globs", "alwaysApply"}
            assert len(text.splitlines()) < 500
