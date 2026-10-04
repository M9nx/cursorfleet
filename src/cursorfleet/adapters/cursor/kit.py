"""Render the Cursor kit (subagents, skills, rules, AGENTS.md blocks) from the roster.

Pure and deterministic: the same roster, config and templates always yield the
same bytes (no timestamps, no versions, no environment). Nothing here touches
the filesystem except reading packaged templates.

Frontmatter written for subagents is limited to ``name``, ``description``,
``model``, ``readonly`` and ``is_background`` (ADR 0001, A7). ``capability_notes``
in the roster are documentation only and are never rendered as if enforced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from cursorfleet.adapters.cursor import blocks
from cursorfleet.adapters.cursor.templates import read_template, render
from cursorfleet.config.models import FleetConfig
from cursorfleet.config.roster import AgentSpec, Role, Roster
from cursorfleet.workflow.frontmatter import yaml_string

ROOT_AGENTS_MD = "AGENTS.md"
CONFIG_PATH = ".cursorfleet/config.toml"
ROSTER_PATH = ".cursorfleet/roster.toml"
LOCK_PATH = ".cursorfleet/install.lock.json"
HOOKS_PATH = ".cursor/hooks.json"
AGENTS_DIR = ".cursor/agents"
RULES_DIR = ".cursor/rules"
SKILLS_DIR = ".cursor/skills"
COORDINATOR_SKILL = "cursorfleet-coordinator"
ARTIFACTS_SKILL = "cursorfleet-artifacts"
SUBAGENT_FRONTMATTER_KEYS: tuple[str, ...] = (
    "name",
    "description",
    "model",
    "readonly",
    "is_background",
)
_COORDINATOR_SUFFIX = (
    " Use for planned, reviewed or parallel multi-agent changes; skip it for small "
    "single-file edits."
)


@dataclass(frozen=True)
class Kit:
    """Everything ``init`` generates, keyed by workspace-relative POSIX path."""

    files: dict[str, str] = field(default_factory=dict)  # whole files CursorFleet owns
    blocks: dict[str, str] = field(default_factory=dict)  # managed blocks in shared files


def agent_file_path(roster: Roster, agent: AgentSpec) -> str:
    return f"{AGENTS_DIR}/{roster.cursor_name(agent.id)}.md"


def _first_name(roster: Roster, role: Role) -> str:
    for agent in roster.enabled_agents():
        if agent.role is role:
            return f"`{roster.cursor_name(agent.id)}`"
    return f"(no enabled {role.value} agent)"


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def roster_table(roster: Roster) -> str:
    rows = ["| Subagent | Role | Access | Use for |", "| --- | --- | --- | --- |"]
    for agent in roster.enabled_agents():
        access = "read-only" if agent.readonly else "can edit"
        name = roster.cursor_name(agent.id)
        rows.append(f"| `{name}` | {agent.role.value} | {access} | {_cell(agent.description)} |")
    return "\n".join(rows)


def _values(roster: Roster, config: FleetConfig, agent: AgentSpec | None) -> dict[str, str]:
    values: dict[str, str] = {
        "work_dir": config.work.dir,
        "name_prefix": roster.name_prefix,
        "roster_table": roster_table(roster),
        "coordinator_description": yaml_string(
            roster.coordinator.description.rstrip() + _COORDINATOR_SUFFIX
        ),
        "name": "",
        "id": "",
    }
    for role in Role:
        if role is not Role.COORDINATOR:
            values[f"role.{role.value}"] = _first_name(roster, role)
    if agent is not None:
        values["name"] = f"`{roster.cursor_name(agent.id)}`"
        values["id"] = agent.id
    return values


def render_agent(roster: Roster, config: FleetConfig, agent: AgentSpec) -> str:
    """Render one ``.cursor/agents/<name>.md`` file (frontmatter limited to 5 keys)."""
    name = roster.cursor_name(agent.id)
    front = [
        "---",
        f"name: {name}",
        f"description: {yaml_string(agent.description)}",
        f"model: {yaml_string(agent.model) if agent.model != 'inherit' else 'inherit'}",
        f"readonly: {'true' if agent.readonly else 'false'}",
        f"is_background: {'true' if agent.is_background else 'false'}",
        "---",
        "",
        "",
    ]
    body = render(read_template(f"agents/{agent.role.value}.md"), _values(roster, config, agent))
    return "\n".join(front)[:-1] + body.rstrip("\n") + "\n"


def _coordinator_body(roster: Roster, config: FleetConfig) -> str:
    template = read_template(f"skills/{COORDINATOR_SKILL}/SKILL.md")
    return render(template, _values(roster, config, None))


def _skill_to_rule(skill_text: str, description: str) -> str:
    """Turn the coordinator SKILL.md into an on-demand rule (same body, rule frontmatter)."""
    body = skill_text.split("\n---\n", 1)[1].lstrip("\n")
    front = f"---\ndescription: {description}\nalwaysApply: false\n---\n\n"
    return front + body


def build_kit(roster: Roster, config: FleetConfig) -> Kit:
    """Build the full kit for ``roster`` and ``config``."""
    files: dict[str, str] = {}
    for agent in roster.enabled_agents():
        files[agent_file_path(roster, agent)] = render_agent(roster, config, agent)

    values = _values(roster, config, None)
    files[f"{SKILLS_DIR}/{ARTIFACTS_SKILL}/SKILL.md"] = render(
        read_template(f"skills/{ARTIFACTS_SKILL}/SKILL.md"), values
    )
    files[f"{RULES_DIR}/cursorfleet-core.mdc"] = render(
        read_template("rules/cursorfleet-core.mdc"), values
    )
    files[f"{RULES_DIR}/cursorfleet-handoff.mdc"] = render(
        read_template("rules/cursorfleet-handoff.mdc"), values
    )
    coordinator = roster.coordinator
    if coordinator.enabled:
        skill_text = _coordinator_body(roster, config)
        if coordinator.delivery in {"skill", "both"}:
            files[f"{SKILLS_DIR}/{COORDINATOR_SKILL}/SKILL.md"] = skill_text
        if coordinator.delivery in {"rule", "both"}:
            files[f"{RULES_DIR}/cursorfleet-coordinator.mdc"] = _skill_to_rule(
                skill_text, values["coordinator_description"]
            )

    kit_blocks = {
        ROOT_AGENTS_MD: blocks.make_block(render(read_template("agents-md/root.md"), values)),
        f"{config.work.dir}/AGENTS.md": blocks.make_block(
            render(read_template("agents-md/work.md"), values)
        ),
    }
    return Kit(files=dict(sorted(files.items())), blocks=kit_blocks)


# ---- seed files: written only if absent, then owned by the user -------------------------


def seed_config_text() -> str:
    return read_template("config/config.toml")


def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _toml_str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        items = "".join(f"  {_toml_value(v)},\n" for v in value)
        return f"[\n{items}]"
    msg = f"unsupported TOML value: {type(value).__name__}"
    raise TypeError(msg)


def _toml_table(data: dict[str, object]) -> list[str]:
    return [f"{key} = {_toml_value(value)}" for key, value in data.items()]


def seed_roster_text(roster: Roster) -> str:
    """Render ``roster`` as TOML (the roster has only scalars, string lists and 2 table kinds)."""
    dumped = roster.model_dump(mode="json")
    out = [
        "# CursorFleet roster (committed; data only, never executed).",
        "# Source of truth for the generated .cursor/agents/*.md files: edit this file,",
        "# then run `cursorfleet init --cursor` again. `capability_notes` are documentation",
        "# only; Cursor cannot enforce per-agent tools, paths or network, and v0.1 does not.",
        f"schema_version = {_toml_str(dumped['schema_version'])}",
        f"name_prefix = {_toml_str(dumped['name_prefix'])}",
        "",
        "[coordinator]",
        *_toml_table(dumped["coordinator"]),
    ]
    for agent in dumped["agents"]:
        out += ["", "[[agents]]", *_toml_table(agent)]
    return "\n".join(out) + "\n"
