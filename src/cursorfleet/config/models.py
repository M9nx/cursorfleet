"""Model of ``.cursorfleet/config.toml`` (schema_version "1.0"); source of config.schema.json.

Config is data, never code: nothing in it is executed. There is intentionally no
setting that stores prompts, thinking, responses, file contents or command
output, and none that enables a network call or a forbidden hook.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from cursorfleet.events.kinds import COMMAND_DISPLAY_MAX_CHARS
from cursorfleet.events.pathcheck import check_not_in_git_dir, check_relative_posix

# Must equal ALLOWED_V01_HOOKS (asserted by a unit test). Forbidden hooks are
# not representable, so a config file can never ask the installer to emit them.
HookName = Literal[
    "sessionStart",
    "sessionEnd",
    "preToolUse",
    "postToolUse",
    "postToolUseFailure",
    "subagentStart",
    "subagentStop",
    "beforeShellExecution",
    "afterShellExecution",
    "afterFileEdit",
    "preCompact",
    "stop",
]

_DEFAULT_HOOKS: tuple[HookName, ...] = (
    "sessionStart",
    "sessionEnd",
    "preToolUse",
    "postToolUse",
    "postToolUseFailure",
    "subagentStart",
    "subagentStop",
    "beforeShellExecution",
    "afterShellExecution",
    "afterFileEdit",
    "preCompact",
    "stop",
)

_STRICT = ConfigDict(extra="forbid", frozen=True)
_VersionStr = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}$")]


def _relative(value: str) -> str:
    return check_not_in_git_dir(check_relative_posix(value))


class RetentionConfig(BaseModel):
    """Spool retention. Defaults: 14 days or 50 MB per session, whichever comes first."""

    model_config = _STRICT

    max_age_days: int = Field(default=14, ge=1, le=365)
    max_session_mb: int = Field(default=50, ge=1, le=1024)


class PrivacyConfig(BaseModel):
    """Knobs can only reduce what is stored; they cannot add content fields."""

    model_config = _STRICT

    store_command_display: bool = False
    command_display_max_chars: int = Field(default=COMMAND_DISPLAY_MAX_CHARS, ge=20, le=200)
    hash_commands: bool = True


class HooksConfig(BaseModel):
    """Which passive hooks the installer registers (subset of the 12 allowed)."""

    model_config = _STRICT

    enabled: tuple[HookName, ...] = _DEFAULT_HOOKS

    @field_validator("enabled")
    @classmethod
    def _unique(cls, value: tuple[HookName, ...]) -> tuple[HookName, ...]:
        if len(set(value)) != len(value):
            msg = "hooks.enabled must not contain duplicates"
            raise ValueError(msg)
        return value


class GitConfig(BaseModel):
    """Read-only git/worktree collector settings."""

    model_config = _STRICT

    refresh_interval_s: int = Field(default=5, ge=1, le=3600)
    stale_after_hours: int = Field(default=72, ge=1, le=24 * 365)
    ahead_behind: bool = True


class TuiConfig(BaseModel):
    model_config = _STRICT

    refresh_interval_ms: int = Field(default=500, ge=100, le=10_000)


class CursorConfig(BaseModel):
    """Cursor-specific settings."""

    model_config = _STRICT

    validated_versions: tuple[_VersionStr, ...] = Field(
        default=(),
        description="Cursor versions you have verified; `doctor` warns on others. "
        "Empty until a live capture has been reviewed (ADR 0001).",
    )


class WorkConfig(BaseModel):
    model_config = _STRICT

    dir: Annotated[str, AfterValidator(_relative)] = Field(
        default=".cursorfleet/work",
        description="Workspace-relative directory holding agent-declared Markdown artifacts.",
    )


class FleetConfig(BaseModel):
    """Root of ``.cursorfleet/config.toml``."""

    model_config = _STRICT

    schema_version: Literal["1.0"] = "1.0"
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    tui: TuiConfig = Field(default_factory=TuiConfig)
    cursor: CursorConfig = Field(default_factory=CursorConfig)
    work: WorkConfig = Field(default_factory=WorkConfig)


__all__ = [
    "CursorConfig",
    "FleetConfig",
    "GitConfig",
    "HookName",
    "HooksConfig",
    "PrivacyConfig",
    "RetentionConfig",
    "TuiConfig",
    "WorkConfig",
]
