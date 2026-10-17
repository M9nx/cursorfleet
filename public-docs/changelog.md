# Changelog

Released versions are public on [PyPI](https://pypi.org/project/cursorfleet/).
CursorFleet is unofficial: it is not affiliated with or endorsed by Anysphere
or Cursor.

This page is a public summary. It does not list internal follow-up tasks.

## 0.1.1 (2026-10-13)

- TUI: attach suggested sessions from the Active run screen (Enter).
- Optional `ghcr.io/m9nx/cursorfleet` container for GitHub Packages visibility.
- README and the docs site document PyPI install and released status; PyPI
  `project.urls` point at the docs site.

## 0.1.0 (2026-10-12)

**Observe-only:** no enforcement, no forced approvals, no cloud-agent
visibility. Hooks fail open. Not a security boundary.

- **Active run TUI** (default screen `a`): participant groups/instances, runs
  list (`u`), sessions archive (`o`).
- **`cursorfleet run`** start/list/attach/archive; run files under the git
  common directory.
- **`status --json` `runs[]`** when telemetry exists (`cursorfleet.status/0.2`).
- Twelve observe-only hooks: the narrower nine-hook policy plan plus
  `beforeShellExecution`, `afterShellExecution` and `afterFileEdit` for the
  observe set ([ADR 0007 amendment](https://github.com/M9nx/cursorfleet/blob/main/docs/adr/0007-narrower-v01-hook-policy.md)).
- Sanitized legacy spool fixture and doc-derived examples under
  `tests/fixtures/cursor/`.

Still true for v0.1.x: the maintainer's Linux IDE smoke is the only
exercised live surface (no independent audit); the Cursor CLI, Agents
Window, worktrees, and parallel subagents are unverified/not claimed;
macOS and Windows hook latency are unmeasured; Linux steady-state
latency outside Cursor is measured, and end-to-end inside-Cursor
latency is not; `cursorfleet emit` is not implemented.

## Unreleased

Development on `main` is `0.1.2.dev0`: release-truth and evidence closure
first (live B0 scenarios, SO-01 permission-hook rows, end-to-end latency row
13B), then the external-alpha tracks. See
[Known limitations](known-limitations.md).
