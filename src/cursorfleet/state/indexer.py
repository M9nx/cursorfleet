"""Single-writer SQLite WAL projection and incremental spool indexer.

- Hooks never touch SQLite. This module is the only writer, guarded by ``IndexerLock``.
- The database is a cache: it is rebuildable from the spool. A corrupt or
  wrong-version database is moved to ``quarantine/`` and rebuilt.
- Tailing: per spool file we keep a byte offset keyed by ``(session dir, fingerprint of
  the first line)``, so a size-rotation rename does not cause a re-read. Offsets only
  advance past complete lines; a torn tail is retried.
- Equivalence with replay: new events are applied incrementally only if they sort after
  the session watermark; otherwise that session is rebuilt from the spool. Either way the
  result equals ``reduce_events`` over the whole spool (property-tested).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field

from cursorfleet.events.ids import fs_name_for
from cursorfleet.events.models import Event
from cursorfleet.state.event_store import (
    EVENTS_DDL,
    delete_session_events,
    insert_events,
)
from cursorfleet.state.lock import IndexerBusy, IndexerLock
from cursorfleet.state.models import SessionAcc
from cursorfleet.state.reducer import apply_event, dedupe_and_sort, reduce_events, sort_key
from cursorfleet.state.runtime import FILE_MODE, RuntimePaths, mkdir_private, untrusted_reason
from cursorfleet.state.spool_read import (
    Corruption,
    accept_placement,
    list_spool_files,
    peek_fingerprint,
    read_all,
    read_file,
)

DB_SCHEMA_VERSION = 1

_DDL = (
    """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files (
    session_dir TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    path TEXT NOT NULL,
    offset INTEGER NOT NULL,
    corruption TEXT NOT NULL,
    PRIMARY KEY (session_dir, fingerprint)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    watermark_ts TEXT NOT NULL,
    watermark_id TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS seen (
    session_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    PRIMARY KEY (session_id, event_id)
) WITHOUT ROWID;
"""
    + EVENTS_DDL
)


@dataclass
class SyncStats:
    files_scanned: int = 0
    events_read: int = 0
    events_new: int = 0
    sessions_updated: int = 0
    sessions_rebuilt: int = 0
    sessions_pruned: int = 0
    db_recovered: bool = False
    corruption: Corruption = field(default_factory=Corruption)


def _json_to_corruption(text: str) -> Corruption:
    try:
        data = json.loads(text)
        return Corruption.from_dict({k: v for k, v in data.items() if isinstance(v, int)})
    except (ValueError, AttributeError, TypeError):
        return Corruption()


def _corruption_to_json(counts: Corruption) -> str:
    return json.dumps(counts.to_dict(), sort_keys=True)


class UntrustedRuntime(IndexerBusy):
    """The runtime directory is not private to this user (symlink, other owner, group-writable)."""


class Projection:
    """Thin wrapper around the SQLite file (open, validate, recover)."""

    def __init__(self, paths: RuntimePaths) -> None:
        self._paths = paths
        self.recovered = False

    def quarantine(self) -> None:
        mkdir_private(self._paths.quarantine)
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        for suffix in ("", "-wal", "-shm"):
            source = self._paths.db + suffix
            if os.path.exists(source):
                target = os.path.join(
                    self._paths.quarantine, f"state.sqlite{suffix}.{stamp}.{os.getpid()}"
                )
                try:
                    os.replace(source, target)
                except OSError:
                    with suppress(OSError):
                        os.remove(source)

    def _create_private(self) -> None:
        mkdir_private(self._paths.index_dir)
        if not os.path.exists(self._paths.db):
            fd = os.open(
                self._paths.db,
                os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0),
                FILE_MODE,
            )
            os.close(fd)
            if os.name == "posix":
                os.chmod(self._paths.db, FILE_MODE)

    def _open_checked(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._paths.db, timeout=10.0, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version not in (0, DB_SCHEMA_VERSION):
                msg = f"unsupported projection schema version {version}"
                raise sqlite3.DatabaseError(msg)
            conn.executescript(_DDL)
            conn.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
            conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
            return conn
        except BaseException:
            conn.close()
            raise

    def connect(self) -> sqlite3.Connection:
        self._create_private()
        try:
            return self._open_checked()
        except sqlite3.DatabaseError:
            self.quarantine()
            self.recovered = True
            self._create_private()
            return self._open_checked()

    def reset(self) -> None:
        """Delete the projection (used by ``rebuild``)."""
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._paths.db + suffix)
            except OSError:
                continue


class Indexer:
    """Tails the spool into the projection. Construct, then call :meth:`sync`."""

    def __init__(self, paths: RuntimePaths) -> None:
        self._paths = paths
        self._projection = Projection(paths)

    # ------------------------------------------------------------ public API

    def sync(self, *, rebuild: bool = False) -> SyncStats:
        """Index new spool lines. Raises :class:`IndexerBusy` if another indexer runs.

        Raises :class:`UntrustedRuntime` (an ``IndexerBusy``) when the runtime directory is
        not private to this user; nothing is read, created or written in that case.
        """
        reason = untrusted_reason(self._paths.root)
        if reason is not None:
            msg = f"the runtime directory {reason}; refusing to index (see `cursorfleet doctor`)"
            raise UntrustedRuntime(msg)
        with IndexerLock(self._paths.indexer_lock):
            if rebuild:
                self._projection.reset()
            conn = self._projection.connect()
            try:
                stats = SyncStats(db_recovered=self._projection.recovered or rebuild)
                try:
                    self._sync(conn, stats)
                except ValueError:
                    # A stored row that no longer validates (corrupt or planted database):
                    # the projection is only a cache, so quarantine it and rebuild once.
                    conn.close()
                    self._projection.quarantine()
                    conn = self._projection.connect()
                    stats = SyncStats(db_recovered=True)
                    self._sync(conn, stats)
                return stats
            finally:
                conn.close()

    def try_sync(self) -> SyncStats | None:
        """Like :meth:`sync` but returns ``None`` when another indexer is active."""
        try:
            return self.sync()
        except IndexerBusy:
            return None

    def load_sessions(self) -> dict[str, SessionAcc]:
        """Read the projection (no locking; WAL readers never block the writer)."""
        if not os.path.exists(self._paths.db) or untrusted_reason(self._paths.root) is not None:
            return {}
        try:
            conn = self._projection.connect()
        except (sqlite3.DatabaseError, OSError):
            return {}
        try:
            return {
                row[0]: SessionAcc.model_validate_json(row[1])
                for row in conn.execute("SELECT session_id, state FROM sessions ORDER BY 1")
            }
        except (sqlite3.DatabaseError, ValueError):
            return {}
        finally:
            conn.close()

    def corruption(self) -> Corruption:
        """Cumulative corruption counters across indexed files."""
        total = Corruption()
        if not os.path.exists(self._paths.db) or untrusted_reason(self._paths.root) is not None:
            return total
        try:
            conn = self._projection.connect()
        except (sqlite3.DatabaseError, OSError):
            return total
        try:
            for (text,) in conn.execute("SELECT corruption FROM files"):
                total.add(_json_to_corruption(text))
        except sqlite3.DatabaseError:
            pass
        finally:
            conn.close()
        return total

    # ------------------------------------------------------------ internals

    @contextmanager
    def _tx(self, conn: sqlite3.Connection) -> Iterator[None]:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")

    def _ensure_event_store(self, conn: sqlite3.Connection) -> None:
        """Projections written before the ``events`` table existed are re-indexed once."""
        if conn.execute("SELECT 1 FROM meta WHERE key='event_store'").fetchone() is not None:
            return
        with self._tx(conn):
            conn.execute("DELETE FROM files")
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM seen")
            conn.execute("DELETE FROM events")
            conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('event_store', '1')")

    def _sync(self, conn: sqlite3.Connection, stats: SyncStats) -> None:
        self._ensure_event_store(conn)
        batches: dict[str, list[Event]] = {}
        file_updates: list[tuple[str, str, str, int, str]] = []
        live_keys: set[tuple[str, str]] = set()
        files = list_spool_files(self._paths)
        for path in files:
            fingerprint = peek_fingerprint(path)
            if fingerprint is None:
                continue
            session_dir = os.path.basename(os.path.dirname(path))
            live_keys.add((session_dir, fingerprint))
            row = conn.execute(
                "SELECT offset, corruption FROM files WHERE session_dir=? AND fingerprint=?",
                (session_dir, fingerprint),
            ).fetchone()
            offset = int(row[0]) if row else 0
            previous = _json_to_corruption(row[1]) if row else Corruption()
            result = read_file(path, offset)
            accepted = [e for e in result.events if accept_placement(path, e, result.corruption)]
            stats.files_scanned += 1
            stats.events_read += len(accepted)
            if result.new_offset < offset or (offset > result.size):
                previous = Corruption()  # file was truncated/replaced: counters restart
            previous.add(result.corruption)
            stats.corruption.add(result.corruption)
            file_updates.append(
                (session_dir, fingerprint, path, result.new_offset, _corruption_to_json(previous))
            )
            for event in accepted:
                batches.setdefault(event.session_id, []).append(event)
        with self._tx(conn):
            for session_id in sorted(batches):
                self._index_session(conn, session_id, batches[session_id], stats)
            conn.executemany(
                "INSERT OR REPLACE INTO files(session_dir, fingerprint, path, offset, corruption)"
                " VALUES (?,?,?,?,?)",
                file_updates,
            )
            self._prune(conn, live_keys, stats)
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(DB_SCHEMA_VERSION),),
            )

    def _index_session(
        self, conn: sqlite3.Connection, session_id: str, events: list[Event], stats: SyncStats
    ) -> None:
        fresh = [
            e
            for e in dedupe_and_sort(events)
            if conn.execute(
                "SELECT 1 FROM seen WHERE session_id=? AND event_id=?", (session_id, e.event_id)
            ).fetchone()
            is None
        ]
        if not fresh:
            return
        stats.events_new += len(fresh)
        row = conn.execute(
            "SELECT state FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        acc = SessionAcc.model_validate_json(row[0]) if row else None
        out_of_order = acc is not None and sort_key(fresh[0]) <= (
            acc.watermark_ts,
            acc.watermark_id,
        )
        if out_of_order:
            self._rebuild_session(conn, session_id, stats)
            return
        for event in fresh:
            acc = apply_event(acc, event)
        assert acc is not None  # noqa: S101 - fresh is non-empty
        conn.executemany(
            "INSERT OR IGNORE INTO seen(session_id, event_id) VALUES (?,?)",
            [(session_id, e.event_id) for e in fresh],
        )
        insert_events(conn, fresh)
        self._store(conn, acc)
        stats.sessions_updated += 1

    def _rebuild_session(self, conn: sqlite3.Connection, session_id: str, stats: SyncStats) -> None:
        all_events, _corruption, _files = read_all(self._paths, session_id)
        # Include events from other session dirs that claim this id (dir name != id).
        rebuilt = reduce_events(all_events).get(session_id)
        conn.execute("DELETE FROM seen WHERE session_id=?", (session_id,))
        delete_session_events(conn, session_id)
        if rebuilt is None:
            conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
            return
        unique = dedupe_and_sort(all_events)
        conn.executemany(
            "INSERT OR IGNORE INTO seen(session_id, event_id) VALUES (?,?)",
            [(session_id, e.event_id) for e in unique],
        )
        insert_events(conn, [e for e in unique if e.session_id == session_id])
        self._store(conn, rebuilt)
        stats.sessions_rebuilt += 1

    @staticmethod
    def _store(conn: sqlite3.Connection, acc: SessionAcc) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO sessions(session_id, state, watermark_ts, watermark_id)"
            " VALUES (?,?,?,?)",
            (acc.session_id, acc.model_dump_json(), acc.watermark_ts.isoformat(), acc.watermark_id),
        )

    def _prune(
        self, conn: sqlite3.Connection, live_keys: set[tuple[str, str]], stats: SyncStats
    ) -> None:
        """Drop projection rows whose spool is gone (retention prunes spool and projection)."""
        for session_dir, fingerprint in conn.execute(
            "SELECT session_dir, fingerprint FROM files"
        ).fetchall():
            if (session_dir, fingerprint) not in live_keys:
                conn.execute(
                    "DELETE FROM files WHERE session_dir=? AND fingerprint=?",
                    (session_dir, fingerprint),
                )
        for (session_id,) in conn.execute("SELECT session_id FROM sessions").fetchall():
            directory = os.path.join(self._paths.spool, fs_name_for(session_id))
            if not os.path.isdir(directory):
                conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
                conn.execute("DELETE FROM seen WHERE session_id=?", (session_id,))
                delete_session_events(conn, session_id)
                stats.sessions_pruned += 1


def replay_session_state(
    paths: RuntimePaths, session_id: str | None = None
) -> tuple[dict[str, SessionAcc], Corruption, int]:
    """Pure replay straight from the spool (no SQLite). Used by ``replay`` and as fallback."""
    events, corruption, files = read_all(paths, session_id)
    return reduce_events(events), corruption, files


__all__ = [
    "DB_SCHEMA_VERSION",
    "Indexer",
    "IndexerBusy",
    "Projection",
    "SyncStats",
    "UntrustedRuntime",
    "replay_session_state",
]
