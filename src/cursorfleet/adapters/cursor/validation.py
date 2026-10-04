"""``cursorfleet validate``: check config, roster, generated kit and artifacts.

Read-only. Findings about files CursorFleet generated are errors; findings
about user-owned files (their own rules or agents) are warnings, because we
cannot know what Cursor accepts beyond what the docs say. PROVISIONAL: the
allowed frontmatter keys come from the Cursor docs (ADR 0001 A7), not a live run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import ValidationError

from cursorfleet.adapters.cursor import blocks
from cursorfleet.adapters.cursor.fsutil import (
    UnsafePathError,
    ensure_inside,
    is_link_like,
    read_text,
    sha256_text,
)
from cursorfleet.adapters.cursor.installer import check_drift, read_lock
from cursorfleet.adapters.cursor.kit import (
    AGENTS_DIR,
    CONFIG_PATH,
    LOCK_PATH,
    ROSTER_PATH,
    RULES_DIR,
    SKILLS_DIR,
    SUBAGENT_FRONTMATTER_KEYS,
    build_kit,
)
from cursorfleet.config.io import loads_config, loads_roster
from cursorfleet.config.models import FleetConfig
from cursorfleet.config.roster import Roster, default_roster
from cursorfleet.workflow.artifacts import MAX_ARTIFACT_BYTES, validate_artifact_text
from cursorfleet.workflow.frontmatter import FrontmatterError, parse_frontmatter

Severity = Literal["error", "warning"]
RULE_KEYS: frozenset[str] = frozenset({"description", "globs", "alwaysApply"})
SKILL_KEYS: frozenset[str] = frozenset({"name", "description"})
MAX_RULE_LINES = 500  # rules must stay strictly under this
MAX_ARTIFACT_FILES = 2000


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str
    message: str
    path: str | None = None
    hint: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "hint": self.hint,
        }


def _first_line(exc: Exception) -> str:
    return (str(exc).strip().splitlines() or ["error"])[0][:200]


class _Validator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings: list[Finding] = []

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        path: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.findings.append(Finding(severity, code, message, path, hint))

    def read(self, rel: str) -> str | None:
        try:
            return read_text(ensure_inside(self.root, rel))
        except (UnsafePathError, ValueError) as exc:
            self.add("error", "file.unreadable", _first_line(exc), rel)
            return None

    # -- config and roster ---------------------------------------------------------

    def load_config(self) -> FleetConfig | None:
        text = self.read(CONFIG_PATH)
        if text is None:
            return FleetConfig() if not self._has(CONFIG_PATH) else None
        try:
            return loads_config(text)
        except (ValueError, ValidationError) as exc:
            self.add(
                "error",
                "config.invalid",
                _first_line(exc),
                CONFIG_PATH,
                "Fix the value or delete the file and re-run `cursorfleet init --cursor`.",
            )
            return None

    def load_roster(self) -> Roster | None:
        text = self.read(ROSTER_PATH)
        if text is None:
            return default_roster() if not self._has(ROSTER_PATH) else None
        try:
            return loads_roster(text)
        except (ValueError, ValidationError) as exc:
            self.add(
                "error",
                "roster.invalid",
                _first_line(exc),
                ROSTER_PATH,
                "Fix the roster (ids are unique slugs; the coordinator is not a subagent).",
            )
            return None

    def _has(self, rel: str) -> bool:
        return self.root.joinpath(*rel.split("/")).exists()

    def check_roster(self, roster: Roster) -> None:
        names = [roster.cursor_name(a.id) for a in roster.agents]
        if len(set(names)) != len(names):
            self.add("error", "roster.duplicate_names", "two agents share a Cursor subagent name")
        if not roster.enabled_agents():
            self.add("warning", "roster.empty", "no subagent is enabled", ROSTER_PATH)
        coordinator_file = f"{AGENTS_DIR}/{roster.cursor_name('coordinator')}.md"
        if self._has(coordinator_file):
            self.add(
                "error",
                "roster.coordinator_as_subagent",
                "the coordinator must be the main agent (a skill), not a subagent file",
                coordinator_file,
                "Delete the file; the cursorfleet-coordinator skill delivers the coordinator.",
            )

    # -- generated kit -------------------------------------------------------------

    def check_kit(self, roster: Roster, config: FleetConfig) -> set[str]:  # noqa: PLR0912
        """Compare disk with the rendered kit. Returns the set of kit-owned file paths."""
        lock_errors: list[str] = []
        lock = read_lock(self.root, lock_errors)
        for err in lock_errors:
            self.add("error", "lock.invalid", err, LOCK_PATH)
        kit = build_kit(roster, config)
        installed = lock is not None or any(self._has(p) for p in kit.files)
        if not installed:
            self.add(
                "warning",
                "kit.not_installed",
                "the CursorFleet kit is not installed",
                None,
                "Run `cursorfleet init --cursor`.",
            )
            return set(kit.files)
        for rel, desired in kit.files.items():
            disk = self.read(rel)
            if disk is None:
                if not any(f.path == rel and f.code == "file.unreadable" for f in self.findings):
                    self.add(
                        "error",
                        "kit.missing",
                        "generated file is missing",
                        rel,
                        "Run `cursorfleet init --cursor` to regenerate it.",
                    )
            elif sha256_text(disk) != sha256_text(desired):
                self.add(
                    "error",
                    "kit.drift",
                    "file differs from what the templates and roster generate",
                    rel,
                    "Edit the roster instead of the file, then re-run `cursorfleet init --cursor`.",
                )
        for rel, block in kit.blocks.items():
            disk = self.read(rel)
            try:
                current = blocks.block_text(disk) if disk is not None else None
            except blocks.BlockError as exc:
                self.add("error", "kit.block_malformed", str(exc), rel)
                continue
            if current is None:
                self.add("error", "kit.block_missing", "managed block is missing", rel)
            elif sha256_text(current) != sha256_text(block):
                self.add("error", "kit.block_drift", "managed block differs from template", rel)
        if lock is not None:
            for item in check_drift(self.root, lock):
                if item.is_problem and item.kind == "hooks":
                    self.add("error", "kit.hooks_drift", item.detail, item.path)
            for entry in lock.files:
                if entry.kind == "file" and entry.path not in kit.files:
                    self.add(
                        "warning",
                        "kit.orphan",
                        "installed file is no longer generated by the roster",
                        entry.path,
                        "Re-run `cursorfleet init --cursor` to remove it.",
                    )
        return set(kit.files)

    # -- frontmatter checks --------------------------------------------------------

    def check_agents(self, roster: Roster, kit_files: set[str]) -> None:
        base = self.root / AGENTS_DIR
        if not base.is_dir() or is_link_like(base):
            return
        for entry in sorted(base.iterdir(), key=lambda p: p.name):
            rel = f"{AGENTS_DIR}/{entry.name}"
            if rel not in kit_files and not entry.name.startswith(roster.name_prefix or "\0"):
                continue
            text = self.read(rel)
            if text is None:
                continue
            try:
                meta = parse_frontmatter(text).meta
            except FrontmatterError as exc:
                self.add("error", "agent.frontmatter", str(exc), rel)
                continue
            extra = sorted(set(meta) - set(SUBAGENT_FRONTMATTER_KEYS))
            if extra:
                self.add(
                    "error",
                    "agent.frontmatter_key",
                    f"unsupported subagent frontmatter keys: {', '.join(extra)}",
                    rel,
                    f"Cursor supports only: {', '.join(SUBAGENT_FRONTMATTER_KEYS)}.",
                )
            for key in ("name", "description"):
                if not isinstance(meta.get(key), str) or not meta.get(key):
                    self.add("error", "agent.frontmatter_missing", f"missing {key}", rel)
            for key in ("readonly", "is_background"):
                if key in meta and not isinstance(meta[key], bool):
                    self.add("error", "agent.frontmatter_type", f"{key} must be true/false", rel)
            if meta.get("name") != PurePosixPath(entry.name).stem:
                self.add("error", "agent.name_mismatch", "name must equal the file name", rel)

    def check_rules(self, kit_files: set[str]) -> None:
        base = self.root / RULES_DIR
        if not base.is_dir() or is_link_like(base):
            return
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames.sort()
            for name in sorted(filenames):
                full = Path(dirpath) / name
                rel = full.relative_to(self.root).as_posix()
                ours = rel in kit_files
                sev: Severity = "error" if ours else "warning"
                if full.suffix != ".mdc":
                    self.add(
                        sev,
                        "rules.extension",
                        "rule files must be .mdc; Cursor ignores other extensions here",
                        rel,
                        "Rename to .mdc and add frontmatter.",
                    )
                    continue
                self._check_rule(rel, sev)

    def _check_rule(self, rel: str, sev: Severity) -> None:
        text = self.read(rel)
        if text is None:
            return
        if len(text.splitlines()) >= MAX_RULE_LINES:
            self.add(sev, "rules.too_long", f"rule has {MAX_RULE_LINES} or more lines", rel)
        try:
            meta = parse_frontmatter(text).meta
        except FrontmatterError as exc:
            self.add(sev, "rules.frontmatter", str(exc), rel, "Add a `---` frontmatter block.")
            return
        extra = sorted(set(meta) - RULE_KEYS)
        if extra:
            self.add(
                "warning",
                "rules.frontmatter_key",
                f"unrecognized rule keys: {', '.join(extra)}",
                rel,
            )
        if "alwaysApply" in meta and not isinstance(meta["alwaysApply"], bool):
            self.add(sev, "rules.frontmatter_type", "alwaysApply must be true/false", rel)

    def check_skills(self, kit_files: set[str]) -> None:
        for rel in sorted(p for p in kit_files if p.startswith(SKILLS_DIR + "/")):
            if not self._has(rel):
                continue
            text = self.read(rel)
            if text is None:
                continue
            try:
                meta = parse_frontmatter(text).meta
            except FrontmatterError as exc:
                self.add("error", "skill.frontmatter", str(exc), rel)
                continue
            extra = sorted(set(meta) - SKILL_KEYS)
            if extra:
                self.add("error", "skill.frontmatter_key", f"unsupported: {', '.join(extra)}", rel)
            if meta.get("name") != PurePosixPath(rel).parent.name:
                self.add("error", "skill.name_mismatch", "name must equal the directory", rel)
            if not isinstance(meta.get("description"), str) or not meta.get("description"):
                self.add("error", "skill.frontmatter_missing", "missing description", rel)

    # -- artifacts -----------------------------------------------------------------

    def check_artifacts(self, config: FleetConfig) -> int:
        work_rel = config.work.dir
        base = self.root.joinpath(*work_rel.split("/"))
        if not base.is_dir() or is_link_like(base):
            return 0
        count = 0
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames.sort()
            for name in sorted(filenames):
                full = Path(dirpath) / name
                inner = full.relative_to(base).as_posix()
                rel = f"{work_rel}/{inner}"
                if not name.endswith(".md") or name == "AGENTS.md":
                    continue
                count += 1
                if count > MAX_ARTIFACT_FILES:
                    self.add("warning", "artifact.too_many", "stopped after 2000 artifacts")
                    return count
                if is_link_like(full):
                    self.add("warning", "artifact.symlink", "symlink skipped", rel)
                    continue
                try:
                    if full.stat().st_size > MAX_ARTIFACT_BYTES:
                        self.add("error", "artifact.too_large", "artifact is too large", rel)
                        continue
                except OSError:
                    continue
                text = self.read(rel)
                if text is None:
                    continue
                for problem in validate_artifact_text(text, inner):
                    self.add("error", problem.code, problem.message, rel)
        return count


def validate_workspace(root: Path) -> tuple[list[Finding], dict[str, int]]:
    """Run every check. Returns ``(findings, stats)``."""
    v = _Validator(root)
    config = v.load_config()
    roster = v.load_roster()
    artifacts = 0
    if roster is not None:
        v.check_roster(roster)
    if roster is not None and config is not None:
        kit_files = v.check_kit(roster, config)
        v.check_agents(roster, kit_files)
        v.check_skills(kit_files)
        v.check_rules(kit_files)
    else:
        v.check_rules(set())
    artifacts = v.check_artifacts(config or FleetConfig())
    stats = {"artifacts": artifacts}
    return v.findings, stats
