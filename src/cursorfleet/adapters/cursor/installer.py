"""Plan, preview, apply and undo the Cursor kit install.

``build_install_plan`` and ``build_uninstall_plan`` are pure with respect to the
workspace: they only read files and return a :class:`Plan`. ``render_diff``
prints exactly what ``apply_plan`` will write. Nothing is written without a plan,
and the lockfile is always written last so a crash never records files that
were not written.

Invariants (tested):

* only paths on the managed allowlist are touched, never through symlinks;
* user content in ``hooks.json`` and ``AGENTS.md`` is preserved byte-for-byte
  where possible, and ``uninstall`` restores the pre-install bytes;
* ``init`` refuses on dirty conflicts instead of overwriting;
* ``init`` twice is a no-op (the lock has no timestamps);
* hooks emitted are exactly the enabled subset of ``ALLOWED_V01_HOOKS``.
"""

from __future__ import annotations

import base64
import binascii
import difflib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pydantic import ValidationError

from cursorfleet import __version__
from cursorfleet.adapters.cursor import blocks, hooksjson
from cursorfleet.adapters.cursor.fsutil import (
    UnsafePathError,
    atomic_write_text,
    ensure_inside,
    read_text,
    remove_empty_dirs,
    safe_text,
    sha256_text,
)
from cursorfleet.adapters.cursor.kit import (
    CONFIG_PATH,
    HOOKS_PATH,
    LOCK_PATH,
    ROSTER_PATH,
    build_kit,
    seed_config_text,
    seed_roster_text,
)
from cursorfleet.adapters.cursor.lock import (
    InstallLock,
    LockBlock,
    LockFile,
    LockHooks,
    dumps_lock,
    loads_lock,
)
from cursorfleet.config.io import loads_config, loads_roster
from cursorfleet.config.models import FleetConfig
from cursorfleet.config.roster import Roster, default_roster


class Action(StrEnum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


@dataclass(frozen=True)
class Change:
    path: str
    action: Action
    old: str | None
    new: str | None


@dataclass
class Plan:
    root: Path
    changes: list[Change] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    remove_dirs: list[str] = field(default_factory=list)

    @property
    def noop(self) -> bool:
        return not self.changes and not self.remove_dirs

    @property
    def touches_hooks(self) -> bool:
        return any(c.path == HOOKS_PATH for c in self.changes)


class _Reader:
    """Reads workspace files safely and turns problems into conflict messages."""

    def __init__(self, root: Path, problems: list[str]) -> None:
        self.root = root
        self.problems = problems

    def read(self, rel: str) -> str | None:
        try:
            return read_text(ensure_inside(self.root, rel))
        except (UnsafePathError, ValueError) as exc:
            self.problems.append(f"{rel}: {exc}")
            return None


# --------------------------------------------------------------------------------------
# Inputs


def load_inputs(root: Path, problems: list[str]) -> tuple[FleetConfig, Roster]:
    """Load committed config/roster if present, else defaults. Problems become conflicts."""
    reader = _Reader(root, problems)
    config = FleetConfig()
    roster = default_roster()
    cfg_text = reader.read(CONFIG_PATH)
    if cfg_text is not None:
        try:
            config = loads_config(cfg_text)
        except (ValueError, ValidationError) as exc:
            problems.append(f"{CONFIG_PATH}: invalid ({_first_line(exc)})")
    roster_text = reader.read(ROSTER_PATH)
    if roster_text is not None:
        try:
            roster = loads_roster(roster_text)
        except (ValueError, ValidationError) as exc:
            problems.append(f"{ROSTER_PATH}: invalid ({_first_line(exc)})")
    return config, roster


def _first_line(exc: Exception) -> str:
    return (str(exc).strip().splitlines() or ["error"])[0][:200]


def read_lock(root: Path, problems: list[str]) -> InstallLock | None:
    text = _Reader(root, problems).read(LOCK_PATH)
    if text is None:
        return None
    try:
        return loads_lock(text)
    except (ValueError, ValidationError) as exc:
        problems.append(f"{LOCK_PATH}: invalid lockfile ({_first_line(exc)})")
        return None


def _missing_dirs(root: Path, rel_path: str) -> list[str]:
    parts = rel_path.split("/")[:-1]
    missing: list[str] = []
    for i in range(1, len(parts) + 1):
        rel = "/".join(parts[:i])
        if not root.joinpath(*parts[:i]).exists():
            missing.append(rel)
    return missing


# --------------------------------------------------------------------------------------
# Install


def build_install_plan(root: Path) -> Plan:  # noqa: PLR0912, PLR0915
    """Compute what ``init --cursor`` would do in ``root`` (read-only)."""
    plan = Plan(root=root)
    reader = _Reader(root, plan.conflicts)
    config, roster = load_inputs(root, plan.conflicts)
    old_lock = read_lock(root, plan.conflicts)
    if plan.conflicts:
        return plan

    kit = build_kit(roster, config)
    old_files = old_lock.file_map() if old_lock else {}
    old_blocks = old_lock.block_map() if old_lock else {}
    new_files: list[LockFile] = []
    new_blocks: list[LockBlock] = []
    changes: list[Change] = []

    # 1. Whole generated files.
    for rel, desired in kit.files.items():
        disk = reader.read(rel)
        entry = old_files.get(rel)
        digest = sha256_text(desired)
        if disk is None:
            changes.append(Change(rel, Action.CREATE, None, desired))
            new_files.append(LockFile(path=rel, sha256=digest))
        elif sha256_text(disk) == digest:
            new_files.append(
                LockFile(path=rel, sha256=digest, adopted=entry.adopted if entry else True)
            )
        elif entry is not None and sha256_text(disk) == entry.sha256:
            changes.append(Change(rel, Action.MODIFY, disk, desired))
            new_files.append(LockFile(path=rel, sha256=digest, adopted=entry.adopted))
        elif entry is not None:
            plan.conflicts.append(
                f"{rel}: modified since CursorFleet installed it; move your changes into "
                f"{ROSTER_PATH} or delete the file, then re-run init"
            )
        else:
            plan.conflicts.append(
                f"{rel}: already exists and is not managed by CursorFleet; "
                "rename or remove it, then re-run init"
            )

    # 2. Files from an earlier install that the current roster no longer generates.
    for rel, entry in old_files.items():
        if rel in kit.files:
            continue
        if entry.kind == "seed":
            continue  # carried over in step 3
        disk = reader.read(rel)
        if disk is None:
            continue
        if sha256_text(disk) == entry.sha256 and not entry.adopted:
            changes.append(Change(rel, Action.DELETE, disk, None))
        else:
            plan.notes.append(f"{rel}: no longer generated; left in place (modified or adopted)")

    # 3. Seed files (config, roster): written only if absent, user-owned afterwards.
    seeds = {CONFIG_PATH: seed_config_text(), ROSTER_PATH: seed_roster_text(roster)}
    for rel, text in seeds.items():
        disk = reader.read(rel)
        if disk is None:
            changes.append(Change(rel, Action.CREATE, None, text))
            new_files.append(LockFile(path=rel, sha256=sha256_text(text), kind="seed"))
        elif rel in old_files:
            new_files.append(old_files[rel])

    # 4. Managed blocks in AGENTS.md files.
    for rel, block in kit.blocks.items():
        _plan_block(plan, reader, rel, block, old_blocks.get(rel), new_blocks, changes)

    # 5. hooks.json.
    lock_hooks = _plan_hooks(plan, reader, config, old_lock, changes)

    if plan.conflicts:
        return plan

    # 6. Directories we will create, and the lockfile itself (always last).
    dirs = list(old_lock.dirs_created) if old_lock else []
    for change in [*changes, Change(LOCK_PATH, Action.CREATE, None, "")]:
        if change.action is Action.CREATE:
            for d in _missing_dirs(root, change.path):
                if d not in dirs:
                    dirs.append(d)
    new_lock = InstallLock(
        cursorfleet_version=__version__,
        files=sorted(new_files, key=lambda f: f.path),
        blocks=sorted(new_blocks, key=lambda b: b.path),
        hooks=lock_hooks,
        dirs_created=dirs,
    )
    new_text = dumps_lock(new_lock)
    old_text = reader.read(LOCK_PATH)
    if old_text != new_text and not plan.conflicts:
        action = Action.CREATE if old_text is None else Action.MODIFY
        changes.append(Change(LOCK_PATH, action, old_text, new_text))
    plan.changes = changes
    return plan


def _plan_block(  # noqa: PLR0913, PLR0917
    plan: Plan,
    reader: _Reader,
    rel: str,
    block: str,
    entry: LockBlock | None,
    new_blocks: list[LockBlock],
    changes: list[Change],
) -> None:
    digest = sha256_text(block)
    disk = reader.read(rel)
    if disk is None:
        text, _ = blocks.insert_block("", block)
        changes.append(Change(rel, Action.CREATE, None, text))
        new_blocks.append(LockBlock(path=rel, sha256=digest, prefix="", file_created=True))
        return
    try:
        current = blocks.block_text(disk)
    except blocks.BlockError as exc:
        plan.conflicts.append(f"{rel}: {exc}; fix the markers by hand, then re-run init")
        return
    if current is None:
        text, prefix = blocks.insert_block(disk, block)
        changes.append(Change(rel, Action.MODIFY, disk, text))
        new_blocks.append(LockBlock(path=rel, sha256=digest, prefix=prefix))
    elif sha256_text(current) == digest:
        new_blocks.append(
            entry.model_copy(update={"sha256": digest})
            if entry
            else LockBlock(path=rel, sha256=digest)
        )
    elif entry is not None and sha256_text(current) == entry.sha256:
        changes.append(Change(rel, Action.MODIFY, disk, blocks.replace_block(disk, block)))
        new_blocks.append(entry.model_copy(update={"sha256": digest}))
    else:
        plan.conflicts.append(
            f"{rel}: the CursorFleet managed block was edited by hand; "
            "restore it or remove the block, then re-run init"
        )


def _plan_hooks(
    plan: Plan,
    reader: _Reader,
    config: FleetConfig,
    old_lock: InstallLock | None,
    changes: list[Change],
) -> LockHooks | None:
    try:
        wanted = hooksjson.assert_registrable(config.hooks.enabled)
    except hooksjson.HooksJsonError as exc:  # unreachable via config; defence in depth
        plan.conflicts.append(str(exc))
        return None
    disk = reader.read(HOOKS_PATH)
    old = old_lock.hooks if old_lock else None
    if disk is None and not wanted:
        return None
    previous_state = (
        hooksjson.HooksState(
            added_version=old.added_version,
            added_hooks_key=old.added_hooks_key,
            added_events=list(old.added_events),
            entries=dict(old.entries),
        )
        if old
        else None
    )
    try:
        merged = hooksjson.merge(
            disk, wanted, previous=old.entries if old else None, previous_state=previous_state
        )
    except hooksjson.HooksJsonError as exc:
        plan.conflicts.append(
            f"{HOOKS_PATH}: {exc}; fix the file by hand (CursorFleet never rewrites invalid JSON)"
        )
        return None
    plan.conflicts.extend(f"{HOOKS_PATH}: {c}" for c in merged.conflicts)

    if disk is None:
        changes.append(Change(HOOKS_PATH, Action.CREATE, None, merged.text))
    elif merged.text != disk:
        changes.append(Change(HOOKS_PATH, Action.MODIFY, disk, merged.text))

    if old is not None:
        original_sha, original_b64 = old.original_sha256, old.original_b64
        created = old.created
    else:
        created = disk is None
        original_sha = sha256_text(disk) if disk is not None else None
        original_b64 = (
            base64.b64encode(disk.encode("utf-8")).decode("ascii")
            if disk is not None and not merged.reproducible
            else None
        )
    return LockHooks(
        created=created,
        added_version=merged.state.added_version,
        added_hooks_key=merged.state.added_hooks_key,
        added_events=merged.state.added_events,
        entries=merged.state.entries,
        style=merged.style,
        installed_sha256=sha256_text(merged.text),
        original_sha256=original_sha,
        original_b64=original_b64,
    )


# --------------------------------------------------------------------------------------
# Uninstall


def build_uninstall_plan(root: Path, *, force: bool = False) -> Plan:  # noqa: PLR0912
    """Compute what ``uninstall`` would remove, driven only by the lockfile."""
    plan = Plan(root=root)
    reader = _Reader(root, plan.conflicts)
    lock = read_lock(root, plan.conflicts)
    if lock is None:
        if not plan.conflicts:
            plan.notes.append("No CursorFleet install found (no .cursorfleet/install.lock.json).")
        return plan

    changes: list[Change] = []
    keep_files: list[LockFile] = []
    keep_blocks: list[LockBlock] = []
    keep_hooks: LockHooks | None = None

    if lock.hooks is not None:
        keep_hooks = _plan_unhooks(plan, reader, lock.hooks, force, changes)

    for entry in lock.blocks:
        kept = _plan_unblock(plan, reader, entry, force, changes)
        if kept is not None:
            keep_blocks.append(kept)

    for fentry in lock.files:
        disk = reader.read(fentry.path)
        if disk is None:
            continue
        matches = sha256_text(disk) == fentry.sha256
        if fentry.kind == "seed":
            if matches:
                changes.append(Change(fentry.path, Action.DELETE, disk, None))
            else:
                plan.notes.append(f"{fentry.path}: edited by you; kept (yours now)")
        elif fentry.adopted:
            plan.notes.append(f"{fentry.path}: existed before init with identical content; kept")
        elif matches or force:
            changes.append(Change(fentry.path, Action.DELETE, disk, None))
        else:
            plan.drift.append(f"{fentry.path}: modified since install; skipped (use --force)")
            keep_files.append(fentry)

    lock_text = reader.read(LOCK_PATH)
    if keep_files or keep_blocks or keep_hooks is not None:
        remaining = lock.model_copy(
            update={"files": keep_files, "blocks": keep_blocks, "hooks": keep_hooks}
        )
        new_text = dumps_lock(remaining)
        if new_text != lock_text:
            changes.append(Change(LOCK_PATH, Action.MODIFY, lock_text, new_text))
    else:
        changes.append(Change(LOCK_PATH, Action.DELETE, lock_text, None))
        plan.remove_dirs = list(lock.dirs_created)
    plan.changes = changes
    return plan


def _plan_unhooks(
    plan: Plan, reader: _Reader, entry: LockHooks, force: bool, changes: list[Change]
) -> LockHooks | None:
    """Return the lock entry to keep (``None`` when hooks are fully handled)."""
    disk = reader.read(HOOKS_PATH)
    if disk is None:
        return None
    state = hooksjson.HooksState(
        added_version=entry.added_version,
        added_hooks_key=entry.added_hooks_key,
        added_events=list(entry.added_events),
        entries=dict(entry.entries),
    )
    try:
        result = hooksjson.unmerge(disk, state, entry.style, created=entry.created, force=force)
    except hooksjson.HooksJsonError as exc:
        plan.drift.append(f"{HOOKS_PATH}: {exc}; skipped")
        return entry
    if result.drift:
        plan.drift.extend(f"{HOOKS_PATH}: {d}; skipped (use --force)" for d in result.drift)
        return entry
    new_text = result.text
    unchanged_since_install = sha256_text(disk) == entry.installed_sha256
    if (
        entry.original_b64
        and entry.original_sha256
        and unchanged_since_install
        and sha256_text(new_text) != entry.original_sha256
    ):
        try:
            restored = base64.b64decode(entry.original_b64, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            restored = None
        if restored is not None and sha256_text(restored) == entry.original_sha256:
            new_text = restored
    if result.now_empty:
        changes.append(Change(HOOKS_PATH, Action.DELETE, disk, None))
    elif new_text != disk:
        changes.append(Change(HOOKS_PATH, Action.MODIFY, disk, new_text))
    return None


def _plan_unblock(
    plan: Plan, reader: _Reader, entry: LockBlock, force: bool, changes: list[Change]
) -> LockBlock | None:
    disk = reader.read(entry.path)
    if disk is None:
        return None
    try:
        current = blocks.block_text(disk)
    except blocks.BlockError as exc:
        plan.drift.append(f"{entry.path}: {exc}; skipped")
        return entry
    if current is None:
        return None
    if sha256_text(current) != entry.sha256 and not force:
        plan.drift.append(f"{entry.path}: managed block was edited; skipped (use --force)")
        return entry
    new_text = blocks.remove_block(disk, entry.prefix)
    if entry.file_created and new_text.strip() == "":
        changes.append(Change(entry.path, Action.DELETE, disk, None))
    else:
        changes.append(Change(entry.path, Action.MODIFY, disk, new_text))
    return None


# --------------------------------------------------------------------------------------
# Presentation and apply


def _diff_lines(text: str | None) -> list[str]:
    if not text:
        return []
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n\\ No newline at end of file\n"
    return lines


def render_diff(plan: Plan) -> str:
    """Exact unified diff of every change, safe to print to a terminal."""
    out: list[str] = []
    for change in plan.changes:
        old = _diff_lines(change.old)
        new = _diff_lines(change.new)
        from_file = "/dev/null" if change.action is Action.CREATE else f"a/{change.path}"
        to_file = "/dev/null" if change.action is Action.DELETE else f"b/{change.path}"
        out.append(f"diff --cursorfleet {change.action.value} {change.path}\n")
        out.extend(difflib.unified_diff(old, new, fromfile=from_file, tofile=to_file))
    return safe_text("".join(out))


def summarize(plan: Plan) -> list[str]:
    return [f"{c.action.value:<7} {safe_text(c.path)}" for c in plan.changes] + [
        f"rmdir   {safe_text(d)} (if empty)" for d in plan.remove_dirs
    ]


def apply_plan(plan: Plan) -> None:
    """Write ``plan`` to disk atomically, file by file, lockfile last (or removed last)."""
    if plan.conflicts:
        msg = "refusing to apply a plan with conflicts"
        raise RuntimeError(msg)
    for change in plan.changes:
        target = ensure_inside(plan.root, change.path)
        if change.action is Action.DELETE:
            target.unlink(missing_ok=True)
        elif change.new is not None:
            atomic_write_text(target, change.new)
    if plan.remove_dirs:
        remove_empty_dirs(plan.root, plan.remove_dirs)


# --------------------------------------------------------------------------------------
# Drift (used by doctor and validate)


@dataclass(frozen=True)
class DriftItem:
    path: str
    kind: str  # file | seed | block | hooks
    status: str  # ok | modified | missing | edited
    detail: str = ""

    @property
    def is_problem(self) -> bool:
        return self.status in {"modified", "missing"}


def check_drift(root: Path, lock: InstallLock) -> list[DriftItem]:  # noqa: PLR0912
    """Compare the workspace with the lockfile. Read-only; never raises on bad files."""
    items: list[DriftItem] = []
    problems: list[str] = []
    reader = _Reader(root, problems)
    for f in lock.files:
        disk = reader.read(f.path)
        if disk is None:
            if f.kind == "seed":
                items.append(DriftItem(f.path, "seed", "missing", "removed after install"))
            else:
                items.append(DriftItem(f.path, "file", "missing", "installed file is gone"))
        elif sha256_text(disk) == f.sha256:
            items.append(DriftItem(f.path, f.kind, "ok"))
        elif f.kind == "seed":
            items.append(DriftItem(f.path, "seed", "edited", "user-edited; expected"))
        else:
            items.append(DriftItem(f.path, "file", "modified", "content differs from install"))
    for b in lock.blocks:
        disk = reader.read(b.path)
        try:
            current = blocks.block_text(disk) if disk is not None else None
        except blocks.BlockError as exc:
            items.append(DriftItem(b.path, "block", "modified", str(exc)))
            continue
        if current is None:
            items.append(DriftItem(b.path, "block", "missing", "managed block is gone"))
        elif sha256_text(current) == b.sha256:
            items.append(DriftItem(b.path, "block", "ok"))
        else:
            items.append(DriftItem(b.path, "block", "modified", "managed block was edited"))
    if lock.hooks is not None:
        items.append(_check_hooks(reader, lock.hooks))
    return items


def _check_hooks(reader: _Reader, entry: LockHooks) -> DriftItem:
    disk = reader.read(HOOKS_PATH)
    if disk is None:
        return DriftItem(HOOKS_PATH, "hooks", "missing", "hooks.json is gone")
    try:
        events = hooksjson.effective_events(disk)
    except hooksjson.HooksJsonError as exc:
        return DriftItem(HOOKS_PATH, "hooks", "modified", str(exc))
    missing: list[str] = []
    modified: list[str] = []
    for event, recorded in entry.entries.items():
        ours = [e for e in events.get(event, []) if hooksjson.is_ours(e)]
        if not ours:
            missing.append(event)
        elif ours != [recorded]:
            modified.append(event)
    extra = sorted(
        e
        for e, entries in events.items()
        if e not in entry.entries and any(hooksjson.is_ours(x) for x in entries)
    )
    if missing or modified or extra:
        detail = "; ".join(
            part
            for part in (
                f"missing: {', '.join(missing)}" if missing else "",
                f"modified: {', '.join(modified)}" if modified else "",
                f"unrecorded: {', '.join(extra)}" if extra else "",
            )
            if part
        )
        return DriftItem(HOOKS_PATH, "hooks", "modified", detail)
    return DriftItem(HOOKS_PATH, "hooks", "ok")
