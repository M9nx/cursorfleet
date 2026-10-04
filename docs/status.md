# Project status

Last updated: 2026-10-04. CursorFleet is unofficial and pre-alpha; nothing is published.
Everything here was written and reviewed by the same author: it is a self-review, not an
independent audit.

## Process freeze

New M2 and TUI implementation is **frozen** until both of these are true:

- The M0a live Cursor spike ([`spike/README.md`](../spike/README.md)) has been run on a real
  Cursor install and its raw captures reviewed.
- The ADR 0001 questions (Q1 to Q6 and the secondary questions) are answered in
  [`spike/questions.md`](../spike/questions.md) and ADR 0001, with the Cursor version and
  surface recorded. The full list is in [`empirical-test-plan.md`](empirical-test-plan.md).

While frozen:

- Allowed: documentation, ADRs, bug fixes that keep behaviour the same, the spike kit, and
  the follow-up tasks in [`follow-ups.md`](follow-ups.md) once the spike has answered the
  question each one depends on.
- Not allowed: new features, new hooks, new TUI screens, new event kinds, new CLI commands.
- Each follow-up task states the spike result it waits for.

## State of the code

- M0 (foundations, spike kit): done. The spike kit has only been self-tested with
  synthetic payloads.
- M1 (kit: `init`, `uninstall`, `doctor`, `validate`): **implemented, provisional,
  unvalidated against live Cursor.**
- M2 (hook, spool, indexer, reducer, git collector, `status --json`): **implemented,
  provisional, unvalidated against live Cursor.**
- M3 (Textual TUI): **implemented, provisional, unvalidated against live Cursor.** Gate
  tiles are heuristic and non-authoritative (see [`tui.md`](tui.md) and ADR 0011).
- M4 (CI, docs, release preparation): done as files. CI has not run on GitHub. Nothing was
  tagged, published or pushed.

"Unvalidated against live Cursor" means: hook payload shapes come from the Cursor
documentation, not from captures. The permission-hook reply shape, agent identity inside
subagent tool hooks, custom `subagent_type` naming, behaviour in the CLI, Agents Window and
worktrees, and hook latency inside Cursor are all unobserved. The only latency number is
Linux steady-state process time outside Cursor; there is no first-run or end-to-end number.
The end-to-end release contract (PASS median <= 100 ms and p95 <= 200 ms over paired
hooks-on/hooks-off calls) is defined in [ADR 0001 section D](adr/0001-cursor-capabilities.md)
and not yet measured.

## Supported surface for v0.1

- Local Cursor IDE (desktop) only, and even that is unverified until the spike runs.
- Not claimed: Cursor CLI (`agent`), Agents Window, Cursor-managed or manual worktrees as a
  tested path, cloud agents, other IDEs. See [`platform-support.md`](platform-support.md) and
  [ADR 0001](adr/0001-cursor-capabilities.md).

## Where the code and the decisions disagree

The architecture-owner decisions of 2026-10-04 (ADRs 0001 to 0012) differ from the current
code in several places: the hook list, schema version, heuristic test events, command
display default, hashing, locking, artifact format, gate derivation, attribution
aggregation (the reducer keeps the strongest value; the rule is weakest-wins),
`init`/`uninstall` repository-root preconditions (exit 2 at a non-root is implemented;
`doctor`/`validate` still do not print the detected root), and remaining ADR follow-ups
other than task 16. Runtime inheritance for a nested non-Git directory is implemented
in code; live row 17b remains OPEN. They are listed in [`follow-ups.md`](follow-ups.md).
New M2 and TUI implementation stays frozen.

## Gates before v0.1.0

The per-ADR release gates are summarised in the [ADR index](adr/README.md). The owner steps
are in [`release-checklist.md`](release-checklist.md). Naming and trademark review (ADR
0005) is a release gate, and no public docs site is published before it
([`docs-site-plan.md`](docs-site-plan.md)). The owner has chosen Zensical for the docs site
(mdBook is the documented fallback); nothing is built or published yet.
