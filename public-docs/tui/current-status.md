# TUI current status

The dashboard exists and is usable against synthetic and fixture data. It is
**provisional and unvalidated against live Cursor.** New TUI screens and
event kinds are frozen until the live spike answers the open Cursor
questions.

## Spike gates (empirical)

- **Q1** and **Q2** remain **OPEN**; the UI does not treat missing identifiers
  as zero matches or infer quiet idle.
- **session_id** is shown for correlation only, never as agent identity.
- Incomplete subagent lifecycles (unpaired start/stop) stay visible; the UI
  does not assume background or parallel execution.

## Implemented

- Overview lanes, agent detail, timeline (paged), worktrees, evidence, help.
- Observe-only: no allow/deny/ask, no network, no fetch, no prompt or
  thinking display.
- Keys, layouts, filter, pin, tiles, re-read, and `NO_COLOR` as described in
  [overview](overview.md).
- Refresh on a timer; optional `watchfiles` extra for spool-change wakeups;
  a failed watcher falls back to polling. A missing or corrupt projection is
  rebuilt from the spool. A failed refresh keeps the last good data and
  shows "refresh failed".
- Work artifacts under `.cursorfleet/work/` are scanned read-only and shown
  as self-reported. The body is never displayed.

## Planned / under development

- **Violations screen.** Placeholder only. A policy engine (allow / warn /
  ask / deny) is v0.2 Guard, not built.
- **Authoritative gates.** Real PASS / FAIL needs evidence from a
  deterministic runner bound to a commit SHA (v0.3 Prove). Not built.
- **Cloud-agent visibility.** Never in v0.1.
- **Token or cost budgets.** Not exposed by Cursor hooks; not planned as a
  v0.1 feature.
- **Cursor CLI, Agents Window, and worktree surfaces.** Not claimed until
  the spike marks those rows PASS.

## Gate tiles are heuristic and non-authoritative

The gates screen is labelled "heuristic, non-authoritative". It is a display
of guesses, not proof that anything passed. v0.1 does not enforce or certify
any gate. Cursor's `stop` hook cannot block completion.

The ten signals (each its own tile, never aggregated): unit tests,
integration tests, type check, lint, security checks, independent review,
re-review, documentation, CI status, merge readiness.

Intended states are UNKNOWN, STALE, and "observed (heuristic)". The current
build still draws PASS and FAIL from a command classifier over sanitized
shell text and its exit code. Read those tiles as "a command that looked
like this exited 0 or non-zero", nothing more. Review, documentation, CI,
and merge readiness have no observable source in v0.1 and stay UNKNOWN.

Self-reported artifacts never satisfy a gate.

## STALE / OFFLINE is not idle

An agent with no recent events is **STALE / OFFLINE**. An agent or worktree
with no hook telemetry is **UNKNOWN / NO TELEMETRY**, with setup guidance.
There is no idle lane. Silence is not evidence that the agent is waiting
quietly.

Lane assignment from hooks without tool activity is coarse
("lifecycle-only") and depends on subagent identity (Q1, still OPEN).

See [known limitations](../known-limitations.md).
