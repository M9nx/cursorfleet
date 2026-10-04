# ADR 0008: Enforcement boundaries (Observe, Guard, Prove)

- Status: accepted
- Date: 2026-10-04
- Deciders: project owner (M9nx), architecture-owner decision
- Evidence level: verified-from-docs (ADR 0001 A2, A3, A6, A7); behaviour of `ask`, `deny` and the reply shapes is unobserved
- Supersedes: none
- Superseded by: none
- Related ADRs: 0001 (A2, A3, A6), 0004 and 0007 (hook list and fail-open replies), 0009 (what the installer may write), 0011 (evidence tiers)
- Implementation status: Implemented-provisional. Hooks fail open and never set `failClosed` or `matcher`; no code path produces `deny`, `ask`, `updated_input` or a `followup_message`. `schemas/policy.schema.json` is reserved and unused. Nothing is validated against live Cursor.
- Review trigger: any request to make a hook block, ask or deny; the spike result on `ask` and on the permission-hook reply; Cursor changing `stop` or `preToolUse` semantics
- Release gate: README, quickstart, `doctor` output and product contract say "observe only, no enforcement" and nothing in the code can emit a blocking reply; the permission-hook fail-open reply is confirmed (ADR 0007)

## Context

Verified from the Cursor docs (ADR 0001, fetched 2026-10-04):

- `stop` and `subagentStop` can only submit a `followup_message`, capped by `loop_limit`
  (default 5). They cannot block completion (A6).
- `ask` is accepted by the `preToolUse` schema but **not enforced today**. For
  `subagentStart`, `ask` is not supported and is treated as `deny` (A2).
- Subagent frontmatter has no tool allowlist, path scope, network or git permission field.
  `readonly` is the only coarse switch (A7).
- Exit code 2, a `deny` permission, or `failClosed: true` on a hook definition block an
  action; invalid output from a permission hook blocks it too (A3).
- All matching hooks from every source run; any `deny` beats `ask` beats `allow` (A4).

## Decision

CursorFleet separates three capabilities and ships only the first in v0.1.

- **v0.1 Observe (this release).** Observe and display. No allow, deny or ask decisions;
  no `updated_input`; no `followup_message`; no exit code 2; no `failClosed`. Every hook
  returns the no-op reply for its type (`{"permission":"allow"}` for `preToolUse` and
  `subagentStart`, `{}` for the rest) and exits 0 on any internal error.
  **Hooks never block in v0.1.**
- **v0.2 Guard (not built).** A policy engine with allow, warn, ask and deny **where Cursor
  supports it**: `deny` on `preToolUse` (enforced per the docs), path-scoped write denial,
  tamper protection for hook config and policy, a `failClosed` shim, headless `ingest`.
  `ask` on `preToolUse` is not relied on until observed to work. Guard needs its own ADR
  and a threat-model update before any line is written.
- **v0.3 Prove (not built).** Evidence contracts bound to a commit SHA, produced by
  deterministic runners outside the agent's control; review, patch, re-review state
  machine; QA in a fresh worktree; external gate command and CI status. Real "done" gating
  lives outside Cursor (CLI exit code, git hook, CI) because Cursor cannot block `stop`.

### Platform limits that bound all three

- Cursor cannot block `stop` or `subagentStop`, so "an agent may not finish while gates
  fail" is not enforceable inside Cursor.
- `ask` is not enforced on `preToolUse` and is `deny` on `subagentStart`.
- Subagent capabilities cannot be restricted per agent; the roster's capability notes are
  documentation only.
- **Guardrails are not a security boundary.** A same-user, prompt-injected or malicious
  agent can edit hook config, delete the spool or call tools through paths no hook sees.
  Observe-only telemetry is best-effort and forgeable (threat model).

### Fail-open versus `failClosed`

- v0.1: `failClosed` is **never** written. The installer does not emit it, the config model
  cannot express it, and `doctor` lists the `failClosed` setting of every hook entry it
  finds.
  A crash, timeout, missing binary or malformed payload lets the action proceed.
- A permission-hook reply that Cursor rejects blocks the action; that is why the reply is
  `{"permission":"allow"}` rather than `{}` for `preToolUse` and `subagentStart`, and why
  that shape is a release gate.
- v0.2 may use `failClosed` only for a hook that enforces a named policy, only through a
  small stdlib shim that decides within its time budget, and only after a superseding ADR.
  Observation hooks stay fail-open forever.
- No `matcher` is written in v0.1; a wrong matcher silently loses events (see
  `hooksjson.py`).

## Consequences

- Positive: v0.1 cannot block or break an agent through policy; the claims in the docs are
  small enough to be true.
- Negative / costs: no prevention of anything; gates in v0.1 are display only (and, per
  ADR 0003 rule R1, not even derived from heuristics).
- Follow-ups: Guard and Prove ADRs when those milestones start; the spike rows for `ask` and
  the reply shape.

## Open questions

- Does Cursor accept `{"permission":"allow"}` from `preToolUse` and `subagentStart`, and does
  `{}` work too?
- Does `deny` on `preToolUse` block every tool type, including `Task` and MCP tools?
- Does `ask` on `beforeShellExecution` show a prompt? (Informational: that hook is not
  registered in v0.1.)

## Alternatives considered

- Ship a warn-only policy in v0.1: rejected, it needs the reply shapes to be verified and
  adds surface before the observer is validated.
- Use `stop` follow-ups as a soft gate: rejected, capped by `loop_limit`, not a gate, and
  it injects text into the conversation.
- `failClosed` for tamper resistance now: rejected, a missing binary on a teammate's
  machine would block their agent.
