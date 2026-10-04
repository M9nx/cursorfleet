"""Locate external programs (``git``, ``cursor``) without trusting the current directory.

``shutil.which`` and ``CreateProcess`` search the current directory first on Windows, and
a ``PATH`` with an empty or ``.`` entry does the same on POSIX. CursorFleet is routinely run
inside repositories it does not control, so a repository that ships ``git.exe`` or
``cursor.cmd`` could otherwise get it executed (security review SR-05). :func:`find_executable`
searches only absolute ``PATH`` entries that are not the current directory, and returns an
absolute path, which callers then pass as ``argv[0]``.
"""

from __future__ import annotations

import os
from functools import lru_cache


def _search_dirs(path_env: str, cwd: str | None) -> list[str]:
    real_cwd = os.path.normcase(os.path.realpath(cwd)) if cwd else None
    found: list[str] = []
    for entry in path_env.split(os.pathsep):
        entry = entry.strip().strip('"')  # noqa: PLW2901 - normalising the loop value
        if not entry or entry == os.curdir or not os.path.isabs(entry):
            continue
        if os.path.normcase(os.path.realpath(entry)) == real_cwd:
            continue
        found.append(entry)
    return found


def _candidate_names(name: str, pathext: str) -> list[str]:
    if os.name != "nt":
        return [name]
    suffixes = [s for s in pathext.split(os.pathsep) if s] or [".EXE", ".CMD", ".BAT", ".COM"]
    if os.path.splitext(name)[1].upper() in {s.upper() for s in suffixes}:
        return [name]
    return [name + s for s in suffixes]


@lru_cache(maxsize=32)
def _lookup(name: str, path_value: str, pathext_value: str, cwd: str | None) -> str | None:
    for directory in _search_dirs(path_value, cwd):
        for candidate in _candidate_names(name, pathext_value):
            full = os.path.join(directory, candidate)
            if os.path.isfile(full) and os.access(full, os.X_OK):
                return full
    return None


def find_executable(
    name: str,
    *,
    path_env: str | None = None,
    pathext: str | None = None,
    cwd: str | None = None,
) -> str | None:
    """Return the absolute path of ``name`` on ``PATH`` or ``None``. Never searches ``cwd``."""
    if os.path.basename(name) != name:
        return None  # only bare program names are looked up
    path_value = os.environ.get("PATH", "") if path_env is None else path_env
    pathext_value = os.environ.get("PATHEXT", "") if pathext is None else pathext
    if cwd is None:
        try:
            cwd = os.getcwd()
        except OSError:  # the directory was deleted under us: nothing to exclude
            cwd = None
    found = _lookup(name, path_value, pathext_value, cwd)
    if found is not None and not os.path.isfile(found):
        _lookup.cache_clear()  # the cached program vanished: search again
        return _lookup(name, path_value, pathext_value, cwd)
    return found
