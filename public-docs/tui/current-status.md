# TUI current status

The dashboard works against **live hook telemetry** (Linux Cursor IDE 3.22.7 maintainer
smoke) and against synthetic fixtures. **M2.5** is improving the default experience toward
**Active Run** (task-centric) is the default TUI screen; press **o** for the session archive.

## Empirical gates

- **Q1** and **Q2** remain **OPEN**; the UI does not treat missing identifiers as zero
  matches or infer quiet idle.
- **session_id** is correlation only, never agent identity.
- Unpaired subagent start/stop stays visible; parallel execution is not assumed.

## Implemented

- Overview lanes, agent detail, timeline (paged), worktrees, gates/evidence, help.
- Observe-only: no allow/deny/ask, no network, no fetch, no prompt or thinking display.
- Live refresh against spool + projection; optional `watchfiles`; corrupt DB rebuild from spool.
- Work artifacts under `.cursorfleet/work/` shown as self-reported; body never displayed.

## M2.5 in progress

- **Active Run** default screen and stale-session hiding (prototype behind env flag during B1).
- **Observations** replacing misleading PASS/FAIL gate tiles (A3/E).
- **Violations** placeholder will be **removed** from alpha navigation (v0.2 Guard is separate).
- Plain trust labels on primary rows (Observed / Declared / Inferred / Unavailable / Conflict).

## Known live-smoke limitations

- Many separate Cursor chats produce many sessions; overview becomes noisy until Active Run ships.
- Observed and declared role cards can duplicate until reconciliation (M2.5-C).

See [known limitations](../known-limitations.md).
