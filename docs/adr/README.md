# Architecture Decision Records

Short, dated records of decisions that shape CursorFleet. The process, the required fields and
the template are in [`0000-template.md`](0000-template.md). Number sequentially, never
renumber, and supersede rather than edit accepted decisions (clarifying typos and filling in
"Implementation status" is fine).

Every ADR that depends on Cursor behaviour separates facts verified from the Cursor docs
from facts that still need an empirical check, and names the `cursor_version` for anything
empirical. ADRs are the author's own reasoning and have had no independent review.

## Index

Each entry: status; supersession; implementation status (see 0000 for the vocabulary);
release gate in one line. The full gate text is in each ADR.

- [0000: ADR process and template](0000-template.md)
  - Status: accepted. Supersedes: none.
  - Implementation: Implemented.
  - Gate: every ADR carries all required fields.
- [0001: Cursor capabilities and limits](0001-cursor-capabilities.md)
  - Status: **provisional**. Supersedes: none. Related: 0002, 0003, 0007, 0008, 0012.
  - Implementation: Implemented-provisional; its 12-hook list is amended by 0007.
  - Gate: Q1 to Q6 answered, section B resolved, real fixtures, permission-hook reply confirmed, end-to-end latency contract (section D: paired hooks-on/hooks-off, PASS median <= 100 ms and p95 <= 200 ms) met per OS claimed.
  - Local Cursor IDE (desktop) is the only supported v0.1 surface until the empirical test matrix passes.
- [0002: Storage layout and runtime directory](0002-storage-layout-and-runtime-directory.md)
  - Status: provisional (git-common-dir design kept). Supersedes: none.
  - Implementation: Divergent-from-code (CRC32 fingerprints, unkeyed worktree ids, no maintenance lock).
  - Gate: Q4 and Q5 answered on each OS claimed; BLAKE2s, HMAC ids and the lock implemented.
- [0003: Event model and sanitization allowlist](0003-event-model-and-sanitization.md)
  - Status: provisional (amended 2026-10-04). Supersedes: none.
  - Implementation: Divergent-from-code (schema `1.0`, `test.completed`, command display on, attribution aggregation keeps the strongest value instead of the weakest).
  - Gate: schema `0.1`; `verification.observed`; no heuristic gates; display default off.
- [0004: No chain-of-thought; never register content hooks](0004-no-chain-of-thought-and-hook-policy.md)
  - Status: **superseded by [0007](0007-narrower-v01-hook-policy.md)**. Content kept.
  - Implementation: its never-register rule is implemented; its 12-hook list is divergent.
  - Gate: none of its own.
- [0005: Naming and trademark](0005-naming-and-trademark.md)
  - Status: **provisional** (working name). Supersedes: none.
  - Implementation: working name in use everywhere.
  - Gate: public name chosen without a third-party mark; registry availability and trademark review done.
- [0006: Agent-declared events via Markdown artifacts](0006-agent-declared-events.md)
  - Status: provisional (TOML frontmatter). Supersedes: none.
  - Implementation: Divergent-from-code (YAML subset, no `artifact_id`/`revision`/digest).
  - Gate: TOML with `tomllib`, identity, revision and digest implemented; artifacts ineligible as gate evidence.
- [0007: Narrower v0.1 hook policy](0007-narrower-v01-hook-policy.md)
  - Status: accepted. **Supersedes 0004.**
  - Implementation: Divergent-from-code (12 hooks registered, 9 decided).
  - Gate: installer registers exactly nine hooks; permission-hook reply confirmed.
- [0008: Enforcement boundaries](0008-enforcement-boundaries.md)
  - Status: accepted. Supersedes: none.
  - Implementation: Implemented-provisional.
  - Gate: nothing can emit a blocking reply; docs say observe only.
- [0009: Install and uninstall ownership](0009-install-uninstall-ownership.md)
  - Status: accepted. Supersedes: none.
  - Implementation: Implemented-provisional; no migration for removed hooks.
  - Gate: round trip passes on all three OSes in CI; migration exists.
- [0010: Reducer state semantics](0010-reducer-state-semantics.md)
  - Status: provisional. Supersedes: none.
  - Implementation: Implemented-provisional; some divergences from 0003.
  - Gate: lane basis shown everywhere; no reducer output used as gate evidence.
- [0011: Evidence trust model](0011-evidence-trust-model.md)
  - Status: accepted. Supersedes: none.
  - Implementation: Divergent-from-code (TUI derives gates from heuristics).
  - Gate: no v0.1 gate satisfied by tier 1 to 3 data; tiers labelled in the UI.
- [0012: Roster and worktree ownership](0012-roster-and-worktree-ownership.md)
  - Status: provisional. Supersedes: none.
  - Implementation: Implemented-provisional.
  - Gate: owners shown with attribution labels; no isolation or cleanup claims; worktree claims match the spike.

## Supersession links

- 0004 is superseded by 0007.
- No other ADR is superseded. 0005 and 0006 were revised in place while provisional; their
  earlier text is in git history.

## Release gates summary (before v0.1.0 is tagged)

Spike and facts:

- ADR 0001: spike run, Q1 to Q6 and secondary questions answered, real sanitized fixtures
  committed, permission-hook reply shape confirmed.
- ADR 0002: Q4 and Q5 answered on every OS claimed.
- ADR 0007: installer registers exactly the nine hooks.

Code brought in line with the decisions:

- ADR 0002: BLAKE2s segment fingerprints, HMAC worktree ids, maintenance lock.
- ADR 0003: schema `0.1`; `verification.observed`; command display default off; attribution
  never shows inferred as exact.
- ADR 0006: TOML artifacts with identity, revision and digest.
- ADR 0009: migration that removes hook entries for hooks no longer registered.
- ADR 0010 and 0011: lane basis shown; no gate satisfied by heuristic or self-reported data.

Project and legal:

- ADR 0005: public name chosen and checked (PyPI, npm, GitHub), trademark review done.
- ADR 0008: docs and code say observe only, no enforcement.
- ADR 0012: no isolation or cleanup claims.

The ordered implementation tasks are in [`../follow-ups.md`](../follow-ups.md); the live
tests are in [`../empirical-test-plan.md`](../empirical-test-plan.md); the owner steps are in
[`../release-checklist.md`](../release-checklist.md).

Related documents: [project status](../status.md), [product contract](../product-contract.md),
[threat model](../threat-model.md), [privacy](../privacy.md), [architecture](../architecture.md).
