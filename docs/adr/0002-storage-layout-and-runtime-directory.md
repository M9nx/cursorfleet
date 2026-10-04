# ADR 0002: Storage layout and runtime directory

- Status: provisional (the git-common-dir design is KEPT; Q4 and Q5 still open)
- Date: 2026-10-04
- Deciders: project owner (M9nx)
- Evidence level: verified-from-docs for the git facts; assumption for Cursor worktree behavior
- Supersedes: none
- Superseded by: none
- Related ADRs: 0001 (Q4, Q5), 0003 (event ids, worktree attribution), 0009 (uninstall leaves runtime data; init refuses ordinary subdirectories), 0010 (replay from spool), 0012 (worktree ownership)
- Implementation status: Partly implemented. Implemented: git-common-dir layout, CRC-per-line spool, quarantine of a corrupt database, an indexer lock; the file-walk finds the nearest `.git` and treats an inner `.git`/gitfile/submodule as a new boundary; **runtime inheritance** (marker required before any runtime directory or event file; tool cwd else `CURSOR_PROJECT_DIR`; fail-open no-event cases; paths relative to the inherited root). The write-command repository-root check (exit 2, no writes) is implemented as required by the task 16 owner contract; `doctor`/`validate` still do not print the detected root (task 15 remainder). Divergent: segment fingerprint is CRC32 not BLAKE2s; `worktree_id` is a bare SHA-256 prefix not an HMAC; no lock for retention/purge; the lock cannot tell contention from an unsupported filesystem. Details in the amendments below and in ADR 0009. Live row 17b remains OPEN.
- Review trigger: Q4 or Q5 answered on any OS, or a reproduced torn or interleaved spool line, or a live row 17b result that refutes inheritance
- Release gate: Q4 and Q5 answered on every OS claimed; BLAKE2s fingerprints, HMAC worktree ids and the maintenance lock implemented, or the claims in this ADR weakened to match the code; runtime inheritance (marker required, fail-open no-event cases, no nested state) implemented or the claims weakened

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
- **Non-git workspaces and nested directories.** A directory with no enclosing Git
  working tree is unsupported in v0.1: hooks record nothing and exit open, `doctor`
  explains. A **non-Git directory nested inside an already initialized Git
  repository** inherits that enclosing repository for **runtime** event attribution
  (amendment 2026-10-04, runtime inheritance). Write commands (`init`, `uninstall`)
  require a Git **repository root**: exit 2, nothing changed, no `--allow-non-git`.
  An ordinary subdirectory is refused the same way (print the detected root; never
  silently modify the parent). A genuine nested repository and a linked-worktree
  root are valid roots for install. Full write-command rules are in
  [ADR 0009](0009-install-uninstall-ownership.md). The hook records only when the
  detected root already has `.cursorfleet/config.toml`. `init`/`uninstall` require
  a repository root (exit 2, no writes). Live Cursor behaviour for nested folders
  (row 17b) remains OPEN.
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
  from the spool; a corrupt database is quarantined (moved aside) and rebuilt, never
  deleted silently (see the amendment).
- **Permissions.** Directories `0700`, files `0600` set at creation (explicit
  chmod, not umask-dependent). Windows: user-only ACLs, best effort.
- **Retention.** Defaults 14 days or 50 MB per session; enforcement placement
  (hook stat check versus indexer) is decided in M2. See [privacy](../privacy.md).
- **Worktree identity.** Original decision: `worktree_id` is `wt-` plus the first 12 hex
  of a SHA-256 of the realpath of the worktree top level. **Replaced by an HMAC, see the
  amendment.** Worktrees are treated as external and ephemeral; their records outlive them
  until retention.
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

## Amendment 2026-10-04 (architecture-owner decisions)

The `<git-common-dir>/cursorfleet/` design is **kept**. These decisions are added. Each
states what the code does today; the divergences are tracked in
[`../follow-ups.md`](../follow-ups.md) and are not fixed by this documentation pass.

### Telemetry is best-effort

- Events may be dropped: a hook that cannot write (full disk, capped session, unreadable
  runtime directory, `MAX_PATH`, internal error) drops the event and still exits 0 with the
  fail-open reply. Hooks never block or fail the agent to protect telemetry.
- Therefore every status view can be **incomplete**. Absence of an event is not evidence
  that something did not happen. Docs, `status --json` notes and the TUI must say so; a
  count shown to the user is a lower bound.
- Implementation status: spool drops are counted only when the reader sees a damaged line;
  silently dropped events leave no trace. A `dropped` counter on the hot path is not
  implemented and is not required for v0.1.

### Corrupt data is quarantined, never deleted silently

- A corrupt, unreadable or wrong-version SQLite projection is **renamed aside** into
  `quarantine/` (`state.sqlite[-wal|-shm].<utc stamp>.<pid>`) and rebuilt from the spool.
  It is never deleted by recovery.
- Corrupt spool lines are skipped and counted by the reader; the file stays in place. If
  a whole spool file must be set aside it also goes to `quarantine/`.
- `quarantine/` is cleared only by an explicit `events purge --all`, which reports what it
  removed. `doctor` reports a non-empty `quarantine/`.
- Implementation status: **Divergent-from-code (minor).** `Projection.quarantine()` in
  `state/indexer.py` renames aside, but if `os.replace` fails it falls back to
  `os.remove`, which deletes silently. Also not implemented: `doctor` does not report a non-empty
  `quarantine/`. Follow-up: leave the file in place and report instead.

### Segment fingerprints use BLAKE2s

- The indexer identifies a spool segment (so a rotation rename is not re-read) by a
  fingerprint of its first complete line: `hashlib.blake2s(first_line, digest_size=16)`,
  lower-case hex (32 characters). The per-line CRC32 stays as torn-write and bit-rot
  detection only; it is not an identity or integrity-against-an-attacker mechanism.
- Reason: a same-user agent can write spool files (threat model TB2), and a 32-bit checksum
  as identity lets a crafted collision make the indexer reuse another segment's offset.
- Scope: segment fingerprints (and the artifact digest of ADR 0006). The other SHA-256 uses
  (install lockfile, replay digest, `fs_name_for`, `safe_id`) are unchanged; whether to unify
  them is a follow-up decision.
- Implementation status: **Divergent-from-code.** `state/spool_read.py:fingerprint_of`
  returns the CRC32 of the first line as 8 hex characters, and `files.fingerprint` in the
  SQLite schema holds that. Changing it changes `PRAGMA user_version` (the projection is
  rebuildable, so a version bump rebuilds it).

### Worktree identifiers are keyed (HMAC), not bare hashes

- `worktree_id = "wt-" + hex(HMAC-SHA256(key, b"cursorfleet/worktree/v1\0" + normcase(realpath)))[:16]`.
- `key` is a per-repository random 32-byte secret stored in the runtime directory
  (`hmac.key`, mode `0600`, created with `O_EXCL`; the same file command hashes use, with
  a different domain label). It never leaves the machine.
- Reason: a bare hash of a path is guessable for known paths and correlates across machines
  and shared diagnostics; a keyed id correlates only within one repository's runtime dir.
- If the key is missing or unreadable the hook omits `worktree_id` (unknown); it never
  falls back to a bare hash. `events purge --all` rotates the key, so old ids stop matching
  new ones; this is accepted and documented.
- Cost: one small file read per hook. Its latency must be re-measured by the spike (Q6).
- Implementation status: **Divergent-from-code.** `events/ids.py:worktree_id_for` is `wt-`
  plus the first 12 hex of an unkeyed SHA-256. Command hashes use `HMAC-SHA256(key,
  normalized argv)` truncated to 32 hex with no domain label (`hook_sanitize.py`).

### Locking

Hooks stay **lock-free and append-only**. Only two background roles lock.

- **Lock files:** `<runtime>/locks/indexer.lock` (the single SQLite writer) and
  `<runtime>/locks/maintenance.lock` (retention, purge, key rotation, rebuild from scratch,
  quarantine clearing). Created `0600` inside the `0700` runtime directory, never deleted
  while in use, never followed through a symlink.
- **Mechanism:** an OS advisory lock on byte 0 of the open file: `fcntl.flock(fd,
  LOCK_EX | LOCK_NB)` on POSIX and `msvcrt.locking(fd, LK_NBLCK, 1)` on Windows. The OS
  releases it when the process exits or crashes.
- **Stale-lock recovery:** none is needed for process death, which is why `O_EXCL`
  lock files (which need pid or age heuristics) are not used. The file may contain the
  holder's pid and start time for diagnostics only; liveness is never inferred from it.
- **Contention versus failure:** only the documented "would block" errors (`EWOULDBLOCK`,
  `EAGAIN`, `EACCES` on POSIX; a locking violation on Windows) mean "busy". Any other error
  (for example `ENOLCK` or `ENOTSUP` on a network or synced file system) means "locking
  unsupported": the command refuses to write and `doctor` reports it. There is no fallback
  lock in v0.1.
- **Timeouts:** the indexer tries once; if busy, the caller carries on read-only on the
  last good projection and says another indexer is running. Maintenance polls with a
  deadline (10 s, 100 ms steps, injected clock) and then exits with status 1; it never kills
  the holder.
- **Order:** maintenance takes `maintenance.lock` then `indexer.lock`; the indexer takes
  only `indexer.lock`. One fixed order, so no deadlock.
- **What is locked:** SQLite writes and the quarantine rename (indexer); deletion of spool
  segments, key rotation and projection rebuild (maintenance, which also holds the indexer
  lock). Readers (`status`, TUI) take no lock and rely on WAL.
- A hook may append while a purge runs and recreate a fresh file; this is accepted.
- Tests required: a multi-process contention test and a kill-the-holder test on each OS in CI.
- Implementation status: **Partly implemented.** `state/lock.py:IndexerLock` uses `flock`
  and `msvcrt.locking` on `locks/indexer.lock`, non-blocking and single try, which matches
  the indexer rules. Not implemented: `maintenance.lock`; any locking in
  `state/retention.py` or `cli/commands/events.py` (purge can race the indexer); the
  contention-versus-unsupported distinction (any `OSError` is treated as busy); the
  diagnostic pid content; `O_NOFOLLOW` when opening the lock file. Windows behaviour is
  unverified.

### Repository-root preconditions for write commands

`init` and `uninstall` require a Git repository root. The rules, messages and exit codes
are in [ADR 0009](0009-install-uninstall-ownership.md) (amendment of the same date). This
ADR's non-git rule is unchanged for hooks (record nothing, exit open) and is extended for
write commands:

- Non-git directory: `init`/`uninstall` exit **2**, write nothing. No `--allow-non-git`
  flag, environment variable or config key in v0.1.
- Ordinary subdirectory of a repository: exit 2, write nothing, print the detected
  repository root and tell the user to run there.
- Genuine nested repository: the nearest root wins; the outer repository is never
  consulted.
- Linked-worktree root: valid. Runtime data stays at `<git-common-dir>/cursorfleet/`.
- `doctor` and `validate` stay read-only and may resolve from a subdirectory; `doctor`
  outside Git exits 1 (a check failed).

Write-command preconditions: see ADR 0009. A directory with no enclosing Git working
tree still records nothing
(`tests/integration/test_hook_main.py::test_not_a_git_repo_records_nothing`). Nested
non-Git inheritance is the next amendment (implemented in code; live row 17b OPEN).

## Amendment 2026-10-04 (runtime inheritance for nested non-Git directories)

Owner decision. Implemented in code (follow-ups task 16). Live Cursor behaviour
(row 17b) remains OPEN and is not claimed verified. It does not change write-command
preconditions (those remain repository-root only; see
[ADR 0009](0009-install-uninstall-ownership.md)). It decides what a hook does when it
runs from a directory that is not itself a Git repository root.

**Decision.** A non-Git directory nested inside an already initialized Git repository
inherits that enclosing repository for **runtime** event attribution.

**Resolution (normative).**

1. Use the tool cwd when available, otherwise `CURSOR_PROJECT_DIR`.
2. Realpath-resolve that anchor.
3. Find the nearest Git root (the innermost `.git` directory or gitfile walking up from
   the resolved anchor).
4. Require the detected root to contain the CursorFleet installation/config marker
   (committed `.cursorfleet/` at that root).
5. Use that root's `git-common-dir` and repository identity.
6. Normalize stored paths relative to that root.
7. Never create nested config (`.cursorfleet/`) or runtime state
   (`<git-common-dir>/cursorfleet/`) under the nested directory, and never create a new
   installation. Inheritance is allowed only for an installation that already exists at
   the resolved root.

**Boundaries.**

- An inner `.git` directory or gitfile, including a submodule, is a new repository
  boundary. The inner root is the detected root; the outer repository is never consulted.
- Do not fall back from an uninitialized inner repository (a Git root whose `.cursorfleet/`
  marker is absent) to the outer repository.
- A missing CursorFleet marker at the detected root produces no event and fails open
  (exit 0, correct reply).
- External symlinks, ambiguous multi-root workspaces, and uninitialized roots produce no
  event and fail open.

**Init is unchanged.** `cursorfleet init` invoked from an ordinary subdirectory still
exits 2 and performs no writes ([ADR 0009](0009-install-uninstall-ownership.md)). Runtime
inheritance does not authorize a nested install.

**Implementation status of this amendment.** **Implemented in code** (follow-ups task 16;
`adapters/cursor/hook_main.py:_resolve_runtime_location` / `record`,
`state/runtime.py:has_install_marker` / `resolve_inherited_location`). Live row 17b
remains OPEN.

- Start selection: tool cwd (`payload.cwd` when that path lexists, else process cwd),
  otherwise `CURSOR_PROJECT_DIR`. `workspace_roots` is not a start; two or more distinct
  realpath roots are ambiguous and fail open.
- Nearest Git root: `find_git_location` walks up to the first `.git` and treats an inner
  `.git`/gitfile/submodule as a new boundary. Search does not continue outward.
- Marker: v0.1 marker is `<repo-root>/.cursorfleet/config.toml`, a regular file after
  realpath. Symlink/junction-to-elsewhere is refused. The marker is validated before any
  runtime directory or event file is created.
- Paths: `PathResolver` is given only the inherited root (`location.top_level`).
- Fail-open no-event: missing marker, uninitialized inner repository, external symlink,
  ambiguous multi-root, uninitialized root, and no enclosing Git. Exit 0 with the correct
  fail-open reply.

Empirical cases remain in [empirical-test-plan](../empirical-test-plan.md) row 17, case 17b.
Tests: `tests/integration/test_runtime_inheritance.py`.
