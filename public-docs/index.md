# CursorFleet

A local TUI and workflow harness for Cursor agent teams: see which local
agents and worktrees are doing what, from passive hooks and read-only git,
without sending anything anywhere.

**Unofficial.** CursorFleet is not affiliated with or endorsed by Anysphere or
Cursor. "Cursor" is a trademark of its respective owner. The name
"CursorFleet" is a working name.

## Status

**Pre-alpha, not released.** There is no PyPI package, tag, or GitHub release.
Install from a git checkout. See [Installation](getting-started/installation.md).

- v0.1 is **Observe** only: no enforcement, no forced approvals, and no
  cloud-agent visibility (local Cursor sessions only). It is not a security
  boundary: a malicious or prompt-injected agent can bypass or forge what it
  shows.
- Hook payload shapes come from Cursor's documentation. The project has **not**
  been verified against a live Cursor as a completed spike. **Q1** (identity of
  the current subagent inside its tool hooks) and **Q2** (how custom subagent
  names appear in `subagent_type`) remain **OPEN**.
- Parallel-identity classification is **BLOCKED/OPEN** on the Cursor **3.22.7**
  Linux surface that has been exercised. Do not treat that single observation
  as a Q1 result.
- The Textual dashboard (`cursorfleet tui`) is **under development**: the
  command exists in the checkout, but it is provisional and unvalidated against
  live Cursor. New TUI work is frozen until the live spike is finished.
- **Supported surface (intended):** the local Cursor IDE (desktop) only, once
  the spike confirms it. The Cursor CLI, the Agents Window, Cursor-managed and
  manual worktrees, parallel subagents, and cloud agents are not claimed.
- Linux is the tested platform; macOS and Windows are CI-tested only.
- Cursor is the only officially supported IDE. Internals are adapter-ready; no
  other adapter is planned for v0.1.
- Local only: no network calls, no telemetry, no accounts. CursorFleet does not
  store prompts, model thinking, responses, file contents, command output,
  environment variables, emails, or transcript paths.

## Get started

1. [Install from a checkout](getting-started/installation.md)
2. [Quickstart](getting-started/quickstart.md) — `init`, `doctor`, `status`
3. [CLI](cli/init.md), [privacy](privacy-and-security.md), and
   [known limitations](known-limitations.md)

Git is required for `init`. There is no `--allow-non-git` flag.

## What you get in the checkout

| Area | What exists today |
| --- | --- |
| Kit | `cursorfleet init --cursor`, `uninstall`, `doctor`, `validate` |
| Observer | Fail-open `cursorfleet-hook`, local spool and projection, `status --json` |
| Dashboard | `cursorfleet tui` — under development, observe-only |
| Scope | One Git repository; runtime state under that repo's Git common directory |

## License

MIT. Source: [github.com/M9nx/cursorfleet](https://github.com/M9nx/cursorfleet).
