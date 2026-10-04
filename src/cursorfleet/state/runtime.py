"""Runtime directory resolution and private-file helpers. Stdlib only (hot-path safe).

Layout (ADR 0002)::

    <git-common-dir>/cursorfleet/
      LAYOUT, hmac.key, spool/<session>/<writer>.jsonl, index/state.sqlite,
      locks/indexer.lock, quarantine/

PROVISIONAL (ADR 0001 Q4): that the common dir resolves identically from every
Cursor surface (IDE, CLI, Agents Window worktrees) is unverified.
"""

from __future__ import annotations

import os
import stat

LAYOUT_VERSION = "1"
RUNTIME_DIRNAME = "cursorfleet"
_MAX_WALK = 64
_MAX_SMALL_READ = 4096

DIR_MODE = 0o700
FILE_MODE = 0o600


class GitLocation:
    """Where a path sits in git, found by reading ``.git`` files (no subprocess).

    A plain class on purpose: ``dataclasses`` costs ~12 ms of import time on the hook hot path.
    """

    __slots__ = ("common_dir", "git_dir", "top_level")

    def __init__(self, top_level: str, git_dir: str, common_dir: str) -> None:
        self.top_level = top_level  # realpath of the directory containing the ``.git`` entry
        self.git_dir = git_dir  # realpath of this worktree's git dir (== common for main)
        self.common_dir = common_dir  # realpath of the shared git dir

    def __repr__(self) -> str:
        return f"GitLocation({self.top_level!r}, {self.git_dir!r}, {self.common_dir!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, GitLocation) and (
            (self.top_level, self.git_dir, self.common_dir)
            == (other.top_level, other.git_dir, other.common_dir)
        )

    def __hash__(self) -> int:
        return hash((self.top_level, self.git_dir, self.common_dir))


class RuntimePaths:
    """Absolute paths (``str``: no pathlib import on the hot path) in the runtime dir."""

    __slots__ = ("root",)

    def __init__(self, root: str) -> None:
        self.root = root

    @property
    def spool(self) -> str:
        return os.path.join(self.root, "spool")

    @property
    def index_dir(self) -> str:
        return os.path.join(self.root, "index")

    @property
    def db(self) -> str:
        return os.path.join(self.index_dir, "state.sqlite")

    @property
    def locks(self) -> str:
        return os.path.join(self.root, "locks")

    @property
    def indexer_lock(self) -> str:
        return os.path.join(self.locks, "indexer.lock")

    @property
    def quarantine(self) -> str:
        return os.path.join(self.root, "quarantine")

    @property
    def hmac_key(self) -> str:
        return os.path.join(self.root, "hmac.key")

    @property
    def layout(self) -> str:
        return os.path.join(self.root, "LAYOUT")


def runtime_paths(common_dir: str | os.PathLike[str]) -> RuntimePaths:
    return RuntimePaths(os.path.join(os.fspath(common_dir), RUNTIME_DIRNAME))


def safe_realpath(path: str) -> str:
    """``os.path.realpath`` that still works when ``getcwd`` is unusable.

    Windows ``ntpath.realpath`` can call ``getcwd`` even for a drive-absolute path.
    If that raises and ``path`` is already absolute, fall back to ``normpath``
    (no further symlink resolution). Never used for relative paths: those stay
    rejected so a broken cwd cannot silently mean "somewhere else".
    """
    try:
        return os.path.realpath(path)
    except OSError:
        if os.path.isabs(path):
            return os.path.normpath(path)
        raise


def _read_small(path: str) -> str:
    with open(path, "rb") as handle:
        return handle.read(_MAX_SMALL_READ).decode("utf-8", "replace")


def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[0].strip() if lines else ""


def _resolve_gitfile(entry: str) -> tuple[str, str] | None:
    """Return ``(git_dir, common_dir)`` for a ``.git`` file (linked worktree/submodule)."""
    line = _first_line(_read_small(entry))
    if not line.startswith("gitdir:"):
        return None
    gitdir = line[len("gitdir:") :].strip()
    if not gitdir:
        return None
    if not os.path.isabs(gitdir):
        gitdir = os.path.join(os.path.dirname(entry), gitdir)
    gitdir = safe_realpath(gitdir)
    common = gitdir
    commondir_file = os.path.join(gitdir, "commondir")
    if os.path.isfile(commondir_file):
        value = _first_line(_read_small(commondir_file))
        if value:
            common = safe_realpath(value if os.path.isabs(value) else os.path.join(gitdir, value))
    return gitdir, common


def find_git_location(start: str) -> GitLocation | None:  # noqa: PLR0911
    """Walk up from ``start`` looking for ``.git``; resolve it without spawning git.

    Equivalent to ``git rev-parse --show-toplevel / --git-dir / --git-common-dir`` for
    ordinary checkouts, linked worktrees and submodules (contract-tested against git).
    Returns ``None`` outside a git repo. Never raises.
    """
    if not start or not os.path.isabs(start):
        return None  # relative/empty starts would silently mean "the cwd"
    try:
        current = safe_realpath(start)
        for _ in range(_MAX_WALK):
            entry = os.path.join(current, ".git")
            if os.path.lexists(entry):
                if os.path.isdir(entry):
                    real = safe_realpath(entry)
                    return GitLocation(current, real, real)
                resolved = _resolve_gitfile(entry)
                if resolved is None:
                    return None
                return GitLocation(current, resolved[0], resolved[1])
            parent = os.path.dirname(current)
            if parent == current:
                return None
            current = parent
    except (OSError, ValueError):
        return None
    return None


_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
INSTALL_MARKER_DIR = ".cursorfleet"
INSTALL_MARKER_NAME = "config.toml"


def _is_link_like(info: os.stat_result) -> bool:
    """True for a symlink or a Windows reparse point (junction), matching ``untrusted_reason``."""
    return bool(
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def has_install_marker(top_level: str) -> bool:
    """True when ``<top_level>/.cursorfleet/config.toml`` is a regular file (ADR 0002).

    The marker must exist before any runtime directory or event file is created.
    A symlink or junction on ``.cursorfleet`` or ``config.toml`` (including a
    link-to-elsewhere) is refused, consistent with runtime path safety.
    Never creates files. Never raises.
    """
    if not top_level:
        return False
    try:
        directory = os.path.join(top_level, INSTALL_MARKER_DIR)
        marker = os.path.join(directory, INSTALL_MARKER_NAME)
        dir_info = os.lstat(directory)
        file_info = os.lstat(marker)
        real = safe_realpath(marker)
        real_info = os.lstat(real)
        root_real = safe_realpath(top_level)
        prefix = root_real if root_real.endswith(os.sep) else root_real + os.sep
        return (
            not _is_link_like(dir_info)
            and stat.S_ISDIR(dir_info.st_mode)
            and not _is_link_like(file_info)
            and stat.S_ISREG(file_info.st_mode)
            and not _is_link_like(real_info)
            and stat.S_ISREG(real_info.st_mode)
            and os.path.normcase(real).startswith(os.path.normcase(prefix))
        )
    except OSError:
        return False


def resolve_inherited_location(start: str) -> GitLocation | None:
    """Nearest Git root from ``start`` if it already has the install marker.

    Stops at the first ``.git`` directory or gitfile. Does not walk past an inner
    repository boundary when that root has no marker. Creates nothing. Never raises.
    """
    location = find_git_location(start)
    if location is None or not has_install_marker(location.top_level):
        return None
    return location


BOUNDARY_REPOSITORY_ROOT = "repository-root"
BOUNDARY_ORDINARY_DESCENDANT = "ordinary-descendant"
BOUNDARY_LINKED_WORKTREE = "linked-worktree"
BOUNDARY_NESTED_REPOSITORY = "nested-repository"
BOUNDARY_SUBMODULE = "submodule"
BOUNDARY_NON_GIT = "non-git"
BOUNDARY_EXTERNAL_SYMLINK = "external-symlink"
BOUNDARY_AMBIGUOUS_MULTI_ROOT = "ambiguous-multi-root"
_MAX_ROOTS = 16


def posix_abs_path(path: str | None) -> str | None:
    """Absolute path with POSIX separators for JSON and matching text output."""
    if path is None:
        return None
    return os.path.normpath(path).replace("\\", "/")


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))


def is_ambiguous_workspace_roots(raw: object) -> bool:
    """True when ``workspace_roots`` names two or more distinct realpath roots."""
    if not isinstance(raw, list):
        return False
    seen: set[str] = set()
    for item in raw[:_MAX_ROOTS]:
        if not isinstance(item, str) or not item:
            continue
        try:
            real = os.path.normcase(safe_realpath(item))
        except (OSError, ValueError):
            return True
        seen.add(real)
        if len(seen) > 1:
            return True
    return False


def is_external_symlink_anchor(raw: str) -> bool:
    """True when a symlink component of ``raw`` escapes the Git root that contains the link."""
    try:
        current = raw if os.path.isabs(raw) else os.path.join(os.getcwd(), raw)
        current = os.path.abspath(current)
        for _ in range(_MAX_ROOTS * 4):
            if os.path.islink(current):
                parent = os.path.dirname(current)
                parent_loc = find_git_location(parent)
                if parent_loc is not None:
                    real = safe_realpath(current)
                    top = parent_loc.top_level
                    prefix = top if top.endswith(os.sep) else top + os.sep
                    real_n, top_n, prefix_n = (
                        os.path.normcase(real),
                        os.path.normcase(top),
                        os.path.normcase(prefix),
                    )
                    if real_n != top_n and not real_n.startswith(prefix_n):
                        return True
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    except OSError:
        return True
    return False


def _child_git_roots(start: str) -> list[str]:
    """Immediate child directories that have a ``.git`` entry (multi-root parent folder)."""
    found: list[str] = []
    try:
        with os.scandir(start) as entries:
            for entry in entries:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                if os.path.lexists(os.path.join(entry.path, ".git")):
                    found.append(entry.path)
                    if len(found) > 1:
                        return found
    except OSError:
        return []
    return found


def _gitfile_boundary(location: GitLocation) -> str:
    entry = os.path.join(location.top_level, ".git")
    try:
        is_file = os.path.isfile(entry) and not os.path.isdir(entry)
    except OSError:
        is_file = False
    if not is_file:
        return BOUNDARY_REPOSITORY_ROOT
    parts = location.git_dir.replace("\\", "/").split("/")
    if "worktrees" in parts:
        return BOUNDARY_LINKED_WORKTREE
    if "modules" in parts:
        return BOUNDARY_SUBMODULE
    if not _same_path(location.git_dir, location.common_dir):
        return BOUNDARY_LINKED_WORKTREE
    return BOUNDARY_SUBMODULE


def _enclosing_git(top_level: str) -> GitLocation | None:
    parent = os.path.dirname(top_level)
    if parent == top_level:
        return None
    outer = find_git_location(parent)
    if outer is None or _same_path(outer.top_level, top_level):
        return None
    return outer


class Resolution:
    """Read-only repository resolution for ``doctor`` and ``validate`` (ADR 0009).

    A plain class: this module stays stdlib-only for the hook import path.
    """

    __slots__ = (
        "boundary",
        "common_dir",
        "input_path",
        "marker_path",
        "marker_present",
        "marker_valid",
        "reason",
        "resolved_path",
        "status",
        "top_level",
    )

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        input_path: str,
        resolved_path: str,
        top_level: str | None,
        common_dir: str | None,
        marker_path: str | None,
        marker_present: bool,
        marker_valid: bool,
        boundary: str,
        status: str,
        reason: str,
    ) -> None:
        self.input_path = input_path
        self.resolved_path = resolved_path
        self.top_level = top_level
        self.common_dir = common_dir
        self.marker_path = marker_path
        self.marker_present = marker_present
        self.marker_valid = marker_valid
        self.boundary = boundary
        self.status = status
        self.reason = reason

    def as_dict(self) -> dict[str, object]:
        """JSON-ready facts. Text output must render this same mapping."""
        return {
            "input_path": posix_abs_path(self.input_path),
            "resolved_path": posix_abs_path(self.resolved_path),
            "repository_root": posix_abs_path(self.top_level),
            "common_dir": posix_abs_path(self.common_dir),
            "marker_path": posix_abs_path(self.marker_path),
            "marker_present": self.marker_present,
            "marker_valid": self.marker_valid,
            "boundary": self.boundary,
            "status": self.status,
            "reason": self.reason,
        }


def _marker_fields(top_level: str | None) -> tuple[str | None, bool, bool]:
    if not top_level:
        return None, False, False
    marker = os.path.join(top_level, INSTALL_MARKER_DIR, INSTALL_MARKER_NAME)
    try:
        present = os.path.lexists(marker)
    except OSError:
        present = False
    return marker, present, has_install_marker(top_level)


def _fail(  # noqa: PLR0913, PLR0917
    input_path: str,
    resolved_path: str,
    boundary: str,
    reason: str,
    top_level: str | None = None,
    common_dir: str | None = None,
) -> Resolution:
    marker_path, present, valid = _marker_fields(top_level)
    return Resolution(
        input_path,
        resolved_path,
        top_level,
        common_dir,
        marker_path,
        present,
        valid,
        boundary,
        "fail",
        reason,
    )


def _ok(
    input_path: str,
    resolved_path: str,
    location: GitLocation,
    boundary: str,
    reason: str,
) -> Resolution:
    marker_path, present, valid = _marker_fields(location.top_level)
    return Resolution(
        input_path,
        resolved_path,
        location.top_level,
        location.common_dir,
        marker_path,
        present,
        valid,
        boundary,
        "ok",
        reason,
    )


def inspect_repository(  # noqa: PLR0911
    start: str, workspace_roots: object = None
) -> Resolution:
    """Classify ``start`` using the Task 16 file-walk. Creates nothing. Never raises."""
    input_path = start
    try:
        abs_input = start if os.path.isabs(start) else os.path.abspath(start)
    except OSError:
        abs_input = start
    try:
        resolved = safe_realpath(abs_input)
    except (OSError, ValueError):
        resolved = abs_input
    if is_ambiguous_workspace_roots(workspace_roots):
        return _fail(
            input_path,
            resolved,
            BOUNDARY_AMBIGUOUS_MULTI_ROOT,
            "ambiguous multi-root workspace",
        )
    if is_external_symlink_anchor(abs_input):
        return _fail(
            input_path,
            resolved,
            BOUNDARY_EXTERNAL_SYMLINK,
            "path is an external symlink that leaves the containing repository",
        )
    location = find_git_location(resolved if os.path.isabs(resolved) else abs_input)
    if location is None:
        if len(_child_git_roots(resolved)) > 1:
            return _fail(
                input_path,
                resolved,
                BOUNDARY_AMBIGUOUS_MULTI_ROOT,
                "ambiguous multi-root workspace",
            )
        return _fail(
            input_path,
            resolved,
            BOUNDARY_NON_GIT,
            "not inside a Git working tree",
        )
    kind = _gitfile_boundary(location)
    nested = _enclosing_git(location.top_level) is not None
    at_root = _same_path(resolved, location.top_level)
    marker_valid = has_install_marker(location.top_level)
    if kind == BOUNDARY_LINKED_WORKTREE:
        if at_root:
            return _ok(
                input_path,
                resolved,
                location,
                BOUNDARY_LINKED_WORKTREE,
                "linked worktree root; runtime stays at the git common directory",
            )
        return _ok(
            input_path,
            resolved,
            location,
            BOUNDARY_ORDINARY_DESCENDANT,
            "ordinary descendant of a linked worktree",
        )
    if kind == BOUNDARY_SUBMODULE:
        return _ok(
            input_path,
            resolved,
            location,
            BOUNDARY_SUBMODULE,
            "submodule or gitfile boundary; outer repository is not used",
        )
    if nested:
        reason = (
            "uninitialized inner repository; will not fall back to an outer repository"
            if not marker_valid
            else "nested repository; inner root is the boundary"
        )
        return _ok(
            input_path,
            resolved,
            location,
            BOUNDARY_NESTED_REPOSITORY if at_root else BOUNDARY_ORDINARY_DESCENDANT,
            reason,
        )
    if at_root:
        return _ok(
            input_path,
            resolved,
            location,
            BOUNDARY_REPOSITORY_ROOT,
            (
                "detected repository root"
                if marker_valid
                else "detected repository root; CursorFleet marker is absent"
            ),
        )
    return _ok(
        input_path,
        resolved,
        location,
        BOUNDARY_ORDINARY_DESCENDANT,
        (
            "ordinary descendant of an initialized enclosing repository"
            if marker_valid
            else "ordinary descendant of the detected repository; CursorFleet marker is absent"
        ),
    )


def untrusted_reason(root: str) -> str | None:  # noqa: PLR0911
    """Why ``root`` (the runtime directory) must not be written to, or ``None`` if it is fine.

    A missing directory is fine (it will be created 0700 by us). An existing one must be a
    real directory (no symlink or Windows junction) owned by the current user and, on POSIX,
    not writable by group or others. Otherwise another account could have pre-planted
    symlinks or forged spool files in a shared ``.git`` directory (security review SR-02).
    One ``lstat``; hot-path safe.
    """
    try:
        info = os.lstat(root)
    except FileNotFoundError:
        return None
    except OSError:
        return "cannot be inspected"
    if stat.S_ISLNK(info.st_mode):
        return "is a symbolic link"
    if not stat.S_ISDIR(info.st_mode):
        return "is not a directory"
    if getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT:
        return "is a reparse point (junction)"
    if os.name == "posix":
        if info.st_uid != os.geteuid():
            return "is owned by another user"
        if info.st_mode & 0o022:
            return "is writable by group or others"
    return None


def mkdir_private(path: str | os.PathLike[str]) -> None:
    """Create ``path`` (and missing parents) with mode 0700 regardless of umask.

    Existing directories are left untouched (``doctor`` reports wrong modes). On
    Windows the mode is a no-op; user-only ACLs are best effort and not set here.
    """
    target = os.fspath(path)
    missing: list[str] = []
    current = target
    while current and not os.path.isdir(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    for directory in reversed(missing):
        try:
            os.mkdir(directory, DIR_MODE)
        except FileExistsError:
            continue
        if os.name == "posix":
            os.chmod(directory, DIR_MODE)


def write_private_file(path: str | os.PathLike[str], data: bytes, *, exclusive: bool) -> bool:
    """Write ``data`` to a new 0600 file. With ``exclusive`` never overwrite; return created."""
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    try:
        fd = os.open(os.fspath(path), flags, FILE_MODE)
    except FileExistsError:
        return False
    try:
        if os.name == "posix":
            os.fchmod(fd, FILE_MODE)
        os.write(fd, data)
    finally:
        os.close(fd)
    return True


def ensure_runtime_root(paths: RuntimePaths) -> None:
    """Create the runtime root and write ``LAYOUT`` once."""
    if not os.path.isdir(paths.root):
        mkdir_private(paths.root)
        write_private_file(paths.layout, (LAYOUT_VERSION + "\n").encode("ascii"), exclusive=True)
