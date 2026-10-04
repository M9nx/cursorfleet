# Changelog

Nothing has been released. The version in the checkout is `0.0.1.dev0`.
CursorFleet is unofficial: it is not affiliated with or endorsed by Anysphere
or Cursor.

This page is a public summary. It does not list internal follow-up tasks.

## Unreleased

Pre-alpha. **Not verified against a live Cursor session.** v0.1 is *Observe*
only: no enforcement, no forced approvals, no cloud-agent visibility.

**Q1** (subagent identity inside tool hooks) and **Q2** (custom
`subagent_type` naming) remain **OPEN**. Parallel-identity classification is
**BLOCKED/OPEN** on tested Cursor 3.22.7 Linux.

### In the development checkout

- **Kit:** `cursorfleet init --cursor`, `uninstall`, `doctor`, and `validate`.
  Git is required for `init`; there is no `--allow-non-git`. The checkout
  currently registers twelve observe-only hooks; the accepted decision is nine.
- **Observer:** a stdlib-only, fail-open `cursorfleet-hook`, a local append-only
  spool, a SQLite projection, a read-only git/worktree collector, and
  `cursorfleet status --json` (`cursorfleet.status/1`).
- **Dashboard:** `cursorfleet tui` exists in the checkout and is **under
  development**. It is provisional and unvalidated against live Cursor. Gate
  tiles are heuristic and non-authoritative.
- **Release prep:** cross-platform CI (Linux, macOS, Windows; Python 3.11 to
  3.14) and an inactive PyPI/GitHub release workflow. No package, tag, or
  GitHub release has been published.

### Security (high level)

The hook path is fail-open and drops prompts, thinking, file contents, command
output, environment variables, emails, and transcript paths at the parser
boundary. The runtime directory is refused when it is a symlink, a reparse
point, owned by another user, or group/other-writable. Tools are resolved from
absolute `PATH` entries only, never the current directory.

### Not claimed

- No PyPI or TestPyPI package.
- Live Cursor behaviour (including the Cursor CLI, Agents Window, worktrees,
  and parallel subagents) is unverified.
- macOS and Windows hook latency are unmeasured; Linux has a process-wall
  steady-state number taken *outside* Cursor.
- `cursorfleet emit` is not implemented.

See [Known limitations](known-limitations.md).
