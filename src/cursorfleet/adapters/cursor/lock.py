"""The install lockfile ``.cursorfleet/install.lock.json``.

Records exactly what ``init`` wrote (paths, sha256, managed blocks, hook entries,
directories it created) so ``uninstall`` removes only that and ``doctor`` can
report drift. It contains no timestamps, so re-running ``init`` is a no-op.

The lock is data from the repository and therefore untrusted: every path is
validated against an allowlist of managed locations before any use.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cursorfleet.adapters.cursor.hooksjson import JsonStyle
from cursorfleet.adapters.cursor.kit import HOOKS_PATH, LOCK_PATH
from cursorfleet.events.pathcheck import check_not_in_git_dir, check_relative_posix

_STRICT = ConfigDict(extra="forbid", frozen=True)
_FILE_PREFIXES = (".cursor/agents/", ".cursor/rules/", ".cursor/skills/", ".cursorfleet/")
_SHA256 = r"^[0-9a-f]{64}$"
MAX_LOCK_BYTES = 256 * 1024


def is_managed_file_path(path: str) -> bool:
    """True for paths CursorFleet may create as whole files."""
    try:
        check_not_in_git_dir(check_relative_posix(path))
    except ValueError:
        return False
    return path.startswith(_FILE_PREFIXES) and path != LOCK_PATH


def is_managed_block_path(path: str) -> bool:
    """True for ``AGENTS.md`` files (root or nested) that may hold a managed block."""
    try:
        check_not_in_git_dir(check_relative_posix(path))
    except ValueError:
        return False
    return path == "AGENTS.md" or path.endswith("/AGENTS.md")


class LockFile(BaseModel):
    model_config = _STRICT

    path: str
    sha256: str = Field(pattern=_SHA256)
    kind: Literal["file", "seed"] = "file"  # seed = user-owned after creation (config, roster)
    adopted: bool = False  # pre-existed with identical content; never removed

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        if not is_managed_file_path(value):
            msg = f"not a managed file location: {value!r}"
            raise ValueError(msg)
        return value


class LockBlock(BaseModel):
    model_config = _STRICT

    path: str
    sha256: str = Field(pattern=_SHA256)  # of the block text (LF-normalized)
    prefix: str = Field(default="", max_length=4)  # separator inserted before the block
    file_created: bool = False

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        if not is_managed_block_path(value):
            msg = f"not a managed AGENTS.md location: {value!r}"
            raise ValueError(msg)
        return value

    @field_validator("prefix")
    @classmethod
    def _prefix(cls, value: str) -> str:
        if value.replace("\r", "").replace("\n", "") != "":
            msg = "prefix may only contain newlines"
            raise ValueError(msg)
        return value


class LockHooks(BaseModel):
    model_config = _STRICT

    path: str = HOOKS_PATH
    created: bool = False  # file did not exist before init
    added_version: bool = False
    added_hooks_key: bool = False
    added_events: list[str] = Field(default_factory=list)
    entries: dict[str, dict[str, Any]] = Field(default_factory=dict)
    style: JsonStyle = Field(default_factory=JsonStyle)
    installed_sha256: str = Field(pattern=_SHA256)
    original_sha256: str | None = Field(default=None, pattern=_SHA256)
    original_b64: str | None = Field(default=None, max_length=200_000)

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        if value != HOOKS_PATH:
            msg = "hooks path must be .cursor/hooks.json"
            raise ValueError(msg)
        return value


class InstallLock(BaseModel):
    model_config = _STRICT

    lock_version: Literal["1"] = "1"
    cursorfleet_version: str = Field(max_length=64)
    files: list[LockFile] = Field(default_factory=list)
    blocks: list[LockBlock] = Field(default_factory=list)
    hooks: LockHooks | None = None
    dirs_created: list[str] = Field(default_factory=list)

    @field_validator("dirs_created")
    @classmethod
    def _dirs(cls, value: list[str]) -> list[str]:
        for item in value:
            check_not_in_git_dir(check_relative_posix(item))  # only empty dirs are ever removed
        return value

    def file_map(self) -> dict[str, LockFile]:
        return {f.path: f for f in self.files}

    def block_map(self) -> dict[str, LockBlock]:
        return {b.path: b for b in self.blocks}


def dumps_lock(lock: InstallLock) -> str:
    data = lock.model_dump(mode="json")
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def loads_lock(text: str) -> InstallLock:
    """Parse lock text. Raises ``ValueError`` (including pydantic's) on any problem."""
    if len(text.encode("utf-8")) > MAX_LOCK_BYTES:
        msg = "install lockfile is too large"
        raise ValueError(msg)
    return InstallLock.model_validate_json(text)
