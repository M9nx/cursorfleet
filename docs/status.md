# Project status

Last updated: 2026-10-05. CursorFleet is unofficial and pre-alpha; nothing is published on PyPI.
Everything here was written and reviewed by the same author: it is a self-review, not an
independent audit.

## M2.5 active (replaces M0 process freeze for product direction)

The **M0a capture kit** ([`spike/README.md`](../spike/README.md)) and **CursorFleet product hooks**
are separate tracks; see [`evidence/live-validation-index.md`](evidence/live-validation-index.md).

**M2.5 goal:** task-centric local observer (Active Run) without exposing conversation content.

- **Allowed now:** documentation, ADRs, evidence indexes, contract decision matrix (A2),
  contract convergence with spool compatibility (A3), run-association spike (B0), in-memory
  Active Run prototype (B1), and milestones that depend on their gates.
- **Implemented (provisional):** run metadata under `<git-common-dir>/cursorfleet/runs/`,
  `cursorfleet run` CLI, Active run default TUI, hook env attach. **Still OPEN:** TUI attach
  picker, external alpha (M2.5-I), PyPI alpha.1 (ADR 0005 naming gate).
- **Still observe-only:** no enforcement, no agent spawning, no cloud-agent visibility.

M0a formal questions **Q1 and Q2 remain OPEN**; parallel row-8 classification is **BLOCKED/OPEN**
on Cursor 3.22.7 Linux. That does not negate the product-hook smoke on Linux IDE documented in
the evidence index.

## State of the code

- M0 (foundations, spike kit): done. M0a kit self-tested with synthetic payloads; formal matrix
  rows mostly OPEN.
- M1 (kit): **implemented**; exercised live via `init --cursor` on a test repo.
- M2 (hook, spool, indexer, reducer, git, `status --json`): **implemented**; **live hook
  telemetry confirmed** on Linux Cursor IDE 3.22.7 (maintainer smoke); not all ADR matrix rows PASS.
- M3 (Textual TUI): **implemented**; live data observed; **product usefulness limited**
  (session-centric default, stale noise, duplicate role cards). Gate tiles still derive heuristic
  PASS/FAIL until A3/E ([`tui.md`](tui.md), ADR 0011).
- M4 (CI, docs, release prep): CI **green** on GitHub Actions for `main`; GitHub Pages docs site
  deployed. No PyPI package, tag, or GitHub release yet.

Latency: Linux steady-state hook process time outside Cursor is recorded ([`hook-latency.md`](hook-latency.md)).
End-to-end latency **inside Cursor** (ADR 0001 section D) is not measured.

## Supported surface for v0.1

- **Local Cursor IDE (desktop) on Linux:** maintainer smoke with product hooks (partial matrix
  evidence only — see evidence index).
- **Not claimed until matrix PASS:** Cursor CLI, Agents Window, worktrees as a tested path,
  parallel subagents, cloud agents. See [`platform-support.md`](platform-support.md) and
  [ADR 0001](adr/0001-cursor-capabilities.md).

## Where the code and the decisions disagree

Listed in [`follow-ups.md`](follow-ups.md). A2 will produce an evidence-backed decision matrix;
A3 implements outcomes without losing spool replay. New M2/TUI **product** work proceeds under M2.5
charter subject to B0/B1 gates for run persistence.

## Gates before v0.1.0

Per [ADR index](adr/README.md) and [`release-checklist.md`](release-checklist.md). Naming (ADR 0005)
before PyPI. External alpha (M2.5-I) before Product Hunt. The public docs site is published via
GitHub Pages; Zensical source lives under [`public-docs/`](../public-docs/).
