"""Model of ``.cursorfleet/roster.toml`` (schema_version "1.0") and the default roster.

The roster is the source of truth. Generators (M1) render ``.cursor/agents/*.md``,
rules and skills from it; roster semantics are never stored only in Markdown.

Cursor subagent frontmatter supports only name, description, model, readonly and
is_background (ADR 0001, A7). Everything under ``capability_notes`` is
DOCUMENTATION ONLY: Cursor cannot enforce per-agent tools, paths, network or git
capability, and v0.1 does not either.

PROVISIONAL (ADR 0001 Q2): how a custom subagent name appears in
``subagent_type``. ``Roster.role_for_subagent_type`` degrades to ``None`` for
anything unrecognised so callers fall back to the raw value.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

_STRICT = ConfigDict(extra="forbid", frozen=True)

RosterId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9\-]{1,39}$")]
Model = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/\[\]=,\- ]{0,127}$")]
Note = Annotated[str, Field(min_length=1, max_length=200)]


class Role(StrEnum):
    """Workflow function. Several agents may share one role (alpha/beta implementers)."""

    COORDINATOR = "coordinator"
    ARCHITECT = "architect"
    SCOUT = "scout"
    IMPLEMENTER = "implementer"
    TESTER = "tester"
    REVIEWER = "reviewer"
    PATCHER = "patcher"
    QA = "qa"


class AgentSpec(BaseModel):
    """A Cursor subagent rendered to ``.cursor/agents/<name>.md``."""

    model_config = _STRICT

    id: RosterId = Field(description="Stable slug; also the value stored in event.agent_role.")
    role: Role
    description: str = Field(
        min_length=20,
        max_length=1024,
        description="Delegation hint Cursor reads; keep it sharp (when to use, when not to).",
    )
    readonly: bool = Field(description="Cursor's only permission-like switch; coarse.")
    model: Model = "inherit"
    is_background: bool = False
    enabled: bool = True
    capability_notes: tuple[Note, ...] = Field(
        default=(),
        max_length=10,
        description="DOCUMENTATION ONLY. Not enforced by Cursor or by CursorFleet v0.1.",
    )

    @model_validator(mode="after")
    def _not_coordinator(self) -> Self:
        if self.role is Role.COORDINATOR:
            msg = "the coordinator is the main agent, not a subagent; use roster.coordinator"
            raise ValueError(msg)
        return self


class CoordinatorSpec(BaseModel):
    """The main agent, driven by a skill and/or rule. Never rendered as a subagent file.

    Design choice (ADR 0001 A7), not a platform limit.
    """

    model_config = _STRICT

    id: Literal["coordinator"] = "coordinator"
    role: Literal[Role.COORDINATOR] = Role.COORDINATOR
    description: str = Field(min_length=20, max_length=1024)
    delivery: Literal["skill", "rule", "both"] = "skill"
    enabled: bool = True
    capability_notes: tuple[Note, ...] = Field(default=(), max_length=10)


class Roster(BaseModel):
    """Root of ``.cursorfleet/roster.toml``."""

    model_config = _STRICT

    schema_version: Literal["1.0"] = "1.0"
    name_prefix: Annotated[str, Field(pattern=r"^([a-z][a-z0-9]{0,15}-)?$")] = Field(
        default="cf-",
        description="Prefix for generated Cursor subagent names. PROVISIONAL (ADR 0001 Q2).",
    )
    coordinator: CoordinatorSpec
    agents: tuple[AgentSpec, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [self.coordinator.id, *(a.id for a in self.agents)]
        if len(set(ids)) != len(ids):
            msg = "roster ids must be unique and must not reuse 'coordinator'"
            raise ValueError(msg)
        return self

    def enabled_agents(self) -> tuple[AgentSpec, ...]:
        return tuple(a for a in self.agents if a.enabled)

    def cursor_name(self, agent_id: str) -> str:
        """Subagent name written to ``.cursor/agents`` frontmatter and filename."""
        return f"{self.name_prefix}{agent_id}"

    def role_for_subagent_type(self, subagent_type: str) -> str | None:
        """Map a hook ``subagent_type`` to a roster id, or ``None`` if unrecognised.

        Accepts the prefixed Cursor name or the bare id. Built-ins such as
        ``generalPurpose`` and ``explore`` return ``None``; callers then keep the
        raw value as ``agent_role``.
        """
        bare = subagent_type.removeprefix(self.name_prefix) if self.name_prefix else subagent_type
        for agent in self.agents:
            if bare == agent.id:
                return agent.id
        return None


def default_roster() -> Roster:
    """Default roster: the coordinator plus 7 enabled subagents; implementer-beta is off."""
    return Roster(
        coordinator=CoordinatorSpec(
            description=(
                "Main-agent playbook: split work, delegate to roster subagents, track handoffs "
                "and blockers in .cursorfleet/work/, and never declare done on its own."
            ),
            capability_notes=(
                "Runs as the main agent via a skill; it is not a subagent file.",
                "Asks for isolated worktrees in the prompt when parallel implementers are used.",
            ),
        ),
        agents=(
            AgentSpec(
                id="architect",
                role=Role.ARCHITECT,
                description=(
                    "Use for design and planning before code changes: module boundaries, "
                    "interfaces, trade-offs, a written plan. Do not use for implementation."
                ),
                readonly=True,
                capability_notes=("Intended to read the repo and write plan artifacts only.",),
            ),
            AgentSpec(
                id="repo-scout",
                role=Role.SCOUT,
                description=(
                    "Use to map unfamiliar code: find files, trace call paths, summarize "
                    "conventions. Read-only exploration; do not use to change code."
                ),
                readonly=True,
                capability_notes=("Intended to be read-only; cheap model is acceptable.",),
            ),
            AgentSpec(
                id="implementer-alpha",
                role=Role.IMPLEMENTER,
                description=(
                    "Use to implement a scoped, already-planned change in the working tree and "
                    "report a handoff. Do not use for design or for reviewing its own work."
                ),
                readonly=False,
                capability_notes=(
                    "Intended write scope: files named in the plan.",
                    "Ask for an isolated worktree when running beside another implementer.",
                ),
            ),
            AgentSpec(
                id="test-engineer",
                role=Role.TESTER,
                description=(
                    "Use to write and run tests for a change and report results. "
                    "Do not use to change production code beyond testability hooks."
                ),
                readonly=False,
                capability_notes=("Intended write scope: test directories and fixtures.",),
            ),
            AgentSpec(
                id="reviewer",
                role=Role.REVIEWER,
                description=(
                    "Use for independent review of a diff: correctness, security, privacy, "
                    "conventions. Read-only; never fixes issues itself, hands them to the patcher."
                ),
                readonly=True,
                capability_notes=(
                    "Pin a different model family than the implementer for independence; "
                    "Cursor may silently fall back to a compatible model.",
                ),
            ),
            AgentSpec(
                id="patch-engineer",
                role=Role.PATCHER,
                description=(
                    "Use to apply review findings with minimal, targeted fixes and re-report. "
                    "Do not use for new features or refactors."
                ),
                readonly=False,
                capability_notes=("Intended write scope: files cited in review findings.",),
            ),
            AgentSpec(
                id="qa-release",
                role=Role.QA,
                description=(
                    "Use to verify a finished change: clean install, lint, types, tests, build, "
                    "release notes. Reports evidence; does not edit source."
                ),
                readonly=False,
                capability_notes=(
                    "Needs shell access (so not readonly) but is intended not to edit source.",
                    "Cursor has no clean-environment primitive; v0.1 cannot guarantee one.",
                ),
            ),
            AgentSpec(
                id="implementer-beta",
                role=Role.IMPLEMENTER,
                description=(
                    "Optional second implementer for parallel work in its own worktree. "
                    "Disabled by default; enable only when tasks are truly independent."
                ),
                readonly=False,
                enabled=False,
                capability_notes=("Parallel work without isolation can overwrite alpha's edits.",),
            ),
        ),
    )


__all__ = [
    "AgentSpec",
    "CoordinatorSpec",
    "Role",
    "Roster",
    "default_roster",
]
