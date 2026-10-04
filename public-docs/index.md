---
title: CursorFleet
description: >-
  Passive Cursor hooks + local TUI to observe agent teams. Observe-only,
  pre-alpha, unofficial.
image: assets/og-card.png
---

# CursorFleet

A local **task-centric observer** for Cursor agent teams: see who did what, where
work happened, and what was declared— from passive hooks and read-only git, without
sending anything anywhere.

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
- **Product hooks** were exercised on **Linux Cursor IDE 3.22.7** (maintainer smoke):
  hook telemetry, subagent lifecycle, and work artifacts were observed. Details:
  [live validation index](https://github.com/M9nx/cursorfleet/blob/main/docs/evidence/live-validation-index.md)
  (in-repo).
- **Q1** and **Q2** (subagent identity on tool hooks; custom subagent names) remain
  **OPEN**. Parallel classification is **BLOCKED/OPEN** on the exercised Linux surface.
- **M2.5** ships an **Active Run** default dashboard; the session archive remains on **o**.
  See [TUI current status](tui/current-status.md).
- **CI** runs on GitHub Actions; **documentation** is published via GitHub Pages.
- Linux is the primary tested platform; macOS and Windows are CI-tested only.
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
| Dashboard | `cursorfleet tui` — observe-only; Active Run UX in development (M2.5) |
| Scope | One Git repository; runtime state under that repo's Git common directory |

## License

MIT. Source: [github.com/M9nx/cursorfleet](https://github.com/M9nx/cursorfleet).
