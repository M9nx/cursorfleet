# Architecture Decision Records

Short, dated records of decisions that shape CursorFleet. Start new ADRs from
[`0000-template.md`](0000-template.md). Number sequentially, never renumber,
and supersede rather than edit accepted decisions (clarifying typos is fine).

Every ADR that depends on Cursor behaviour must separate facts verified from
the Cursor docs from facts that still need an empirical check, and must name
the `cursor_version` for anything empirical.

## Index

- [0000: Template](0000-template.md)
- [0001: Cursor capabilities and limits (docs-verified; empirical spike pending)](0001-cursor-capabilities.md): provisional until the M0a spike in `spike/README.md` has been run against a live Cursor session.
- [0002: Storage layout and runtime directory](0002-storage-layout-and-runtime-directory.md): provisional; `<git-common-dir>/cursorfleet/`, per-session JSONL spool, single-writer SQLite. Needs spike Q4 and Q5.
- [0003: Event model and sanitization allowlist](0003-event-model-and-sanitization.md): provisional; field map, closed kind enum, command and path sanitization. Identity fields need Q1 and Q2.
- [0004: No chain-of-thought; never register content hooks](0004-no-chain-of-thought-and-hook-policy.md): accepted.
- [0005: Naming and trademark](0005-naming-and-trademark.md): accepted; fallback name `fleet-for-cursor` (availability unverified).
- [0006: Agent-declared events via Markdown artifacts](0006-agent-declared-events.md): provisional; `emit` CLI fallback, MCP deferred to v0.2.

Related documents: [product contract](../product-contract.md),
[threat model](../threat-model.md), [privacy](../privacy.md),
[architecture](../architecture.md).
