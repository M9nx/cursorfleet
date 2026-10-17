# Project status

Last updated: 2026-10-17. CursorFleet is unofficial; **v0.1.1** is tagged on GitHub and
published on PyPI (0.1.0 and 0.1.1, both 2026-10-12 UTC). GitHub Releases has no published
(non-draft) release; publishing one remains an owner decision. Everything here was written
and reviewed by the same author: it is a self-review, not an independent audit.

## v0.1.2 release preparation (in progress)

Tracking: [`evidence/v012-baseline.md`](evidence/v012-baseline.md) (scope, gate matrix,
required order) and the v0.1 truth table
[`evidence/v01-adr-truth-table.md`](evidence/v01-adr-truth-table.md).

- **Baseline SHA:** `8165a76c367efbc31fd02661f16c4363f93e1eb0`; working version `0.1.2.dev0`.
- **Next owner-controlled issue: V012-02** — live B0 scenarios 1/2/5, the SO-01
  permission-hook rows, and end-to-end latency row 13B on the maintainer's Linux Cursor
  IDE. The owner run kit is [`evidence/run-kit-v012-02.md`](evidence/run-kit-v012-02.md);
  synthetic fixtures and repository tests cannot close these gates.
- **Truth convergence (2026-10-17, repo side):** status page, B0 result rows (v0.1.1 attach
  picker noted, verdicts unchanged), evidence index, release-checklist header note,
  quickstart install/release claims, Pages site claims (index, known limitations, public
  changelog, TUI status), and ADR 0001 §C re-citing the committed 2026-10-04 latency
  re-run. Local verification: ruff/format clean, strict `mypy` clean, **pytest 1011
  passed, 1 deselected** (the earlier recorded skipped test came from another
  environment).
- Tag, PyPI publish, and GitHub Releases remain **NOT AUTHORIZED** until the v0.1.2 gates
  close (owner decision required).

## v0.1.1 (shipped)

Tagged 2026-10-13 and published to PyPI. Added the TUI attach picker (attach a suggested
session from the Active run screen with Enter), an optional GHCR container, and PyPI/docs
metadata refresh. Live-evidence debt (B0, SO-01, latency 13B) carried into v0.1.2 above.

## M2.5 (task-centric observe)

- **Implemented:** run metadata, `cursorfleet run`, Active run default TUI, hook env attach,
  observations without heuristic PASS/FAIL gates, sessions archive on `o`, TUI attach
  picker (v0.1.1).
- **OPEN:** live B0 full PASS for scenarios 1/2/5 on the maintainer machine
  ([`evidence/b0-live-validation-2026-10-12.md`](evidence/b0-live-validation-2026-10-12.md)).
- **Still observe-only:** no enforcement, no agent spawning, no cloud-agent visibility.

## State of the code

- Hook/spool/indexer/TUI/status: implemented; Linux IDE smoke in
  [`evidence/live-validation-index.md`](evidence/live-validation-index.md).
- Run git context: scoped to linked sessions (2026-10-12).
- Privacy hot path: command display **off** without `[privacy]` config (2026-10-12).
- Sanitized legacy spool fixture and doc-derived examples under `tests/fixtures/cursor/`;
  real-capture fixture work still follows the empirical-test-plan row 16 rules.

## Supported surface for v0.1

- **Local Cursor IDE (desktop) on Linux:** maintainer smoke (partial matrix — see the
  [evidence index](evidence/live-validation-index.md)).
- **Not claimed until matrix PASS:** Cursor CLI, Agents Window, worktrees as a tested path,
  parallel subagents, cloud agents. See [`platform-support.md`](platform-support.md) and
  [ADR 0001](adr/0001-cursor-capabilities.md).

## Owner-blocked evidence gates (carried into v0.1.2)

Per the v0.1.2 [gate matrix](evidence/v012-baseline.md): SO-01 live permission-hook
confirmation, latency row 13B for each claimed OS/surface, and B0 live scenarios 1/2/5.
Background: [`evidence/v01-release-ready.md`](evidence/v01-release-ready.md) and
[`release-checklist.md`](release-checklist.md). External-alpha results are `NOT STARTED`;
their recording starts only after the candidate install path is stable (V012-05).
