# Project status

Last updated: 2026-10-12. CursorFleet is unofficial and pre-release; nothing is published on PyPI yet.
Everything here was written and reviewed by the same author: it is a self-review, not an
independent audit.

## v0.1.0 release pass (in progress)

Tracking: [`evidence/v01-release-baseline.md`](evidence/v01-release-baseline.md),
[`evidence/v01-adr-truth-table.md`](evidence/v01-adr-truth-table.md).

**Baseline SHA:** `31c8c2f` (plus v0.1.0 prep commits on `main`).

**Phase 7 decision (2026-10-12):** External alpha (M2.5-I) and Product Hunt are **not**
blocking the first `v0.1.0` tag; they continue immediately after PyPI publish. Maintainer
dogfood is documented in [`evidence/dogfood-week.md`](evidence/dogfood-week.md).

## M2.5 (task-centric observe)

- **Implemented:** run metadata, `cursorfleet run`, Active run default TUI, hook env attach,
  observations without heuristic PASS/FAIL gates, sessions archive on `o`.
- **OPEN:** TUI attach picker (v0.1.1); live B0 scenarios 3/5 full PASS on maintainer machine.
- **Still observe-only:** no enforcement, no agent spawning, no cloud-agent visibility.

## State of the code

- Hook/spool/indexer/TUI/status: implemented; Linux IDE smoke in evidence index.
- Run git context: scoped to linked sessions (2026-10-12).
- Privacy hot path: command display **off** without `[privacy]` config (2026-10-12).

## Supported surface for v0.1

- **Local Cursor IDE (desktop) on Linux:** maintainer smoke (partial matrix — see evidence index).
- **Not claimed until matrix PASS:** Cursor CLI, Agents Window, worktrees as a tested path,
  parallel subagents, cloud agents. See [`platform-support.md`](platform-support.md) and
  [ADR 0001](adr/0001-cursor-capabilities.md).

## Gates before v0.1.0 tag

Per [ADR index](adr/README.md), truth table, and [`release-checklist.md`](release-checklist.md).
**Owner-blocking:** ADR 0005 naming, SO-01 live permission-hook confirmation, latency row 13B
for each claimed OS/surface. See [`evidence/v01-release-ready.md`](evidence/v01-release-ready.md).
