# ADR 0005: Naming and trademark

- Status: accepted (fallback name availability unverified)
- Date: 2026-10-04
- Deciders: project owner (M9nx)
- Evidence level: assumption (no legal advice sought)

## Context

- "Cursor" is a trademark of Anysphere. A product named `CursorFleet` could draw a
  naming complaint.
- Per the reviewed plan, `cursorfleet` is free on PyPI and has no GitHub name
  collision. This was not re-checked here. Availability of `fleet-for-cursor` is **unverified**.
- The repo started as `agentdeck`; the plan renamed it to `M9nx/cursorfleet`.

## Decision

- The project is **CursorFleet**; package and CLI `cursorfleet`; committed
  config `.cursorfleet/`; runtime dir `cursorfleet/` under the git common dir.
- Always state: "Unofficial: not affiliated with or endorsed by Anysphere or
  Cursor. 'Cursor' is a trademark of its respective owner." This appears in the
  README, docs front matter, `--help` epilog (M1), PyPI long description and the
  first-run output.
- Use "Cursor" only to describe compatibility ("for Cursor"), never as a logo,
  never in a way implying endorsement. No Cursor logo, colors or imitation of its
  branding. Do this before PyPI publish and before any logo.
- **Fallback name:** `fleet-for-cursor` (nominative "for Cursor" form; CLI
  `fleet`, import `fleet_for_cursor`). Check PyPI and GitHub availability before
  relying on it, and reserve it before v0.1.0 if cheap.
- Switch to the fallback if Anysphere or counsel objects, or if guidance
  changes. Cost of renaming: package, CLI, `.cursorfleet/` and runtime dir names,
  docs, schemas `$id`. A migration reads the old directories once.

## Consequences

- Positive: clear unofficial status; a prepared exit if challenged.
- Negative / costs: a later rename touches installed hooks (they invoke
  `cursorfleet hook ...`) and committed `.cursorfleet/` directories.
- Follow-ups (owner): check PyPI/GitHub for the fallback; run a trademark search
  before v0.1.0; add the notice to PyPI metadata at M4.

## Open questions

- Would a non-"Cursor" brand (for example `agentfleet`) be safer for the long term?

## Alternatives considered

- Keep `AgentDeck`: rejected earlier; the project is Cursor-only for v0.1 and the
  name would hide that.
- Name without "Cursor": safer legally, weaker discoverability; kept as the
  long-term option.
