# ADR 0002: Storage layout and runtime directory

- Status: provisional
- Date: 2026-10-04
- Deciders: project owner (M9nx)
- Evidence level: verified-from-docs for the git facts; assumption for Cursor worktree behavior

## Context

Verified (git behavior, Cursor docs fetched 2026-10-04 per ADR 0001):

- Project hooks run from the project root, which in a worktree is the worktree root.
- `git rev-parse --git-common-dir` returns the same directory from the main
  checkout and every linked worktree, and it is never tracked.
- Cursor creates, discovers and deletes worktrees itself (default cap 25).
- Parallel subagents in one conversation run simultaneously.

Unverified (ADR 0001 section B):

- Q4: `workspace_roots` and hook cwd inside Cursor-managed worktrees; whether
  `.git` is a gitfile there; whether the common dir resolves identically.
- Q5: whether hook processes overlap and whether concurrent `O_APPEND` writes
  stay intact; whether Cursor serializes hooks.

## Decision

We will keep runtime state out of the working tree, in one directory shared by
all worktrees:

```
<git-common-dir>/cursorfleet/
  LAYOUT                       layout version, e.g. "1"
  hmac.key                     random 32 bytes, 0600, for command hashes
  spool/<session_id>/<writer>.jsonl
  index/state.sqlite[-wal|-shm]
  locks/indexer.lock
  quarantine/                  corrupt lines or files moved aside
```

- **Resolution.** The contract is `git rev-parse --git-common-dir`, made absolute
  and realpath-resolved. The hot path may use an equivalent file-based walk
  (`.git` directory, or gitfile `gitdir:` then `commondir`) to avoid spawning
  git; a contract test compares it with `git`. Other callers use git with an
  argv list and a timeout.
- **Non-git workspaces:** unsupported in v0.1; hooks record nothing and exit
  open, `doctor` explains.
- **Committed config** lives in `.cursorfleet/` (`config.toml`, `roster.toml`,
  `work/<task>/`) and is per checkout. No runtime state under `.cursorfleet/`.
- **Spool.** One directory per session; one file per writer, where writer is
  `main` or the subagent instance id when known. Each line is
  `<crc32 hex8> <space> <event json>\n`, at most 8 KiB, written with a single
  `O_APPEND` write. Readers skip lines with a missing newline, bad CRC or
  unknown `schema_version`, and count them. Session ids are used as directory
  names only if they match the SafeId pattern; otherwise a hash is used.
- **Single writer.** Hooks only append JSONL. The indexer is the only SQLite
  writer (WAL), guarded by `locks/indexer.lock`. The projection is rebuildable
  from the spool; a corrupt database is deleted and rebuilt.
- **Permissions.** Directories `0700`, files `0600` set at creation (explicit
  chmod, not umask-dependent). Windows: user-only ACLs, best effort.
- **Retention.** Defaults 14 days or 50 MB per session; enforcement placement
  (hook stat check versus indexer) is decided in M2. See [privacy](../privacy.md).
- **Worktree identity.** `worktree_id` is `wt-` plus the first 12 hex of a
  SHA-256 of the realpath of the worktree top level. Worktrees are treated as
  external and ephemeral; their records outlive them until retention.
- **Git collector output** is projection state, not spool events.

PROVISIONAL until the spike answers Q4 and Q5: the common-dir location, the
one-file-per-writer split (collapses to one file per session if tool hooks carry
no subagent identity), and the claim that appends stay intact.

## Consequences

- Positive: one TUI sees every worktree; nothing to gitignore; hooks never touch SQLite.
- Negative / costs: depends on resolving the common dir correctly in every
  Cursor surface; per-line CRC and torn-tail handling add code; Windows append
  atomicity is weaker.
- Follow-ups: answer Q4/Q5 and update this ADR (or supersede); decide
  retention enforcement point in M2.

## Open questions

- Q4: does the common dir resolve identically from Cursor-managed worktrees?
- Q5: are concurrent small appends intact on Linux, macOS and Windows?
- Do synced or network-mounted repos break the 0700 assumption? `doctor` should warn.

## Alternatives considered

- `.cursorfleet/runtime/` in the working tree: splits state per worktree and
  risks commits. Rejected.
- Per-user state dir (platformdirs): shares across unrelated repos, needs
  non-stdlib code on the hot path, loses locality to the repo. Rejected for v0.1.
- Single shared spool file: simplest, but interleaving and torn-line risk
  with parallel subagents. Rejected pending Q5.
- SQLite written directly by hooks: slow startup, lock contention. Rejected.

## Addendum (M2, implemented)

- **Retention enforcement point (decided).** Hot path: rotate at 4 MiB; stop appending
  once a session directory reaches its cap and leave a `.capped` marker (a `stat` of one
  directory only when a file is created or rotated, never per event). Indexer and
  `events purge`: delete the oldest segments over the cap, drop sessions older than
  `max_age_days`, clear markers.
- **File naming.** `fs_name_for` keeps lower-case portable ids and replaces everything
  else (upper case, `:`, Windows device names, trailing dots, over-long, a leading `h-`)
  with `h-` plus 24 hex of SHA-256. Lower-case-only keeps names unique on case-insensitive
  filesystems. Readers reject an event whose `session_id` does not map to its directory
  (`misplaced`), so a forged file cannot inject another session.
- **Projection.** `index/state.sqlite` (WAL, `PRAGMA user_version=1`) holds `meta`,
  `files(session_dir, fingerprint, path, offset, corruption)`, `sessions` (reducer state
  as JSON plus the `(ts, event_id)` watermark) and `seen(session_id, event_id)`. Offsets
  are keyed by the CRC of a file's first line, so a rotation rename is not re-read. An
  event that sorts at or before a session's watermark makes the indexer rebuild that
  session from the spool, so incremental indexing always equals a full replay. A corrupt
  or wrong-version database is moved to `quarantine/` and rebuilt.
- **Rotation names** never clobber an earlier rotation (a `-n` suffix is added on collision).
- **Resolution contract test.** `tests/integration/test_runtime_resolution.py` compares the
  hot-path walk with `git rev-parse` for the main checkout, subdirectories, linked worktrees,
  submodules and symlinks. Relative or empty starting points resolve to nothing.
- **Still PROVISIONAL:** Q5 (atomic small appends on every OS). Tested here with real
  multi-process writers on Linux only; the reader tolerates tears regardless.
