# ADR 0000: ADR process and template

- Status: accepted
- Date: 2026-10-04
- Deciders: project owner (M9nx)
- Evidence level: n/a (process decision)
- Supersedes: none
- Superseded by: none
- Related ADRs: all (this ADR governs the format of every other ADR)
- Implementation status: Implemented (this document and [`README.md`](README.md) are the process)
- Review trigger: an ADR is found whose fields cannot express its state, or a second maintainer joins and wants a different workflow
- Release gate: none; but every other ADR must carry all required fields below before v0.1.0 is tagged

This file is both the decision that defines how CursorFleet records decisions and the
template to copy. To write a new ADR, copy everything from "ADR NNNN" below the rule.

## Process

- One decision per ADR, numbered sequentially, never renumbered. The next free number is
  the highest number in the [index](README.md) plus one.
- Do not rewrite an accepted decision. Supersede it with a new ADR and set the old one to
  `Superseded by`, keeping its content. Fixing typos and filling in "Implementation status"
  is fine. Provisional ADRs may be edited in place while they are provisional.
- Every ADR carries all required fields below. A field with nothing to say says `none`; it
  is never omitted.
- Facts are tagged by origin: Cursor docs (URL and fetch date), a captured payload (with
  `cursor_version`), the code (file path), or assumption. Verified facts and unverified
  claims live in separate lists.
- "Implementation status" describes the code in this repository, not the intent. Use one of:
  - `Not implemented`
  - `Implemented-provisional` (code exists, not validated against live Cursor)
  - `Implemented`
  - `Divergent-from-code` followed by the exact divergences and the files affected
- Divergences are recorded, then listed in [`../follow-ups.md`](../follow-ups.md). A docs
  pass does not change code to hide a divergence.
- The index in [`README.md`](README.md) lists every ADR with status, supersession links,
  implementation status and release gate. Update it in the same commit as the ADR.
- ADRs are the author's own reasoning, reviewed by the author. They are not an independent
  audit and do not replace one.

## Required fields

- `Status`: `proposed | accepted | provisional | superseded | rejected`.
- `Date`: ISO date of the last substantive change to the decision.
- `Deciders`: names or roles.
- `Evidence level`: `verified-from-docs | empirically-verified | assumption`, per part if mixed.
- `Supersedes`: ADR numbers this replaces, or `none`.
- `Superseded by`: ADR number, or `none`.
- `Related ADRs`: ADRs that constrain or depend on this one.
- `Implementation status`: see above.
- `Review trigger`: a concrete event or condition that forces this ADR to be re-reviewed
  (for example "spike Q1 answered", "name chosen", "first public release candidate"). "As
  needed" is not a trigger.
- `Release gate`: what must be true before v0.1.0 is tagged, or `none`.

---

# ADR NNNN: Short imperative title

- Status: proposed | accepted | provisional | superseded | rejected
- Date: YYYY-MM-DD
- Deciders: names or roles
- Evidence level: verified-from-docs | empirically-verified | assumption
- Supersedes: none
- Superseded by: none
- Related ADRs: none
- Implementation status: Not implemented | Implemented-provisional | Implemented | Divergent-from-code (details)
- Review trigger: concrete event or condition
- Release gate: what must be true before v0.1.0, or none

## Context

What forces are at play? Facts only, each tagged where it came from. Keep verified facts
and unverified claims in separate lists.

## Decision

What we decided, in active voice ("We will ..."). Note which parts are provisional and
what would change them.

## Consequences

- Positive:
- Negative / costs:
- Follow-ups and owners:

## Open questions

Questions that could invalidate this decision, with the spike or test that answers each.

## Alternatives considered

Each alternative and why it was not chosen.
