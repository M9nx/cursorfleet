# ADR 0011: Evidence trust model

- Status: accepted (design); the tier 4 mechanism is a v0.3 plan
- Date: 2026-10-04
- Deciders: project owner (M9nx), architecture-owner decision
- Evidence level: assumption (a design decision about trust; threat model in `docs/threat-model.md`)
- Supersedes: none
- Superseded by: none
- Related ADRs: 0003 (rule R1, `source`, `verification.observed`), 0006 (self-reported artifacts), 0008 (Observe, Guard, Prove), 0010 (derived lanes)
- Implementation status: Divergent-from-code. `source` (`observed | derived | self_reported`) exists and self-reported events are excluded from `tui/gates.py` evidence. But the TUI derives PASS, FAIL and STALE gate states from heuristic `test.completed` events, which this ADR forbids (tier 2 cannot satisfy a gate). Tier 4 does not exist. No staleness rule is bound to a tree hash, only to a commit SHA recorded on the event.
- Review trigger: any feature that turns a signal into a pass/fail, "ready" or "safe" indication; the start of v0.3 work; a new event producer
- Release gate: no gate in v0.1 is satisfied by tier 1, 2 or 3 data; the UI labels each displayed signal with its tier; `docs/tui.md` says gate display is non-authoritative until tier 4 exists

## Context

CursorFleet shows things agents did, and things agents said. These are not equally
trustworthy: a same-user agent can forge, delete or edit anything on disk, and a
classifier over command text is a guess. Without an explicit trust order, a convenient
display ("tests pass") becomes an implied guarantee. This ADR fixes the order and what each
level may be used for.

## Decision

### Evidence tiers (lowest to highest trust)

1. **Observed hook telemetry.** Facts that came through an allowlisted hook payload: a tool
   was called, a subagent started, a session ended, a tool failed. Trust: as good as Cursor's
   payloads (unverified until the spike) and the local account; tamperable by a same-user
   agent.
2. **Heuristic.** Anything CursorFleet computes by guessing: command classification
   (`verification.observed`), lane assignment, worktree ownership, attribution that is not
   `exact`, pairing of stops to starts. Always carries `heuristic: true` or a basis label.
3. **Self-reported artifact.** What an agent wrote about itself in a work artifact or via
   `emit`: plans, handoffs, blockers, "context loaded". `source=self_reported`. Forgeable,
   including `author_role`.
4. **Deterministic runner evidence bound to a commit SHA and tree hash.** A result produced
   by a command run by CursorFleet or CI outside the agent's control (v0.3): runner identity,
   exact argv, exit code, the commit SHA **and** tree hash it ran against, a clean-tree
   check, and a digest of the output, recorded in a place the agent cannot write.

Tiers 1 to 3 are *signals*. Only tier 4 is *evidence*. The ordering above is not a ranking
of honesty: tier 1 is not higher than tier 3 because it is "true", but because it did not
pass through the agent's own account of itself.

### What each tier may be used for

- **Display:** tiers 1, 2 and 3, each labelled with its tier (source and basis shown in the
  TUI and in JSON).
- **Gates:** **only tier 4.** No gate may be PASS or FAIL from tier 1, 2 or 3. In v0.1 no
  tier 4 source exists, so every gate is "not evaluated"; heuristic observations may be shown
  next to it as "observed, heuristic" (ADR 0003 rule R1).
- **Lane and status hints:** tiers 1, 2 and 3 with their basis visible.
- **Blocking or permission decisions (v0.2):** never from tier 2 or 3; tier 1 only for
  facts the hook itself provides (for example the tool name being denied).

### Staleness

- Tier 4 evidence is bound to a commit SHA and tree hash. When HEAD or the tree moves, it
  becomes stale and stays visible with the old value; it never silently becomes "pass" for
  the new tree.
- Tiers 1 to 3 carry timestamps and are shown stale after the configured window
  (`stale_after_s`) or when they predate HEAD.
- A dirty working tree makes any tier 4 result "unknown" for the tree it did not cover.

### Forgery considerations

- The spool, projection, artifacts and lockfile are writable by a same-user agent. Tiers 1
  to 3 can be forged or deleted and are labelled so. Hash digests (BLAKE2s, SHA-256) detect
  accidental change and give de-duplication; they are not authentication.
- Tier 4 must be produced outside the agent's reach: a separate process or CI, a store the
  agent has no write path to (a signed record, a CI status, a git ref in a protected
  remote), and a runner that fetches its own copy of the commit. Designing this is v0.3
  work and needs its own ADR and threat model.
- A prompt-injected agent can also tell the human a convincing story; the UI must not
  repeat claims as facts.
- Do not mix tiers in one number. There is no aggregate score.

## Implementation status

Divergent-from-code: see the header and ADR 0003 section 3. The follow-up is to stop
`tui/gates.py` from mapping `test.completed` / `verification.observed` to PASS or FAIL and to
label each displayed signal with its tier.

## Consequences

- Positive: the product cannot imply a guarantee it does not have; self-reported data cannot
  be laundered into gates; v0.3 has a clear target.
- Negative / costs: v0.1 has no working gates (all "not evaluated"), which reads as less
  useful; tier 4 needs infrastructure outside Cursor.
- Follow-ups: fix the TUI gate derivation; label tiers in the UI; v0.3 ADR for tier 4.

## Open questions

- Where can tier 4 evidence live so that a same-user agent cannot write it (CI status, a
  separate OS user, a signed note)?
- Is a tree hash enough for monorepos with unrelated changes?

## Alternatives considered

- Let observed test commands satisfy gates with a "heuristic" caveat: rejected, a caveat
  does not stop a green tile being read as a guarantee.
- Let self-reported handoffs count if signed by the author role: rejected, the role is a
  claim made by the same party.
- Score aggregation across tiers: rejected, mixes trust levels.
