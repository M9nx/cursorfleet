# Live validation evidence index

Last updated: 2026-10-05. Self-review by the maintainer; not an independent audit.
Raw Cursor captures are **not** committed to this repository.

## What this index covers

Two different validation tracks must not be conflated:

| Track | Purpose | Status |
| --- | --- | --- |
| **M0a spike kit** (`spike/capture_hook.py`) | Answer ADR 0001 Q1–Q6 with sanitized captures | Kit self-tested; formal row-8 **BLOCKED/OPEN**; Q1/Q2 **OPEN** ([`spike/questions.md`](../spike/questions.md)) |
| **CursorFleet product hooks** (`cursorfleet-hook` after `init --cursor`) | End-to-end observer, TUI, artifacts | **Exercised** on Linux Cursor IDE (see below) |

## CursorFleet product hook smoke (maintainer)

| Field | Value |
| --- | --- |
| Cursor version | 3.22.7 (Linux desktop IDE) |
| Surface | Local Cursor IDE (desktop) |
| Repository | External test repo (Termchat1); multi-chat workflow |
| Hook telemetry | **Yes** — events indexed; `cursorfleet status` reported multiple sessions |
| Subagent lifecycle | **Observed** — at least one session showed subagents with `attribution=exact` across architect/implementer/tester/reviewer/QA-style roles |
| Artifacts | **Yes** — `.cursorfleet/work/<task>/` self-reported files scanned (e.g. smoke handoff task) |
| Git collector | Read-only; no fetch |
| Privacy | No prompts/responses in spool (by design); maintainer did not commit raw spool to git |
| Product gaps observed | Session-centric TUI noise with many separate chats; duplicate role cards (observed vs declared); stale `main` sessions dominate default overview |

**Verdict:** The **observer pipeline works** against live Cursor on Linux IDE for this smoke. That does **not** close M0a Q1/Q2 or parallel classification. It does **not** prove CLI, Agents Window, or worktree matrix rows.

## CI and documentation site

| Check | Evidence |
| --- | --- |
| GitHub Actions CI | Green on `main` (lint, format, mypy, cross-platform tests) as of 2026-10-04 |
| GitHub Pages | Public docs site deployed ([README](../README.md) badge) |

## Still OPEN or unverified

- **Q1 / Q2** ([ADR 0001](../adr/0001-cursor-capabilities.md)): identity on tool hooks; custom `subagent_type` naming
- **Parallel / background subagent classification**: BLOCKED/OPEN on Cursor 3.22.7 Linux ([`spike/README.md`](../../spike/README.md))
- **End-to-end hook latency inside Cursor** (ADR 0001 section D row 13B): not measured
- **Sanitized fixtures in repo**: pending A3 (`tests/fixtures/cursor/`)
- **PyPI / tags / releases**: none

## M2.5 charter (replaces M0 process freeze for product work)

M2.5 targets a **task-centric local observer** useful for daily Cursor work. Allowed: contract convergence (A2/A3), association spike (B0), in-memory Active Run prototype (B1), then persistence (B2+) per [rev. 2 plan](https://github.com/M9nx/cursorfleet) (internal).

**Shipped (M2.5 B2/D, provisional):** JSON run files, `cursorfleet run` CLI, Active run default TUI,
`CURSORFLEET_ACTIVE_RUN` hook attach. **Still blocked/OPEN:** SQLite run tables (not planned for alpha.1),
TUI attach picker, external alpha metrics.

Observe-only boundaries unchanged: passive hooks, read-only git, TUI read-only; future run metadata lives under `<git-common-dir>/cursorfleet/runs/` only (see product contract amendment).

## Private capture location

Maintainer raw JSONL spools and M0a captures stay **outside** this repository. Export sanitized excerpts only via A3 fixture work.
