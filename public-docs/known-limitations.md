# Known limitations

CursorFleet is pre-alpha. **0.1.0** and **0.1.1** are published on
[PyPI](https://pypi.org/project/cursorfleet/) (2026-10-12); versions on `main` may be
ahead. The name **CursorFleet is a working name**; the final-name gate stays tracked in
[ADR 0005](https://github.com/M9nx/cursorfleet/blob/main/docs/adr/0005-naming-and-trademark.md).

## v0.1 is Observe only

No enforcement, no forced approvals, no allow / deny / ask. Hooks always
fail open. It is not a security boundary. See
[privacy and security](privacy-and-security.md).

## Local IDE only until matrix PASS

The intended v0.1 surface is the **local Cursor IDE (desktop)**. A maintainer smoke on
Linux IDE 3.22.7 confirmed hook telemetry, subagent lifecycle and artifact scanning
([live validation index](https://github.com/M9nx/cursorfleet/blob/main/docs/evidence/live-validation-index.md)),
but the formal empirical matrix has not run. The Cursor CLI, the Agents Window,
Cursor-managed and manual worktrees, parallel subagents, and cloud agents are not
claimed.

Live B0 run-security scenarios 1/2/5, the SO-01 live permission-hook rows and
end-to-end latency row 13B are still recorded as open gates; see the
[TUI current status](tui/current-status.md) and the in-repo v0.1.2 baseline.

## Published, still early software

- PyPI releases: 0.1.0 and 0.1.1 (both 2026-10-12 UTC). Install with
  `uv tool install cursorfleet` or `pipx install cursorfleet`
  ([installation](getting-started/installation.md)).
- GitHub: tags `v0.1.0` and `v0.1.1`; no published (non-draft) GitHub Releases page yet,
  so a tag is not the same as a published release.
- Nothing here has been reviewed by an author other than the maintainer; treat it as a
  self-review, not an audit.

## Q1 and Q2 remain OPEN

- **Q1** — Do tool hooks fired inside a subagent identify the current
  subagent instance, or can they be deterministically linked to it?
- **Q2** — Does `subagent_type` show a custom subagent name, the filename,
  or only a built-in type such as `generalPurpose`?

Until those are classified by hand from a READY capture, per-agent tool
timelines can be wrong and custom roster names may not appear as expected.

## Parallel identity classification is BLOCKED/OPEN

On the tested **Cursor 3.22.7 Linux** surface, analyzer readiness for
parallel / background lifecycle is **BLOCKED/OPEN**. Formal repeated
parallel classification has not run. Do not infer a Q1 verdict from that
surface.

A later sanitized observation on that same surface (raw captures stay
private and outside this repository) showed:

- Two-agent attempts repeatedly produced two starts, zero stops, no
  `is_parallel_worker=true`, and no overlapping subagent windows. Task
  background flags were missing.
- `parent_tool_call_id` matched comparable inner events (every comparable
  inner event matched; no mismatches or collisions).
- Formal repeated parallel classification has **not** run.

`parent_tool_call_id` is an unclassified link candidate until concurrent
repetitions verify it. It is not current-subagent identity by itself.

## Other unverified Cursor facts

- Whether the Git common directory resolves identically from every Cursor
  surface (Q4). If not, some agents appear under UNKNOWN / NO TELEMETRY.
- Hook overlap and append integrity under parallel load (Q5).
- Hook latency inside Cursor (Q6). Linux steady-state process time outside
  Cursor has been measured; first-run, macOS, Windows, and end-to-end paired
  deltas have not.
- Whether agents follow the work-artifact conventions, and that
  `author_role` is not forged (it can be).

## Product limits that will not change in v0.1

- Cloud agents and cloud subagents are invisible.
- No token or cost budget. Cursor hooks do not expose usage except context
  numbers on compact.
- Gate tiles are heuristic and non-authoritative. STALE / OFFLINE is not
  idle.
- Worktree isolation is requested, not configured. CursorFleet does not
  create or delete worktrees.
- Telemetry is best-effort: events can be dropped.
- Linux is the tested platform; macOS and Windows are CI-tested only.
- Cursor is the only officially supported IDE.

See [sessions](concepts/sessions.md), [agents and events](concepts/agents-and-events.md),
and [TUI current status](tui/current-status.md).
