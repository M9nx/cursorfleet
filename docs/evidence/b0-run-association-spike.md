# B0: Run-association feasibility spike

Date: 2026-10-05. Status: **procedure approved**; execute on maintainer machine.

## Invariant

Suggested session→run links may be computed; **membership is never silent**.

## Scenarios

| # | Scenario | Pass criteria |
| --- | --- | --- |
| 1 | One active run, multiple Cursor chats | User attaches each chat ≤3 actions; all appear under one run |
| 2 | Two simultaneous runs, one repo | Runs disambiguated; no cross-attach |
| 3 | Runs in linked worktrees | Active pointer respects cwd/worktree (document choice) |
| 4 | First hook after `run start` | Session correlated without pasting UUID |
| 5 | Two chats start simultaneously | Picker resolves ambiguity; no auto-merge |
| 6 | Restart Cursor + CursorFleet | Active run survives in `<git-common-dir>/cursorfleet/runs/` |
| 7 | Archive run A while B active | A hidden from Active list; B unchanged |

## UX candidates (pick in spike)

1. `cursorfleet run start --task <slug>` + TUI/CLI **attach** picker
2. Short token env `CURSORFLEET_ACTIVE_RUN=<token>`
3. Artifact `task` slug → **candidate** list only until confirm

## Storage (recommended)

```text
<git-common-dir>/cursorfleet/runs/<run_id>.json
<git-common-dir>/cursorfleet/runs/index.json   # active pointers
```

## Results (2026-10-05 code path)

| # | Result | Notes |
| --- | --- | --- |
| 1 | PARTIAL | `run attach` + env `CURSORFLEET_ACTIVE_RUN` on hook path; TUI picker not yet |
| 2 | PARTIAL | Separate run files; user must not attach to wrong id |
| 3 | OPEN | Per-repo common dir only; linked worktree cwd not re-tested live |
| 4 | PARTIAL | Env token attach on first indexed hook event |
| 5 | OPEN | No TUI picker yet |
| 6 | PARTIAL | JSON under `cursorfleet/runs/` survives restarts |
| 7 | PARTIAL | `run archive` + TUI hides archived from active list |

**Chosen UX for B2:** CLI `run start` / `run attach` + optional env token; artifact task slug
→ suggested sessions on Active run screen only.
