"""Cross-platform advisory lock for the single SQLite writer (``locks/indexer.lock``)."""

from __future__ import annotations

import os
import sys
from types import TracebackType

from cursorfleet.state.runtime import FILE_MODE, mkdir_private


class IndexerBusy(RuntimeError):
    """Another indexer holds the lock."""


class IndexerLock:
    """Non-blocking exclusive lock held for the lifetime of the object / ``with`` block."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._fd: int | None = None

    def acquire(self) -> bool:
        mkdir_private(os.path.dirname(self._path))
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(self._path, flags, FILE_MODE)
        try:
            if sys.platform == "win32":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            os.close(fd)

    def __enter__(self) -> IndexerLock:
        if not self.acquire():
            msg = "another cursorfleet indexer holds the lock"
            raise IndexerBusy(msg)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
