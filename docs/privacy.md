# Privacy

CursorFleet is local only. It makes **no network calls** and sends no telemetry;
a test asserts the hook path imports no network libraries.

## What is stored

Per event (see [ADR 0003](adr/0003-event-model-and-sanitization.md) and `schemas/event.schema.json`):

- Ids and timestamps: `event_id`, `ts`, `session_id` (Cursor conversation id),
  `generation_id`, `agent_role`, `agent_instance_id`, `agent_id`, `worktree_id`.
- Provenance: `producer`, `producer_version`, `cursor_version`, `source`,
  `attribution`, `schema_version`.
- Classification: `kind`, `risk`, `outcome`, `status`, `tool_name`, gate name and state.
- Commands: argv0 (basename), subcommand, exit code, duration, a redacted and
  truncated display string (at most 200 characters, optional), and a keyed hash.
- Paths: workspace-relative, symlink-resolved; anything outside the workspace
  roots is stored as `<external>`.
- Git context: branch name, commit SHA, optional `issue_ref`.
- Bounded counters: durations, tool-call and message counts, and the context
  usage numbers `preCompact` exposes.

## What is never stored

- Prompts, thinking text, assistant responses, task or summary text.
- File contents, edit diffs (`old`/`new` strings), attachments.
- Command output, raw command lines, tool inputs and outputs, error messages.
- Environment variables.
- User emails (`user_email`, `CURSOR_USER_EMAIL`).
- Transcript paths (`transcript_path`, `agent_transcript_path`); we never open
  transcript files.
- Absolute paths and anything outside the workspace (replaced by `<external>`).

Mechanism: the four content hooks are never registered
([ADR 0004](adr/0004-no-chain-of-thought-and-hook-policy.md)); the remaining
payloads pass an allowlist parser that drops everything else before a write.

Agent-written Markdown under `.cursorfleet/work/` is the user's own content. Only
its path and frontmatter facts are indexed; the body is never copied into events.

Exceptions to be aware of: the hook process receives sensitive fields in memory
before dropping them, and command display strings are redacted on a best-effort basis
([threat model](threat-model.md)).

## Retention

- Defaults: **14 days** or **50 MB per session**, whichever comes first
  (`[retention]` in `.cursorfleet/config.toml`: `max_age_days`, `max_session_mb`).
- Enforced by the indexer and `cursorfleet events purge`; the hook stops
  appending to a session over its cap rather than rotating on the hot path.
- Hot path: a writer file rotates to `<writer>.<ms>-<pid>.jsonl` at 4 MiB. When a
  session directory reaches its cap (`CURSORFLEET_MAX_SESSION_MB` overrides
  `[retention] max_session_mb`) the hook writes a `.capped` marker and stops
  appending for that session. `events purge` (no selector) deletes the oldest
  segments over the cap and clears the marker, and removes sessions whose newest
  segment is older than `max_age_days`.
- The SQLite projection is rebuildable and is pruned together with the spool.
- `cursorfleet events export --sanitized` re-validates every event with the Event model
  and skips (and counts) corrupt lines; there is no raw export.

## Purge command contract

`cursorfleet events purge [--older-than <duration>] [--session <id>] [--all] [--dry-run] [--yes]`

- With no selector it applies the configured retention.
- `--older-than` accepts a duration such as `7d`; `--session` removes one session;
  `--all` removes every spool file and the projection, and also rotates the local
  hashing key (so old command hashes no longer correlate).
- Prints counts of sessions, files and bytes removed. `--dry-run` prints them
  and deletes nothing. Without `--yes` on a TTY it asks for confirmation.
- Exit codes: `0` success (including nothing to purge), `1` error, `2` usage error.
- Touches only `<git-common-dir>/cursorfleet/`. It never touches committed
  `.cursorfleet/` config, roster or work artifacts, or anything in `.cursor/`.
- Safe to run while Cursor is active; a concurrently appending hook may recreate
  a fresh file. Deletion is ordinary file removal, not secure wiping.

## Location and permissions

- Runtime data lives in `<git-common-dir>/cursorfleet/`, never in the working
  tree, so it is shared by all worktrees of a repo and cannot be committed by accident.
- POSIX: directories `0700`, files `0600`. Windows: user-only ACLs where
  possible (best effort; `doctor` reports what it could verify).
- Committed config (`.cursorfleet/config.toml`, `roster.toml`) must not contain
  secrets and is never read for secrets.

## Sharing diagnostics

Before pasting `status --json` or spool lines into an issue, check branch names,
paths and `issue_ref` values, which can be sensitive even though content is not stored.

## Verification

`tests/security/test_no_network.py` checks that no module imports a networking library, that
no CLI command, hook or TUI view opens a socket or resolves a name, and that the git collector
only runs local read-only subcommands. Planted secrets, command output and edit contents are
checked absent from the spool by the security tests and by `scripts/demo.py`. See
[security-review-v0.1.md](security-review-v0.1.md) for the full review and its limits.
