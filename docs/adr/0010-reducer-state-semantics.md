# ADR 0010: Reducer state semantics

- Status: provisional (ordering, dedupe, clock and replay rules are firm; lane rules are heuristics that depend on spike Q1 and Q2)
- Date: 2026-10-04
- Deciders: project owner (M9nx), architecture-owner decision
- Evidence level: code (`src/cursorfleet/state/reducer.py`, `state/models.py`, `state/indexer.py`) plus assumption for Cursor behaviour
- Supersedes: none
- Superseded by: none
- Related ADRs: 0001 (Q1, Q2), 0002 (spool, indexer, watermark), 0003 (attribution, event kinds, `verification.observed`), 0006 (self-reported events), 0007 (which events exist), 0011 (evidence tiers)
- Implementation status: Implemented-provisional for the fold, ordering, dedupe, watermark rebuild, injected clock, stale rule and replay digest. Divergent-from-code for: `test.completed` (renamed `verification.observed` by ADR 0003), attribution aggregation (strongest instead of weakest, ADR 0003), and the `reviewed` flag semantics (below). Not implemented: lane basis shown as heuristic in every view.
- Review trigger: Q1 or Q2 answered; a lane rule changed; any proposal to feed reducer output into a gate
- Release gate: replay equivalence and order-independence tests green (they are today); every lane and every `reviewed` or "verifying" indication in the TUI and `status --json` carries its basis; no reducer output used as gate evidence

## Context

The reducer turns events into per-session, per-agent and per-worktree state that the CLI and
the TUI display. Its job is to be boring: the same events always give the same state, and it
never claims more than the events support. Cursor hooks do not say what an agent is "doing",
so lanes are inferences over tool names and lifecycle events.

## Decision

### Deterministic fold

- The reducer is a pure function of the **set** of events plus an injected `now`. It reads no
  clock, environment, file or network.
- `reduce_events` yields identical state for any input order and for exact duplicates.
  `apply_event` is the incremental form and requires events in order; out-of-order input
  raises.

### Ordering and deduplication

- Total order: `(ts normalised to UTC, event_id)`. `event_id` is a ULID-style id.
- At most one event per `event_id` is folded. Duplicates are dropped, keeping the first in
  total order, with the serialised content as the final tie-break.
- The indexer keeps a per-session watermark `(ts, event_id)` and a `seen` table. An event
  that sorts at or before the watermark makes the indexer **rebuild that session from the
  spool**, so incremental indexing equals a full replay.

### Lanes

A lane is a display classification with a stated basis; it is never evidence (ADR 0011).

- Lanes: `queued`, `loading_context`, `planning`, `working`, `verifying`, `awaiting_review`,
  `patching`, `blocked`, `done`, `stale_offline`, `unknown`.
- Transition rules as implemented (all heuristic, **provisional**):
  - `session.started`: `unknown` becomes `queued`. `session.stopped`: `done`.
  - `tool.started`: a verification-like command sets `verifying`; planning tools
    (`TodoWrite`, plan tools, `SwitchMode`) set `planning` from an early lane and otherwise
    `working`; read-class tools set `loading_context` from an early lane and otherwise keep
    an active lane; a write tool after `awaiting_review` sets `patching`; anything else
    `working`.
  - `status.changed` (from `stop`): `waiting` becomes `awaiting_review` and sets `reviewed`;
    `error` or `blocked` becomes `blocked`; `working` and `done` set those lanes; `idle` and
    `unknown` keep the current lane.
  - `file.changed`: `patching` if `reviewed`, else `working`.
  - `subagent.started`: `working`, lifecycle `running`. `subagent.stopped`: `done`, or
    `blocked` if the outcome was failed; records a stop report.
  - Self-reported `plan.created`, `context.loaded`, `handoff.created`, `blocker.raised` may
    move an agent to `planning`, `loading_context`, `awaiting_review` or `blocked`; the lane
    source is then `self_reported`.
- Each agent view carries `lane_source` (`observed`, `derived`, `self_reported`) and
  `lane_basis` (`observed_activity`, `lifecycle_only`, `self_reported`, `derived`, `none`).
  v0.1 must show the basis wherever a lane is shown.
- `verifying` and `awaiting_review` are the least certain lanes: the first rests on a command
  classifier (ADR 0003 rule R1 applies), the second on a `stop` status that does not mean a
  review was requested. The `reviewed` flag set from `stop` is an inference, not an
  independent review, and must not be presented as one.

### Unknown versus idle versus stale

- **Unknown / no telemetry:** nothing has been observed for the entity (or only unattributed
  events exist). Shown as such with setup guidance. Never rendered as idle.
- **Idle:** there is **no `idle` lane** in v0.1. Nothing positively observed proves idleness;
  `stop` ends a turn, not the agent's life, and the reducer keeps the previous lane.
- **Stale:** a non-terminal agent whose newest **live** (non-self-reported) event is older
  than `stale_after_s` (default 900) becomes `stale_offline` and keeps its previous lane as
  `last_lane`. `done` and `unknown` are never made stale. A running subagent with no
  attributed events borrows its session's liveness (`lifecycle_only`).
- Silence is not idleness and is not completion.

### Clock injection

- `now` and `stale_after_s` are parameters of every snapshot function. Tests, `replay` and
  `status --json` (`generated_at`) pass the clock explicitly. Nothing inside the fold calls
  the system clock.

### Pairing `subagentStop` to `subagentStart`

- Cursor documents no `subagent_id` on `subagentStop` (ADR 0001 A5), so pairing is
  **provisional**. Order of preference:
  1. an explicit instance id on the stop event, if the spike shows one exists;
  2. among running subagents of the same role, the one whose start time is closest to
     `stop_ts - duration_ms`, or the earliest start when no duration is known;
  3. otherwise the stop is **unpaired**: it is counted (`unpaired_stops`) and shown under a
     synthetic entry; it is never forced onto an agent.
- A candidate additional link, `Task` `tool_use_id` equal to `subagentStart.tool_call_id`, is
  recorded (`spawn_link`) but not used for pairing until the spike answers the secondary question on `Task` linkage.

### What is observed, inferred and self-reported

- **Observed:** facts from a hook payload through the allowlist: session and subagent
  lifecycle, tool names, outcomes, durations, compaction metrics, stop status.
- **Derived (inferred by CursorFleet):** lanes, `verification.observed` classification,
  worktree ownership from git plus events, staleness. These are computed, labelled `derived`
  or shown with a basis, and are heuristics.
- **Self-reported:** artifacts and `emit` events (ADR 0006); labelled and ineligible as
  evidence.
- The reducer never attributes an unattributed event to a running subagent by timing; such
  events accumulate on the `main` entry with `attribution: unknown`.

### Replay equivalence

- `cursorfleet replay <session>` reduces the spool twice, reports `deterministic`, and prints
  a SHA-256 digest of the canonical state. A full replay, an incremental index and a
  rebuild after a late event must produce the same state. This is property-tested.

## Consequences

- Positive: state is reproducible and debuggable from the spool alone; the UI can always
  explain a lane; stale and unknown are distinct from idle.
- Negative / costs: lanes are coarse and sometimes wrong; no idle lane means a quiet but
  healthy agent looks stale after 15 minutes; pairing can fail until Q1 is answered.
- Follow-ups: show lane basis everywhere; rename the `reviewed` flag; rewire after
  `verification.observed`; reconsider lanes after the spike.

## Open questions

- Q1: do tool hooks in a subagent carry identity? If yes, the `main` accumulation shrinks and
  attribution can be `exact`.
- Is a 900 s default staleness window right for long-running tools?
- Should a positively observed `stop` with `aborted` produce an `idle` lane?

## Alternatives considered

- Attribute tool events to the most recently started subagent by time: rejected, wrong with
  parallel subagents and would mislabel inferred as exact.
- An `idle` lane after N seconds of silence: rejected, silence is not idleness.
- Wall-clock reads inside the reducer: rejected, breaks replay.
