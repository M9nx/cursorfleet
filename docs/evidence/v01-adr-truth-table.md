# v0.1.0 ADR / release truth table

Last updated: 2026-10-12. **Met** = satisfied for v0.1.0 as amended. **Open** = owner/live action.

| Gate ID | Checklist § | Code fact | v0.1.0 | Evidence | Product claim |
| --- | --- | --- | --- | --- | --- |
| 0001 | A.1–A.7 | Linux IDE smoke; Q1/Q2 OPEN | Amended | [live-validation-index](live-validation-index.md) | Linux Cursor IDE only |
| 0002 | A.3 | CRC32; unkeyed wt ids | Amended | ADR 0002 amendment 2026-10-12 | No HMAC worktree claims |
| 0003 | A.3 | verification.observed; display OFF; status/0.2 | Met / Amended | hook tests, ADR 0003 amendment | Display opt-in; observations not gates |
| 0005 | C.11 | CursorFleet / cursorfleet | Met | [adr-0005-naming-gate](adr-0005-naming-gate.md) | Unofficial working name; re-check PyPI at tag |
| 0006 | A.3 | TOML scan; no digest dedupe | Amended | ADR 0006 amendment 2026-10-12 | Self-reported artifacts |
| 0007 | A.3, A.5 | 12 observe hooks | Amended | ADR 0007 amendment 2026-10-12 | Twelve passive hooks |
| 0008 | — | Fail-open allow | Met | hook_policy | Observe only |
| 0009 | C | init root exit 2; CI round-trip | Met | integration tests | Repo root install |
| 0010 | — | lane_basis in UI/status | Met | tests | Basis on lanes |
| 0011 | — | No tier 1–3 PASS/FAIL | Met | tui/gates.py | Non-authoritative observations |
| 0012 | — | Attribution labels | Met | tui, docs | No isolation claims |
| 0013 | — | run CLI + attach; scoped git | Met | B0/B1 evidence, unit tests | Explicit run association |
| SO-01 | A.5 | Partial live smoke | **Open** | Maintainer | Permission allow reply |

Tag blocked on rows marked **Open** — see [v01-release-ready.md](v01-release-ready.md).
