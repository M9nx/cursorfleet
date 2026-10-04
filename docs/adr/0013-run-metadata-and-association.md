# ADR 0013: Run metadata and explicit association

- Status: Accepted (M2.5 B0/B2)
- Date: 2026-10-05
- Implementation status: Implemented-provisional

## Context

M2.5 introduces a **task-centric** observer. Sessions remain the hook telemetry unit; runs
group sessions and declared artifacts for one task without mutating git or agent content.

## Decision

1. **Storage:** Run records live under `<git-common-dir>/cursorfleet/runs/<run_id>.json`
   (schema `cursorfleet.run/0.1`). Not in the working tree by default.
2. **Membership is never silent:** Sessions join a run only via explicit attach
   (`cursorfleet run attach`, env `CURSORFLEET_ACTIVE_RUN` on hook path, or future TUI
   picker). Artifact task slugs suggest candidates only.
3. **Observe contract unchanged:** Hooks stay fail-open; run attach failures never block
   Cursor.
4. **Status JSON:** When `runs[]` is present, `schema` is `cursorfleet.status/0.2`.

## Consequences

- Multi-chat workflows need an explicit linking step until automatic association is proven.
- TUI **Active run** reads run files + projection; B1 in-memory fallback uses declared task
  slugs when no run file exists.
