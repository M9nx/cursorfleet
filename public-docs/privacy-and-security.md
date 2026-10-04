# Privacy and security

CursorFleet is **unofficial**. It is not affiliated with or endorsed by
Anysphere or Cursor.

It is **local only**: no network calls, no telemetry, no accounts. A test
asserts that the hook path imports no networking libraries and that CLI,
hook, and TUI code do not open a socket or resolve a name.

It is **not a security boundary**. v0.1 observes; it blocks nothing. Hooks
fail open by design. Agents run as the same OS user. A malicious or
prompt-injected agent can bypass, disable, or forge anything CursorFleet
shows. Treat the dashboard as best-effort telemetry, not evidence of safety.

## What is never stored

- Prompts, thinking text, assistant responses, task or summary text.
- File contents, edit diffs, attachments.
- Command output, raw command lines, tool inputs and outputs, error messages.
- Environment variables.
- User emails.
- Transcript paths. Transcript files are never opened.
- Absolute paths and anything outside the workspace (stored as `<external>`).

The hooks that would receive prompts, thinking, responses, or file contents
are never registered. Remaining payloads pass an allowlist parser that drops
everything else before a write.

The hook process still **receives** some sensitive fields in memory before
dropping them. A bug or crash dump in that process could expose them.

## What is stored

Per event: ids and timestamps, session and generation ids, agent role and
instance when known, provenance (`source`, `attribution`), classification
(kind, risk, outcome, tool name), Git branch and commit, workspace-relative
paths, and bounded counters (durations, tool-call counts, `preCompact`
context usage).

Commands are reduced to executable basename, an optional subcommand, exit
code, duration, a keyed hash, and an optional redacted display string (at
most 200 characters). Redaction is best effort. The intended default is to
store no display string; until that default is flipped, set
`privacy.store_command_display = false` in `.cursorfleet/config.toml`.

Agent-written Markdown under `.cursorfleet/work/` is your content. Only its
path and frontmatter facts are indexed; the body is never copied into
events.

## Where it lives

Runtime data is under `<git-common-dir>/cursorfleet/`, never in the working
tree, so it is shared by all worktrees and is not committed by accident.
POSIX directories are `0700`, files `0600`. Windows user-only ACLs are best
effort.

Committed config (`.cursorfleet/config.toml`, `roster.toml`) must not contain
secrets.

Defaults: **14 days** or **50 MB per session**, whichever comes first.
`cursorfleet events purge` applies retention. Deletion is ordinary file
removal, not secure wiping. Purge never touches committed config, roster,
work artifacts, or `.cursor/`.

## What this does not protect

- Same-user forgery of the spool or projection. There are no signatures in
  v0.1.
- Other hooks (user, team, enterprise, third-party) that run beside ours and
  see the same payloads.
- Paths, branch names, and `issue_ref` values, which can themselves be
  sensitive.
- Gate tiles, which are heuristic and non-authoritative.
- Agent identity, which may be absent or inferred (Q1 OPEN).

Cloud agents are out of scope: their hooks never reach the local spool.

Before sharing `status --json` or diagnostics, review branch names, paths,
and issue refs.
