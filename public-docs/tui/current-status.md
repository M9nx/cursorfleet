# TUI current status

The dashboard works against **live hook telemetry** (Linux Cursor IDE 3.22.7 maintainer
smoke) and against synthetic fixtures. **Active Run** (`a`) is the default screen; **o** opens
the session archive.

## Empirical gates

- **Q1** and **Q2** remain **OPEN**; the UI does not treat missing identifiers as zero
  matches or infer quiet idle.
- **session_id** is correlation only, never agent identity.
- Unpaired subagent start/stop stays visible; parallel execution is not assumed.

## Implemented

- Active run default, runs list (`u`), sessions archive (`o`), observations (`g`).
- Overview lanes, agent detail, timeline (paged), worktrees, evidence, help.
- Observe-only: no allow/deny/ask, no network, no fetch, no prompt or thinking display.
- Live refresh against spool + projection; optional `watchfiles`; corrupt DB rebuild from spool.
- Work artifacts under `.cursorfleet/work/` shown as self-reported; body never displayed.
- Run-scoped git context on Active run when sessions are linked to a run.

## Known limitations

- Run association requires explicit `cursorfleet run start` / `attach` or `CURSORFLEET_ACTIVE_RUN`.
- TUI attach picker deferred to v0.1.1; see [B0 evidence](https://github.com/M9nx/cursorfleet/blob/main/docs/evidence/b0-run-association-spike.md).
- Maintainer screenshot (when added): [active-run-screenshot.png](https://github.com/M9nx/cursorfleet/blob/main/docs/evidence/active-run-screenshot.png) (optional pre-tag).
- Many separate Cursor chats produce many sessions until runs are linked.

See [known limitations](../known-limitations.md).
